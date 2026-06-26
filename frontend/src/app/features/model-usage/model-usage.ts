import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, filter, forkJoin, of, switchMap } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ApiService } from '../../core/services/api.service';
import {
  AvailableModels,
  CurrentModelConfig,
  ModelUsageSummaryItem,
  OrgSpend,
} from '../../core/models/profile.model';
import { ApiKeys } from '../api-keys/api-keys';

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
    MatProgressSpinnerModule,
    MatSelectModule,
    MatTooltipModule,
    ApiKeys,
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
  readonly orgSpend = signal<OrgSpend | null>(null);

  readonly selectedCompany = signal<string | null>(null);

  readonly companyControl = new FormControl<string | null>(null);
  readonly modelControl = new FormControl<string | null>(null);

  constructor() {
    this.companyControl.valueChanges
      .pipe(
        filter((v): v is string => v != null),
        takeUntilDestroyed(),
      )
      .subscribe((company) => {
        this.selectedCompany.set(company);
        const models = this.availableModels();
        const first = models?.companies.find((c) => c.name === company)?.models[0] ?? null;
        this.modelControl.setValue(first);
      });

    this.modelControl.valueChanges
      .pipe(
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
      )
      .subscribe((updated) => {
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
      orgSpend: this.api.getOrgSpend().pipe(catchError(() => of(null))),
    }).subscribe({
      next: ({ summary, models, orgSpend }) => {
        this.items.set(summary);
        this.currentModel.set(models.active);
        this.availableModels.set(models);
        this.selectedCompany.set(models.active.company);
        this.companyControl.setValue(models.active.company, { emitEvent: false });
        this.modelControl.setValue(models.active.model, { emitEvent: false });
        this.orgSpend.set(orgSpend);
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
    return available.companies.find((c) => c.name === company)?.models ?? [];
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
}
