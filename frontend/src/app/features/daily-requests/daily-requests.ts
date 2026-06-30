import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ApiService } from '../../core/services/api.service';
import { DailyRequestUsage } from '../../core/models/profile.model';

@Component({
  selector: 'app-daily-requests',
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
    MatTooltipModule,
  ],
  templateUrl: './daily-requests.html',
  styleUrl: './daily-requests.scss',
})
export class DailyRequests {
  private readonly api = inject(ApiService);

  /** A monotonically increasing token the host bumps whenever the per-day budget may have
   * changed (model switch, key add/remove, manual refresh), so this card refetches. The GET
   * reads the server-side model selection; the token is just the re-trigger. */
  readonly refreshToken = input<number>(0);

  readonly loading = signal(false);
  readonly error = signal(false);
  readonly usage = signal<DailyRequestUsage | null>(null);

  readonly saving = signal(false);
  readonly actionError = signal<string | null>(null);
  readonly editing = signal(false);

  readonly limitControl = new FormControl<number | null>(null, {
    validators: [Validators.required, Validators.min(0)],
  });

  constructor() {
    effect(() => {
      this.refreshToken(); // re-run on initial mount and whenever the host bumps the token
      this.load();
    });
  }

  load(): void {
    this.loading.set(true);
    this.error.set(false);
    this.actionError.set(null);
    this.editing.set(false);
    this.api.getDailyRequestUsage().subscribe({
      next: (usage) => {
        this.usage.set(usage);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }

  usedPct(u: DailyRequestUsage): number {
    if (u.limit <= 0) return 100;
    return Math.min((u.used / u.limit) * 100, 100);
  }

  barClass(u: DailyRequestUsage): string {
    const pct = this.usedPct(u);
    if (pct >= 90) return 'bar-critical';
    if (pct >= 70) return 'bar-warning';
    return 'bar-ok';
  }

  /** True when the cap in effect is the user's own override rather than the free-tier default. */
  isOverridden(u: DailyRequestUsage): boolean {
    return u.default_limit == null || u.limit !== u.default_limit;
  }

  startEdit(u: DailyRequestUsage): void {
    this.limitControl.setValue(u.limit);
    this.actionError.set(null);
    this.editing.set(true);
  }

  cancelEdit(): void {
    this.editing.set(false);
  }

  save(): void {
    if (this.saving() || this.limitControl.invalid) {
      this.limitControl.markAsTouched();
      return;
    }
    this.put(this.limitControl.value, 'Could not update the daily request limit.');
  }

  resetToDefault(): void {
    this.put(null, 'Could not reset the daily request limit.');
  }

  private put(limit: number | null, fallback: string): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.actionError.set(null);
    this.api.setDailyRequestLimit(limit).subscribe({
      next: (updated) => {
        this.usage.set(updated);
        this.saving.set(false);
        this.editing.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(this.messageFor(err, fallback));
        this.saving.set(false);
      },
    });
  }

  private messageFor(err: HttpErrorResponse, fallback: string): string {
    const detail = err.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
