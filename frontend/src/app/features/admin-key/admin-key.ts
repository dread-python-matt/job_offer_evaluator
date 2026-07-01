import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { HttpErrorResponse } from '@angular/common/http';

import { ApiService } from '../../core/services/api.service';
import { AdminKey as AdminKeyModel, OrgSpend } from '../../core/models/profile.model';

@Component({
  selector: 'app-admin-key',
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
    MatTooltipModule,
  ],
  templateUrl: './admin-key.html',
  styleUrl: './admin-key.scss',
})
export class AdminKey implements OnInit {
  private readonly api = inject(ApiService);

  /** Emitted when the admin key is saved or removed, so a host can refresh anything
   * derived from it — e.g. the organization spend/usage readouts. */
  readonly changed = output<void>();

  /** Authoritative org-wide spend month-to-date (from the admin usage API), passed in by the
   * host. Shown below the key as the "actual" figure the admin key powers; null when no admin
   * key (saved or env) is configured or the figure is unavailable. */
  readonly spend = input<OrgSpend | null>(null);

  readonly loading = signal(false);
  readonly error = signal(false);
  /** The saved key as a masked view, or null when none is configured. */
  readonly adminKey = signal<AdminKeyModel | null>(null);

  readonly saving = signal(false);
  readonly removing = signal(false);
  readonly actionError = signal<string | null>(null);
  readonly showKey = signal(false);

  readonly keyControl = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required],
  });

  /** Wraps keyControl so the <form> carries a FormGroupDirective. Without it, `(ngSubmit)`
   * never binds and the submit button does a native page reload instead of calling save() —
   * so no PUT /admin-key is ever sent (this was the "admin key won't save" bug). Mirrors the
   * api-keys add form. */
  readonly form = new FormGroup({ key: this.keyControl });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(false);
    this.api.getAdminKey().subscribe({
      next: (key) => {
        this.adminKey.set(key);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }

  toggleShowKey(): void {
    this.showKey.update((shown) => !shown);
  }

  save(): void {
    if (this.saving() || this.keyControl.invalid) {
      this.keyControl.markAsTouched();
      return;
    }
    const key = this.keyControl.value.trim();
    // Catch the most common mistake up front (instead of a silent 400): pasting a project key
    // (sk-proj-…) — the inference key used elsewhere — into the admin field. OpenAI org/admin
    // endpoints only accept an Organization admin key, which starts with "sk-admin-".
    if (!key.startsWith('sk-admin-')) {
      this.actionError.set(
        'That looks like a project/inference key, not an Organization admin key. The admin key ' +
          'must start with “sk-admin-”. Create one under your OpenAI org settings → Admin keys.',
      );
      return;
    }
    this.saving.set(true);
    this.actionError.set(null);
    this.api.setAdminKey(key).subscribe({
      next: (saved) => {
        this.adminKey.set(saved);
        this.keyControl.reset('');
        this.saving.set(false);
        this.changed.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(this.messageFor(err, 'Could not save the admin key.'));
        this.saving.set(false);
      },
    });
  }

  remove(): void {
    if (this.removing()) return;
    this.removing.set(true);
    this.actionError.set(null);
    this.api.deleteAdminKey().subscribe({
      next: () => {
        this.adminKey.set(null);
        this.removing.set(false);
        this.changed.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(this.messageFor(err, 'Could not remove the admin key.'));
        this.removing.set(false);
      },
    });
  }

  private messageFor(err: HttpErrorResponse, fallback: string): string {
    const detail = err.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
