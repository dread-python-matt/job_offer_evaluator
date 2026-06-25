import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';

import { AuthService } from '../services/auth.service';

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
const CSRF_COOKIE = 'csrf_token';
// A 401 from these must NOT trigger a refresh: /auth/refresh itself (would loop), the
// pre-auth flows (a refresh is meaningless there), and /auth/me (its own probe handles the
// refresh fallback without redirecting, so a logged-out load doesn't bounce off /register).
const NO_REFRESH = [
  '/auth/refresh',
  '/auth/login',
  '/auth/register',
  '/auth/verify-email',
  '/auth/forgot-password',
  '/auth/reset-password',
  '/auth/me',
];

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Add credentials and, for state-changing requests, the double-submit CSRF header read
 * fresh from the cookie (so a retry after a refresh carries the rotated CSRF token). */
function withCredentialsAndCsrf(req: HttpRequest<unknown>): HttpRequest<unknown> {
  let request = req.clone({ withCredentials: true });
  if (!SAFE_METHODS.has(req.method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) {
      request = request.clone({ headers: request.headers.set('X-CSRF-Token', csrf) });
    }
  }
  return request;
}

/** Sends cookies + CSRF on every request. On a 401 (likely an expired access token), rotates
 * the session via /auth/refresh and retries the original request once; if the refresh fails,
 * forgets the session and routes to /login. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  const auth = inject(AuthService);

  return next(withCredentialsAndCsrf(req)).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401 || NO_REFRESH.some((path) => req.url.includes(path))) {
        return throwError(() => error);
      }
      return auth.refreshSession().pipe(
        switchMap(() => next(withCredentialsAndCsrf(req))),
        catchError(() => {
          auth.clearSession();
          router.navigate(['/login']);
          return throwError(() => error);
        }),
      );
    }),
  );
};
