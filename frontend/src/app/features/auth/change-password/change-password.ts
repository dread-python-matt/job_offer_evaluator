import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AuthService } from '../../../core/services/auth.service';
import { AuthShell } from '../auth-shell/auth-shell';
import { AuthLogo } from '../auth-logo/auth-logo';

// Mirrors the backend minimum (ChangePasswordRequestSchema); the server enforces it too.
const MIN_PASSWORD_LENGTH = 10;

// Group-level validator: the retyped new password must match. Same pattern as register.ts.
function newPasswordsMatch(group: AbstractControl): ValidationErrors | null {
  const newPassword = group.get('newPassword')?.value;
  const confirmPassword = group.get('confirmPassword')?.value;
  return newPassword === confirmPassword ? null : { passwordMismatch: true };
}

@Component({
  selector: 'app-change-password',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    AuthShell,
    AuthLogo,
  ],
  templateUrl: './change-password.html',
  styleUrl: './change-password.scss',
})
export class ChangePassword {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);

  readonly minPasswordLength = MIN_PASSWORD_LENGTH;
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly success = signal(false);
  // Tracks which password fields are currently shown as plain text.
  private readonly revealed = signal<ReadonlySet<string>>(new Set());

  isRevealed(field: string): boolean {
    return this.revealed().has(field);
  }

  toggleReveal(field: string): void {
    this.revealed.update((shown) => {
      const next = new Set(shown);
      if (next.has(field)) {
        next.delete(field);
      } else {
        next.add(field);
      }
      return next;
    });
  }

  readonly form = this.fb.group(
    {
      currentPassword: this.fb.control('', {
        nonNullable: true,
        validators: [Validators.required],
      }),
      newPassword: this.fb.control('', {
        nonNullable: true,
        validators: [Validators.required, Validators.minLength(MIN_PASSWORD_LENGTH)],
      }),
      confirmPassword: this.fb.control('', {
        nonNullable: true,
        validators: [Validators.required],
      }),
    },
    { validators: newPasswordsMatch },
  );

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    this.error.set(null);
    this.success.set(false);
    const { currentPassword, newPassword } = this.form.getRawValue();
    this.auth
      .changePassword({ current_password: currentPassword, new_password: newPassword })
      .subscribe({
        next: () => {
          this.submitting.set(false);
          this.success.set(true);
          this.form.reset();
        },
        error: (err) => {
          this.submitting.set(false);
          this.error.set(
            err.status === 401
              ? 'Your current password is incorrect.'
              : 'Something went wrong. Please try again.',
          );
        },
      });
  }
}
