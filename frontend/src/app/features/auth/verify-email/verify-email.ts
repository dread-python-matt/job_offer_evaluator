import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AuthService } from '../../../core/services/auth.service';
import { AuthShell } from '../auth-shell/auth-shell';
import { AuthLogo } from '../auth-logo/auth-logo';

@Component({
  selector: 'app-verify-email',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatCardModule, MatProgressSpinnerModule, AuthShell, AuthLogo],
  templateUrl: './verify-email.html',
  styleUrl: './verify-email.scss',
})
export class VerifyEmail implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly status = signal<'verifying' | 'error'>('verifying');
  readonly error = signal<string | null>(null);
  // The token comes from the emailed link (?token=...); empty when the link is malformed.
  private readonly token = this.route.snapshot.queryParamMap.get('token') ?? '';

  ngOnInit(): void {
    if (!this.token) {
      this.fail('This confirmation link is invalid or has expired.');
      return;
    }
    this.auth.verifyEmail(this.token).subscribe({
      // Verifying issues a session, so the user lands signed in.
      next: () => this.router.navigateByUrl('/profile'),
      error: (err) => {
        if (err.status === 409) {
          this.fail('Your email is already confirmed. Please sign in.');
        } else if (err.status === 400) {
          this.fail('This confirmation link is invalid or has expired.');
        } else {
          this.fail('Something went wrong confirming your email. Please try again.');
        }
      },
    });
  }

  private fail(message: string): void {
    this.status.set('error');
    this.error.set(message);
  }
}
