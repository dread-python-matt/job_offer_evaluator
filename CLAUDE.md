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
- Required env: `JWT_SECRET` (override the dev default in prod). `API_KEY_ENCRYPTION_KEY` (Fernet key; override the public dev default in prod — production startup refuses the dev default via `config_validation.py`; rotating it makes stored keys undecryptable). Cross-site prod also needs `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none`. Email confirmation: `APP_BASE_URL` (frontend base for the link, default `http://localhost:4200`), `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_USE_TLS`/`EMAIL_FROM` (SMTP delivery; without `SMTP_HOST` the console fallback logs the link), `EMAIL_VERIFICATION_TTL_HOURS` (default 24), `PASSWORD_RESET_TTL_HOURS` (default 1), `EMAIL_CHECK_DELIVERABILITY` (default false; enable MX checks in prod).

## User-supplied provider API keys (each with its own budget)
- Users register their **own** LLM provider API keys (start set: **OpenAI**, **Google**), one per provider. Each key carries its **own spend budget**, which **gates AI matches** (per-provider spend vs that key's limit). **Fully built end-to-end (backend + Angular UI), TDD-green.**
- **Hashing vs encryption — the key design point**: an API key must be *replayed* to the provider, so it is **symmetrically encrypted** (recoverable), never one-way hashed like a password. `KeyCipher` port → `FernetKeyCipher` (Fernet = AES-128-CBC + HMAC; `cryptography` dep), secret from env `API_KEY_ENCRYPTION_KEY` (lives outside the DB). Only **ciphertext** + a non-secret masked `key_hint` (`sk-…1234`, via `app/domain/api_keys.py:mask_key`) are stored — never plaintext. Contrast: refresh tokens are SHA-256 **hash-only** because they're verified, not replayed.
- **Validation before storing**: a new key is checked against the provider by **listing models** (free — no tokens spent) with it; a **400/401/403** → reject (OpenAI uses 401/403; **Gemini returns 400** "Please pass a valid API key" for a bad key — must be treated as rejection, else it leaks as a 500). Other statuses (429/5xx/network) bubble as transient. `ApiKeyValidator` port → `ModelListingApiKeyValidator` (reuses `OpenAI/GeminiAvailableModelsProvider` via an injected `provider_factory`); rejection raises `InvalidApiKeyError` → 400.
- **Storage**: one row per `(user_id, api_provider)`, `UNIQUE(user_id, api_provider)` (table `user_api_key`, migration `0012_user_api_key`, `UserApiKeyRow`). Columns: ciphertext, hint, `limit_usd`, `tracking_since`, `created_at`. **Usage is *derived*, not stored**: spend on that provider since the key's anchor, from recorded `model_usage` priced by the registry (`UserProviderSpendProvider` → `TokenAccountingProviderSpendProvider`, filtered by `company`). `api_provider` ids (`openai`/`google`) map to the existing `company` labels (`OpenAI`/`Google`) via `app/domain/api_providers.py`.
- **Endpoints** (private, CSRF-guarded): `GET /api-keys/providers` (the pickable list), `GET /api-keys` (list of `{api_provider, key_hint, limit_usd, used_usd}`), `POST /api-keys` `{api_provider, key, limit_usd}` → **201** (`400` unsupported/rejected key, `409` duplicate provider), `PATCH /api-keys/{api_provider}` `{limit_usd}` (budget only; `404` if absent), `DELETE /api-keys/{api_provider}` → **204**. Ports in `app/application/ports.py` (`ApiKeyRepository` → `PostgresApiKeyRepository`); use cases `AddApiKeyUseCase`/`ListApiKeysUseCase`/`SetApiKeyBudgetUseCase`/`DeleteApiKeyUseCase` in `app/application/api_key_use_cases.py`.
- **Require own key (no env fallback) — wired in Phase 2**: AI scoring resolves the calling user's own key for the model's provider via `UserApiKeyResolver` (decrypts on demand) → `build_chat_model_with_key` (single-key client). No key for that provider → `MissingProviderApiKeyError`, surfaced as **400** by a handler in `error_handlers.py` (it's raised while resolving the AI-match *dependency*, so it can't be caught in the route body). `AiScoringContext` now builds/caches use-cases **per `(user_id, model)`** (a use case is bound to one user's key — no cross-user sharing); `default_model=""` (no global default — each user selects from their own keys).
- **Per-user model picker**: `GET /config/models` and `PUT /config/model` list/validate against the user's **own** keys only — `ListAvailableModelsUseCase.execute(user_id)` → `UserAvailableModelsProvider` → `KeyedUserAvailableModelsProvider` (lists each of the user's providers with their decrypted key; a failing/revoked key is skipped, not fatal) wrapped in `CachingUserAvailableModelsProvider` (per-user TTL cache). A user with no keys → empty picker → AI match disabled.
- **Per-key budget enforcement**: an AI match is gated by the **model's provider key budget** (`ApiKeyBudgetStatusReader`: that key's `limit_usd` vs the user's derived spend on that provider) plus the global org-spend backstop — built per `(user, model)` in `_build_ai_use_case`. This **replaced** the old global per-user `BudgetService` gate (the `/usage/limit|cost|reset` endpoints + `budget` table still exist but no longer gate matches and are no longer surfaced in the UI). Exceeded → **402**.
- **Org spend readout (admin key)**: `GET /usage/org-spend` returns the organization's **actual** USD billed today (real money, from OpenAI's admin costs API via `OPENAI_ADMIN_KEY`) — `GetOrgSpendUseCase` over the `SpendProvider` (`OpenAISpendProvider`), today's UTC-day window. **null** when no admin key / `LLM_PROVIDER!=openai` / unavailable. This is org-wide (not per-user) — distinct from the token-accounted per-key usage. Shown as a card on the model-usage page (`ApiService.getOrgSpend`). The same `SpendProvider` still backs the `OrgSpendBackstop` match gate.
- **Frontend** (folded into the model-usage page per the user): `features/api-keys/` standalone component (`<app-api-keys>`, signals, Material) — lists keys (company, masked hint, per-key budget bar + derived usage), add-key form (provider picker from `GET /api-keys/providers`, password-masked key field, budget; surfaces the 400 "rejected"/409 "duplicate" detail), per-key budget `PATCH`, delete; emits `(changed)` so the host reloads the per-user model picker after the first key is added. The old global "API spend budget" card was removed from `model-usage`. `ApiService`: `getApiKeyProviders/getApiKeys/addApiKey/updateApiKeyBudget/deleteApiKey`.
- **Rotating** a key = delete then re-add; changing **only** the budget = `PATCH`.

## Multi-tenancy
- The app is multi-tenant: per-user profile, selected model, usage, and budget. Routes resolve `user: User = Depends(get_current_user)` and pass `user.id` into use cases; app-owned tables (`user_profile`, `selected_model`, `model_usage`, `budget`) carry a `user_id` FK (migrations 0006–0009). `AiScoringContext` resolves each user's model and caches use-cases **per `(user_id, model)`** (each is bound to that user's own provider key — see the API-keys section).
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

