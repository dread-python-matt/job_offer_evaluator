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

import { ApiService } from '../../core/services/api.service';
import { AvailableModels, CurrentModelConfig, OrgSpend } from '../../core/models/profile.model';
import { ApiKeys } from '../api-keys/api-keys';
import { AdminKey } from '../admin-key/admin-key';

@Component({
  selector: 'app-model-usage',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    ApiKeys,
    AdminKey,
  ],
  templateUrl: './model-usage.html',
  styleUrl: './model-usage.scss',
})
export class ModelUsage implements OnInit {
  private readonly api = inject(ApiService);

  readonly loading = signal(false);
  readonly error = signal(false);
  readonly currentModel = signal<CurrentModelConfig | null>(null);
  readonly availableModels = signal<AvailableModels | null>(null);
  readonly selecting = signal(false);
  readonly selectError = signal<string | null>(null);
  readonly orgSpend = signal<OrgSpend | null>(null);

  /** Bumped whenever the embedded daily-request budget may have changed (model switch, key
   * add/remove, manual refresh); forwarded to <app-api-keys>, which passes it to the per-day
   * budget on the Google key row so it refetches for the newly active model. */
  readonly dailyRefresh = signal(0);

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
        this.dailyRefresh.update((n) => n + 1); // the active model changed → refetch its budget
      });
  }

  ngOnInit(): void {
    this.load();
  }

  /** Refresh everything on this page, including the embedded daily-request budget card. Used by
   * the refresh button and by child cards (keys/admin key) whose changes affect the budget. */
  reloadAll(): void {
    this.load();
    this.dailyRefresh.update((n) => n + 1);
  }

  load(): void {
    this.loading.set(true);
    this.error.set(false);
    forkJoin({
      models: this.api.getAvailableModels(),
      orgSpend: this.api.getOrgSpend().pipe(catchError(() => of(null))),
    }).subscribe({
      next: ({ models, orgSpend }) => {
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
}
