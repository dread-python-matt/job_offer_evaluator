import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, catchError, of, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import { AuthUser, Credentials, RegisterRequest } from '../models/auth.model';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  private readonly _currentUser = signal<AuthUser | null>(null);
  readonly currentUser = this._currentUser.asReadonly();
  readonly isAuthenticated = computed(() => this._currentUser() !== null);

  register(payload: RegisterRequest): Observable<AuthUser> {
    return this.http
      .post<AuthUser>(`${this.baseUrl}/auth/register`, payload)
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

  /** Resolve the current session from the cookie (e.g. on a page reload). Returns
   * null without erroring when there is no valid session. */
  loadCurrentUser(): Observable<AuthUser | null> {
    return this.http.get<AuthUser>(`${this.baseUrl}/auth/me`).pipe(
      tap((user) => this._currentUser.set(user)),
      catchError(() => {
        this._currentUser.set(null);
        return of(null);
      }),
    );
  }

  /** Locally forget the session (used when the server reports 401). */
  clearSession(): void {
    this._currentUser.set(null);
  }
}
