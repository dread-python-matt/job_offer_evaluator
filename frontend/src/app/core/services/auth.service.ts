import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, catchError, finalize, of, shareReplay, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AuthUser,
  ChangePasswordRequest,
  Credentials,
  RegisterRequest,
  RegistrationPending,
  ResetPasswordRequest,
} from '../models/auth.model';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  private readonly _currentUser = signal<AuthUser | null>(null);
  readonly currentUser = this._currentUser.asReadonly();
  readonly isAuthenticated = computed(() => this._currentUser() !== null);

  // A single in-flight /auth/refresh shared by all callers, so concurrent 401s trigger one
  // rotation instead of racing each other.
  private refresh$: Observable<AuthUser> | null = null;

  /** Create an account. The server returns 202 with no session — the account is unverified
   * until the emailed confirmation link is followed — so this does not sign the user in. */
  register(payload: RegisterRequest): Observable<RegistrationPending> {
    return this.http.post<RegistrationPending>(`${this.baseUrl}/auth/register`, payload);
  }

  /** Confirm a newly-registered email from the emailed token. The server verifies the
   * account and issues a session, so the user lands signed in. */
  verifyEmail(token: string): Observable<AuthUser> {
    return this.http
      .post<AuthUser>(`${this.baseUrl}/auth/verify-email`, { token })
      .pipe(tap((user) => this._currentUser.set(user)));
  }

  login(credentials: Credentials): Observable<AuthUser> {
    return this.http
      .post<AuthUser>(`${this.baseUrl}/auth/login`, credentials)
      .pipe(tap((user) => this._currentUser.set(user)));
  }

  logout(): Observable<void> {
    return this.http
      .post<void>(`${this.baseUrl}/auth/logout`, {})
      .pipe(tap(() => this._currentUser.set(null)));
  }

  /** Exchange the refresh-token cookie for a new access token, rotating the refresh token.
   * Concurrent callers share one in-flight request. */
  refreshSession(): Observable<AuthUser> {
    this.refresh$ ??= this.http.post<AuthUser>(`${this.baseUrl}/auth/refresh`, {}).pipe(
      tap((user) => this._currentUser.set(user)),
      finalize(() => {
        this.refresh$ = null;
      }),
      shareReplay(1),
    );
    return this.refresh$;
  }

  /** Change the signed-in user's password. The server re-issues this device's session
   * cookie, so the current session stays valid while other sessions are invalidated. */
  changePassword(payload: ChangePasswordRequest): Observable<void> {
    return this.http.post<void>(`${this.baseUrl}/auth/password`, payload);
  }

  /** Start the password-reset flow. The response is the same whether or not the email is
   * registered, so callers should always show a neutral "check your email" message. */
  requestPasswordReset(email: string): Observable<void> {
    return this.http.post<void>(`${this.baseUrl}/auth/forgot-password`, { email });
  }

  /** Complete the password-reset flow from the emailed token. The server issues a fresh
   * session, so the user lands signed in. */
  resetPassword(payload: ResetPasswordRequest): Observable<AuthUser> {
    return this.http
      .post<AuthUser>(`${this.baseUrl}/auth/reset-password`, payload)
      .pipe(tap((user) => this._currentUser.set(user)));
  }

  /** Resolve the current session from the cookie (e.g. on a page reload). Returns
   * null without erroring when there is no valid session. */
  loadCurrentUser(): Observable<AuthUser | null> {
    return this.http.get<AuthUser>(`${this.baseUrl}/auth/me`).pipe(
      tap((user) => this._currentUser.set(user)),
      // On reload with an expired access token, fall back to a refresh so a still-valid
      // refresh cookie keeps the user signed in instead of silently logging them out.
      catchError(() =>
        this.refreshSession().pipe(
          catchError(() => {
            this._currentUser.set(null);
            return of(null);
          }),
        ),
      ),
    );
  }

  /** Locally forget the session (used when the server reports 401). */
  clearSession(): void {
    this._currentUser.set(null);
  }
}
