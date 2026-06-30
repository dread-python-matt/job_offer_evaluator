import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AuthService } from '../../../core/services/auth.service';
import {
  MIN_PASSWORD_LENGTH,
  PASSWORD_REQUIREMENTS_HINT,
  passwordStrength,
} from '../../../core/validators/password';
import { AuthShell } from '../auth-shell/auth-shell';
import { AuthLogo } from '../auth-logo/auth-logo';

// Group-level validator: the retyped password must match. Mirrors the server's check
// (RegisterRequestSchema) so mismatches are caught before a request is made.
function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const password = group.get('password')?.value;
  const confirmPassword = group.get('confirmPassword')?.value;
  return password === confirmPassword ? null : { passwordMismatch: true };
}

@Component({
  selector: 'app-register',
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
  templateUrl: './register.html',
  styleUrl: './register.scss',
})
export class Register {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);

  readonly minPasswordLength = MIN_PASSWORD_LENGTH;
  readonly passwordHint = PASSWORD_REQUIREMENTS_HINT;
  readonly submitting = signal(false);
  readonly submitted = signal(false);
  readonly error = signal<string | null>(null);
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
      email: this.fb.control('', {
        nonNullable: true,
        validators: [Validators.required, Validators.email],
      }),
      password: this.fb.control('', {
        nonNullable: true,
        validators: [
          Validators.required,
          Validators.minLength(MIN_PASSWORD_LENGTH),
          passwordStrength,
        ],
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
    const { email, password, confirmPassword } = this.form.getRawValue();
    this.auth.register({ email, password, confirm_password: confirmPassword }).subscribe({
      // Registration issues no session — the account is unverified until the emailed link is
      // followed (see VerifyEmail). Show a "check your email" prompt rather than signing in.
      next: () => {
        this.submitting.set(false);
        this.submitted.set(true);
      },
      error: (err) => {
        this.submitting.set(false);
        this.error.set(
          err.status === 409
            ? 'That email is already registered.'
            : 'Something went wrong. Please try again.',
        );
      },
    });
  }
}
