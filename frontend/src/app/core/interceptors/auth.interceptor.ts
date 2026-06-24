import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthService } from '../services/auth.service';

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
const CSRF_COOKIE = 'csrf_token';

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Sends the auth cookie with every request (withCredentials), echoes the CSRF cookie
 * as a header on state-changing requests (double-submit), and on a 401 forgets the
 * session and routes to /login. The /auth/* calls are exempt from the redirect so a
 * normal "not logged in" probe doesn't bounce. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  const auth = inject(AuthService);

  let request = req.clone({ withCredentials: true });
  if (!SAFE_METHODS.has(req.method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) {
      request = request.clone({ headers: request.headers.set('X-CSRF-Token', csrf) });
    }
  }

  return next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !req.url.includes('/auth/')) {
        auth.clearSession();
        router.navigate(['/login']);
      }
      return throwError(() => error);
    }),
  );
};
