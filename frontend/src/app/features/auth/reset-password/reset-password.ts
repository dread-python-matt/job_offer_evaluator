import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AuthService } from '../../../core/services/auth.service';
import { AuthShell } from '../auth-shell/auth-shell';
import { AuthLogo } from '../auth-logo/auth-logo';

// Mirrors the backend minimum (ResetPasswordRequestSchema); the server enforces it too.
const MIN_PASSWORD_LENGTH = 10;

// Group-level validator: the retyped new password must match. Same pattern as register.ts.
function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const newPassword = group.get('newPassword')?.value;
  const confirmPassword = group.get('confirmPassword')?.value;
  return newPassword === confirmPassword ? null : { passwordMismatch: true };
}

@Component({
  selector: 'app-reset-password',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    AuthShell,
    AuthLogo,
  ],
  templateUrl: './reset-password.html',
  styleUrl: './reset-password.scss',
})
export class ResetPassword {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly minPasswordLength = MIN_PASSWORD_LENGTH;
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  // The token comes from the emailed link (?token=...); empty when the link is malformed.
  readonly token = this.route.snapshot.queryParamMap.get('token') ?? '';
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
      newPassword: this.fb.control('', {
        nonNullable: true,
        validators: [Validators.required, Validators.minLength(MIN_PASSWORD_LENGTH)],
      }),
      confirmPassword: this.fb.control('', {
        nonNullable: true,
        validators: [Validators.required],
      }),
    },
    { validators: passwordsMatch },
  );

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    this.error.set(null);
    const { newPassword, confirmPassword } = this.form.getRawValue();
    this.auth
      .resetPassword({
        token: this.token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      })
      .subscribe({
        // A reset issues a session, so the user lands signed in.
        next: () => this.router.navigateByUrl('/profile'),
        error: (err) => {
          this.submitting.set(false);
          this.error.set(
            err.status === 400
              ? 'This reset link is invalid or has expired.'
              : 'Something went wrong. Please try again.',
          );
        },
      });
  }
}
