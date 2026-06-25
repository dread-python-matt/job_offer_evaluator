# Job Offers Scraper - Project Context

## What This Is
A Python-based app that matches the best offers to a user profile. The backend is a FastAPI JSON API; the frontend is a separate Angular app — no shared process, communicates over HTTP with CORS.

## Tech Stack
- Backend: Python 3.13.14, uv 0.11.20, pytest 9.0.3, ruff 0.15.16, fastapi 0.137.1
- Frontend: Angular (standalone components, `frontend/` directory), Angular Material, npm

## Key Commands

# Backend — run tests
uv run pytest

# Backend — check linting
uv run ruff check

# Backend — apply DB migrations (app-owned tables; the offers table is scraper-owned)
uv run alembic upgrade head

# Backend — run the API (http://localhost:8000)
uv run python main.py

# Frontend — install deps
cd frontend && npm install

# Frontend — run dev server (http://localhost:4200)
cd frontend && npm start

# Frontend — build
cd frontend && npm run build

# Frontend — run tests
cd frontend && npm test

## Authentication
- Every API route is gated except `/health`, `/auth/register`, `/auth/login`, `/auth/verify-email`, `/auth/forgot-password`, `/auth/reset-password`. Sessions are a JWT in an **httpOnly cookie** (`access_token`) plus a readable `csrf_token` cookie; state-changing requests must echo it in an `X-CSRF-Token` header (double-submit CSRF). `token_version` in the JWT enables revocation/logout-everywhere.
- **Email confirmation flow**: `POST /auth/register` creates an *unverified* account, emails a confirmation link, and returns **202** with **no session** (does not auto-log-in). `POST /auth/login` returns **403** for an unverified account. `POST /auth/verify-email` (public) validates the emailed token, marks the account verified, and **issues the session** — so following the link finishes registration and logs the user in. `users.email_verified` (migration `0010`) gates this; pre-existing accounts are grandfathered as verified.
- Backend: `app/presentation/api/auth.py` (public/private routers, `get_current_user` + `verify_csrf` guards) wired in `main.py` via `include_router(router, dependencies=[...])`; ports/use cases in `app/application` (`RegisterUserUseCase`, `VerifyEmailUseCase`, `AuthenticateUserUseCase`); `Argon2PasswordHasher` + `JwtTokenService` adapters.
- Email-confirmation adapters (ports in `app/application/ports.py`): `EmailSender` → `SmtpEmailSender` (stdlib SMTP) with `ConsoleEmailSender` dev fallback (used when `SMTP_HOST` is unset — just logs the link); `VerificationTokenService` → `JwtVerificationTokenService` (short-lived JWT carrying `purpose=email_verification`, not interchangeable with session tokens); `EmailValidator` → `DnsEmailValidator` (MX/deliverability via `email-validator`) or `AllowAllEmailValidator` when deliverability checks are off.
- **Password change**: `POST /auth/password` (private, needs auth + CSRF) takes `{current_password, new_password}`; verifies the current password (401 if wrong), replaces the hash and **bumps `token_version`** (logs out every *other* session), then re-issues a session cookie so the current device stays signed in. `ChangePasswordUseCase` + `UserRepository.update_password(user_id, password_hash, token_version)`; returns **204**.
- **Password reset (forgot password)**: `POST /auth/forgot-password` `{email}` emails a single-purpose reset link if the address is registered and always returns the same **202** (enumeration-resistant); rate-limited per `(IP, email)` reusing the login `RateLimiter` under a `forgot:` key namespace. `POST /auth/reset-password` `{token, new_password, confirm_password}` validates the token, sets the new hash, **bumps `token_version`** (kills old sessions), marks the email verified (the link proves ownership), and **issues a session** (auto-login) → **200**; an invalid/expired token → **400**. `RequestPasswordResetUseCase` + `ResetPasswordUseCase`; `PasswordResetTokenService` → `JwtPasswordResetTokenService` (`purpose=password_reset`, distinct from confirmation/session tokens).
- **Login throttling**: `POST /auth/login` is rate-limited per `(client IP, email)` — only wrong-credential attempts count toward the limit and a successful login clears the counter; over the limit returns **429** with a `Retry-After` header. `RateLimiter` port (`app/application/ports.py`, provider `get_rate_limiter`) + `InMemoryRateLimiter` adapter (fixed-window, **per-process**: single-worker correct; a multi-worker deploy needs a shared store — swap the adapter, the port stays). Env: `LOGIN_RATE_LIMIT_ATTEMPTS` (default 5), `LOGIN_RATE_LIMIT_WINDOW_MINUTES` (default 15).
- **Token refresh (rotation + reuse detection, RFC 9700)**: the **access token is short-lived** (`ACCESS_TOKEN_TTL_MINUTES`, default 15) and exchanged at **`POST /auth/refresh`** (public; protected by the httpOnly + SameSite refresh cookie, so no CSRF guard) for a fresh one. Every session-issuing route (login, verify-email, reset-password, change-password) also sets a **refresh cookie** (`refresh_token`, httpOnly, `path=/auth`, lifetime `REFRESH_TOKEN_TTL_DAYS` default 14). Each refresh **rotates** the token; replaying an already-consumed token is **reuse → the whole family is revoked** → 401. Logout revokes the current device's family; password change/reset revoke all the user's families. `RefreshTokenService` (`app/application/refresh_tokens.py`) + `RefreshTokenRepository` → `PostgresRefreshTokenRepository` (SHA-256 hash-only storage, migration `0011_refresh_tokens`); provider `get_refresh_token_service`.
- Frontend: `core/services/auth.service.ts` (`changePassword` → `POST /auth/password`), `core/interceptors/auth.interceptor.ts` (sends cookies + CSRF header; on a 401 rotates via `/auth/refresh` — a single shared in-flight `AuthService.refreshSession()` — and retries the request once, else clears the session and redirects to /login), `core/guards/auth.guard.ts`. Auth pages in `features/auth/{login,register,change-password,forgot-password,reset-password}` (standalone, signals, Material): login surfaces the **429** throttle message and links to `forgot-password`; `change-password` is a guarded route reached from the toolbar and reuses register's `passwordsMatch` validator to confirm the new password; `forgot-password` (enter email → neutral "check your email") and `reset-password` (reads `?token=`, new password + retype) are public routes (`auth.service.ts` `requestPasswordReset` / `resetPassword`). (Note: the verify-email page / "check your email" UX is not yet built on the frontend.)
- Required env: `JWT_SECRET` (override the dev default in prod). Cross-site prod also needs `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none`. Email confirmation: `APP_BASE_URL` (frontend base for the link, default `http://localhost:4200`), `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_USE_TLS`/`EMAIL_FROM` (SMTP delivery; without `SMTP_HOST` the console fallback logs the link), `EMAIL_VERIFICATION_TTL_HOURS` (default 24), `PASSWORD_RESET_TTL_HOURS` (default 1), `EMAIL_CHECK_DELIVERABILITY` (default false; enable MX checks in prod).

## Multi-tenancy
- The app is multi-tenant: per-user profile, selected model, usage, and budget. Routes resolve `user: User = Depends(get_current_user)` and pass `user.id` into use cases; app-owned tables (`user_profile`, `selected_model`, `model_usage`, `budget`) carry a `user_id` FK (migrations 0006–0009). `AiScoringContext` resolves each user's model and caches use-cases per-model.
- Per-user budgets are enforced from the user's own recorded token usage priced by `HardcodedModelPricingRegistry` (`TokenAccountingSpendProvider`), composed with a global org-spend backstop for AI matches.
- Note: repo constructors `create_all` their table but do NOT add columns to a pre-existing table — apply Alembic migrations (or rebuild) when a column is added.

## Required Skills

 /tdd
 /clean-ddd-hexagonal
 /clean-code
 /fastapi
 /angular-component


## Code Style
 - Follow Clean Code principles
 - Follow Clean Architecture principles
 - Follow TDD

## Workflow
1. Write a plan and confirm with user before coding.
2. Write tests first (TDD)
3. Implement the feature
4. Run pytest and confirm passing
5. Update this CLAUDE.md if new patterns emerge

