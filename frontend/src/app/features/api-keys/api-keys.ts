import { DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { HttpErrorResponse } from '@angular/common/http';

import { ApiService } from '../../core/services/api.service';
import { ApiKey, ApiProvider } from '../../core/models/profile.model';
import { DailyRequests } from '../daily-requests/daily-requests';

@Component({
  selector: 'app-api-keys',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
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
    DailyRequests,
  ],
  templateUrl: './api-keys.html',
  styleUrl: './api-keys.scss',
})
export class ApiKeys implements OnInit {
  private readonly api = inject(ApiService);

  /** Emitted when the set of keys changes (add/delete), so a host can refresh anything
   * derived from them — e.g. the per-user model picker. */
  readonly changed = output<void>();

  /** Bumped by the host (model switch, manual refresh) and forwarded to the embedded
   * per-day budget on the Google key row so it refetches for the newly active model. */
  readonly refreshToken = input<number>(0);

  readonly loading = signal(false);
  readonly error = signal(false);
  readonly keys = signal<ApiKey[]>([]);
  readonly providers = signal<ApiProvider[]>([]);

  readonly adding = signal(false);
  readonly addError = signal<string | null>(null);
  /** The provider whose budget/delete row is mid-request, so only that row shows a spinner. */
  readonly busyProvider = signal<string | null>(null);
  readonly rowError = signal<string | null>(null);

  /** Providers capped by the per-day request budget instead of a USD budget (Google's free
   * tier is requests/day, not dollars). Their key rows hide the dollar budget and adding one
   * doesn't ask for a USD limit. */
  private static readonly REQUEST_BUDGETED = new Set(['google']);

  /** The provider chosen in the add-key form, mirrored as a signal so the template can show or
   * hide the USD budget field under OnPush. */
  readonly selectedAddProvider = signal<string | null>(null);

  readonly providerControl = new FormControl<string | null>(null, {
    validators: [Validators.required],
  });
  readonly keyControl = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required],
  });
  readonly limitControl = new FormControl<number | null>(5, {
    validators: [Validators.required, Validators.min(0)],
  });

  /** Groups the add-key controls so the <form> carries a FormGroupDirective. Without it,
   * `(ngSubmit)` never binds and the submit button does a native page reload instead of
   * calling addKey() — so no POST is ever sent. */
  readonly addForm = new FormGroup({
    provider: this.providerControl,
    key: this.keyControl,
    limit: this.limitControl,
  });

  /** Providers the user hasn't added yet (one key per provider), for the add-key picker. */
  readonly availableProviders = computed(() => {
    const taken = new Set(this.keys().map((k) => k.api_provider));
    return this.providers().filter((p) => !taken.has(p.provider));
  });

  constructor() {
    // Mirror the chosen provider into a signal, and require a USD limit only for USD-budgeted
    // providers — request-budgeted ones (Google) don't carry a dollar budget.
    this.providerControl.valueChanges.pipe(takeUntilDestroyed()).subscribe((provider) => {
      this.selectedAddProvider.set(provider);
      this.limitControl.setValidators(
        provider != null && this.isRequestBudgeted(provider)
          ? []
          : [Validators.required, Validators.min(0)],
      );
      this.limitControl.updateValueAndValidity();
    });
  }

  /** True when a provider is capped by the per-day request budget rather than a USD budget. */
  isRequestBudgeted(provider: string): boolean {
    return ApiKeys.REQUEST_BUDGETED.has(provider);
  }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(false);
    forkJoin({
      providers: this.api.getApiKeyProviders(),
      keys: this.api.getApiKeys(),
    }).subscribe({
      next: ({ providers, keys }) => {
        this.providers.set(providers);
        this.keys.set(keys);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }

  companyFor(provider: string): string {
    return this.providers().find((p) => p.provider === provider)?.company ?? provider;
  }

  usedPct(key: ApiKey): number {
    if (key.limit_usd <= 0) return 100;
    return Math.min((key.used_usd / key.limit_usd) * 100, 100);
  }

  barClass(key: ApiKey): string {
    const pct = this.usedPct(key);
    if (pct >= 90) return 'bar-critical';
    if (pct >= 70) return 'bar-warning';
    return 'bar-ok';
  }

  addKey(): void {
    if (this.adding()) return;
    if (this.addForm.invalid) {
      this.addForm.markAllAsTouched();
      return;
    }
    const provider = this.providerControl.value as string;
    const key = this.keyControl.value.trim();
    // Request-budgeted providers (Google) carry no USD limit — omit it so the backend defaults
    // it to 0 and the key is capped by the per-day request budget instead.
    const limit = this.isRequestBudgeted(provider)
      ? undefined
      : (this.limitControl.value as number);

    this.adding.set(true);
    this.addError.set(null);
    this.api.addApiKey(provider, key, limit).subscribe({
      next: (added) => {
        this.keys.update((list) =>
          [...list, added].sort((a, b) => a.api_provider.localeCompare(b.api_provider)),
        );
        this.providerControl.reset(null);
        this.keyControl.reset('');
        this.limitControl.reset(5);
        this.adding.set(false);
        this.changed.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.addError.set(this.messageFor(err, 'Could not add the key. Please try again.'));
        this.adding.set(false);
      },
    });
  }

  saveBudget(key: ApiKey, rawLimit: number): void {
    if (this.busyProvider() || rawLimit == null || rawLimit < 0) return;
    this.busyProvider.set(key.api_provider);
    this.rowError.set(null);
    this.api.updateApiKeyBudget(key.api_provider, rawLimit).subscribe({
      next: (updated) => {
        this.keys.update((list) =>
          list.map((k) => (k.api_provider === updated.api_provider ? updated : k)),
        );
        this.busyProvider.set(null);
      },
      error: (err: HttpErrorResponse) => {
        this.rowError.set(this.messageFor(err, 'Could not update the budget.'));
        this.busyProvider.set(null);
      },
    });
  }

  removeKey(key: ApiKey): void {
    if (this.busyProvider()) return;
    this.busyProvider.set(key.api_provider);
    this.rowError.set(null);
    this.api.deleteApiKey(key.api_provider).subscribe({
      next: () => {
        this.keys.update((list) => list.filter((k) => k.api_provider !== key.api_provider));
        this.busyProvider.set(null);
        this.changed.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.rowError.set(this.messageFor(err, 'Could not delete the key.'));
        this.busyProvider.set(null);
      },
    });
  }

  private messageFor(err: HttpErrorResponse, fallback: string): string {
    const detail = err.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
