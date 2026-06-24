import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, Observable, catchError, filter, forkJoin, of, switchMap } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ApiService } from '../../core/services/api.service';
import { AvailableModels, Budget, CompanyModels, CurrentModelConfig, DailyCost, ModelUsageSummaryItem } from '../../core/models/profile.model';

@Component({
  selector: 'app-model-usage',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatTooltipModule,
  ],
  templateUrl: './model-usage.html',
  styleUrl: './model-usage.scss',
})
export class ModelUsage implements OnInit {
  private readonly api = inject(ApiService);

  readonly loading = signal(false);
  readonly error = signal(false);
  readonly items = signal<ModelUsageSummaryItem[]>([]);
  readonly currentModel = signal<CurrentModelConfig | null>(null);
  readonly availableModels = signal<AvailableModels | null>(null);
  readonly selecting = signal(false);
  readonly selectError = signal<string | null>(null);
  readonly dailyCost = signal<DailyCost | null>(null);
  readonly trackingSince = signal<string | null>(null);
  readonly budgetBusy = signal(false);
  readonly budgetError = signal<string | null>(null);

  readonly selectedCompany = signal<string | null>(null);

  readonly companyControl = new FormControl<string | null>(null);
  readonly modelControl = new FormControl<string | null>(null);
  readonly limitControl = new FormControl<number | null>(null, {
    validators: [Validators.required, Validators.min(0)],
  });

  constructor() {
    this.companyControl.valueChanges.pipe(
      filter((v): v is string => v != null),
      takeUntilDestroyed(),
    ).subscribe((company) => {
      this.selectedCompany.set(company);
      const models = this.availableModels();
      const first = models?.companies.find(c => c.name === company)?.models[0] ?? null;
      this.modelControl.setValue(first);
    });

    this.modelControl.valueChanges.pipe(
      filter((v): v is string => v != null),
      switchMap((model) => {
        this.selecting.set(true);
        this.selectError.set(null);
        return this.api.selectModel(model).pipe(
          catchError(() => {
            this.selecting.set(false);
            this.selectError.set('Failed to switch model. Please try again.');
            const cm = this.currentModel();
            this.companyControl.setValue(cm?.company ?? null, { emitEvent: false });
            this.modelControl.setValue(cm?.model ?? null, { emitEvent: false });
            this.selectedCompany.set(cm?.company ?? null);
            return EMPTY;
          }),
        );
      }),
      takeUntilDestroyed(),
    ).subscribe((updated) => {
      this.currentModel.set(updated);
      this.selecting.set(false);
    });
  }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(false);
    forkJoin({
      summary: this.api.getUsageSummary(),
      models: this.api.getAvailableModels(),
      cost: this.api.getDailyCost().pipe(catchError(() => of(null))),
    }).subscribe({
      next: ({ summary, models, cost }) => {
        this.items.set(summary);
        this.currentModel.set(models.active);
        this.availableModels.set(models);
        this.selectedCompany.set(models.active.company);
        this.companyControl.setValue(models.active.company, { emitEvent: false });
        this.modelControl.setValue(models.active.model, { emitEvent: false });
        this.dailyCost.set(cost);
        if (cost) {
          this.limitControl.setValue(cost.limit_usd, { emitEvent: false });
        }
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }

  modelsForCompany(): string[] {
    const company = this.selectedCompany();
    const available = this.availableModels();
    if (!company || !available) return [];
    return available.companies.find(c => c.name === company)?.models ?? [];
  }

  total(item: ModelUsageSummaryItem): number {
    return item.input_tokens + item.output_tokens;
  }

  inputPct(item: ModelUsageSummaryItem): number {
    const t = this.total(item);
    return t === 0 ? 50 : (item.input_tokens / t) * 100;
  }

  isActive(item: ModelUsageSummaryItem): boolean {
    const cm = this.currentModel();
    return cm != null && cm.model === item.model;
  }

  costPct(cost: DailyCost): number {
    return Math.min((cost.cost_usd / cost.limit_usd) * 100, 100);
  }

  costBarClass(cost: DailyCost): string {
    const pct = this.costPct(cost);
    if (pct >= 90) return 'cost-critical';
    if (pct >= 70) return 'cost-warning';
    return 'cost-ok';
  }

  saveLimit(): void {
    if (this.limitControl.invalid || this.budgetBusy()) {
      this.limitControl.markAsTouched();
      return;
    }
    const limit = this.limitControl.value as number;
    this.runBudgetMutation(this.api.setBudgetLimit(limit));
  }

  resetUsage(): void {
    if (this.budgetBusy()) return;
    this.runBudgetMutation(this.api.resetUsage());
  }

  private runBudgetMutation(request: Observable<Budget>): void {
    this.budgetBusy.set(true);
    this.budgetError.set(null);
    request.subscribe({
      next: (budget) => this.applyBudget(budget),
      error: () => {
        this.budgetError.set('Failed to update the budget. Please try again.');
        this.budgetBusy.set(false);
      },
    });
  }

  private applyBudget(budget: Budget): void {
    this.dailyCost.set({ cost_usd: budget.used_usd ?? 0, limit_usd: budget.limit_usd });
    this.trackingSince.set(budget.tracking_since);
    this.limitControl.setValue(budget.limit_usd, { emitEvent: false });
    this.budgetBusy.set(false);
  }
}
