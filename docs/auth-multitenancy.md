# Auth & Multi-Tenancy — Implementation Report

Status as of 2026-06-24. **Phase 1 (authentication) and Phase 2 (multi-tenancy) are complete.**
Backend: **441 tests pass, `uv run ruff check` clean, the app boots.** Login/register verified manually by the user.

> **Resume-here TL;DR**
> 1. **Before running locally:** your dev DB's `budget` table still lacks `user_id`. Drop it (create_all rebuilds it on boot) or run migrations. See [Action required](#-action-required-database).
> 2. The app is now fully multi-tenant: each user has their own profile, selected model, usage, and budget.
> 3. Best next tasks: request-scoped usage fix, login rate-limiting, token refresh. See [What could be done next](#what-could-be-done-next).

---

## 1. What was implemented

### Phase 1 — Authentication (gate the whole app)
Session auth via an **httpOnly JWT cookie** + **double-submit CSRF**, **open** self-serve registration, **argon2** password hashing, **token_version** for revocation/logout-everywhere. Registration auto-logs-in.

**Backend**
- Domain: `app/domain/auth.py` (`User`), errors in `app/domain/errors.py` (`EmailAlreadyRegisteredError`, `InvalidCredentialsError`, `AuthenticationError`).
- Application: ports `UserRepository` / `PasswordHasher` / `TokenService` / `TokenClaims` (`app/application/ports.py`); use cases `RegisterUserUseCase`, `AuthenticateUserUseCase` (`app/application/auth_use_cases.py`).
- Infrastructure: `Argon2PasswordHasher`, `JwtTokenService` (PyJWT HS256, 7-day, `sub`+`ver`+`exp`), `PostgresUserRepository`, `UserRow` in `orm_models.py`. Migration `alembic/versions/0005_users.py`.
- Presentation: `app/presentation/api/auth.py` — `public_router` (`GET /health`, `POST /auth/register`, `POST /auth/login`), `private_router` (`POST /auth/logout`, `GET /auth/me`), the `get_current_user` and `verify_csrf` guards, `CookieSettings`, cookie set/clear helpers. Schemas in `schemas.py`.
- Wiring: `main.py` includes the app router with `dependencies=[Depends(get_current_user), Depends(verify_csrf)]` (secure-by-default). Config: `JWT_SECRET`, `SESSION_TTL_DAYS`, `COOKIE_SECURE`, `COOKIE_SAMESITE` in `app/config.py`.

**Frontend** (`frontend/src/app/`)
- `core/models/auth.model.ts`, `core/services/auth.service.ts` (signals, `loadCurrentUser` hydrates from cookie), `core/interceptors/auth.interceptor.ts` (`withCredentials` + `X-CSRF-Token` + 401→/login), `core/guards/auth.guard.ts`.
- `features/auth/login/*`, `features/auth/register/*` (standalone Material components).
- `app.config.ts` (registers the interceptor), `app.routes.ts` (login/register routes + guard on feature routes), `app.ts`/`app.html` (shows email + sign-out; nav hidden when logged out).

**Dependencies added:** `pyjwt`, `argon2-cffi`, `email-validator`.

### Phase 2 — Multi-tenancy (per-user data)
Each app-owned table gained a `user_id` FK; routes resolve `user: User = Depends(get_current_user)` and pass `user.id` into use cases. Delivered in four vertical slices, each its own migration:

| Slice | Delivers | Migration | Key files |
|---|---|---|---|
| **A** | Per-user **profile** | `0006_user_profile_user_id` | `postgres_user_profile_repository.py`, `Save/GetUserProfileUseCase` |
| **B** | Per-user **selected model** | `0007_selected_model_user_id` | `ai_scoring_context.py`, `postgres_selected_model_repository.py` |
| **C** | Per-user **usage** | `0008_model_usage_user_id` | `MatchOffersWithAiUseCase._persist_usage`, `postgres_model_usage_repository.py` |
| **D** | Per-user **token-accounting budget** | `0009_budget_user_id` | `budget_service.py`, `model_pricing_registry.py`, `token_accounting_spend_provider.py`, `org_spend_backstop.py`, `composite_budget_status_reader.py` |

Notable design points:
- **B:** `AiScoringContext` resolves each user's model (`active_model_for` / `use_case_for` / `select_model(user_id, …)`) and caches built use-cases **per model** (shared across users). `main._ai_use_case_for_request` resolves the AI-match use case for the calling user. The old global `get_current_model` wiring was removed.
- **C:** Usage persistence was moved **out of the scorer's tracker path into the match use case** (where `user_id` is known): the scorer records to an in-process tracker; `MatchOffersWithAiUseCase._persist_usage(user_id)` drains it, stamps the user, and saves via `ModelUsageRepository`. `GetModelUsageSummaryUseCase` is now DB-only per-user (the org-level external usage provider was dropped — it can't be attributed per user).
- **D:** Per-user budgets are enforced from the user's own recorded tokens × price (`TokenAccountingSpendProvider` + `HardcodedModelPricingRegistry`). The org-level spend guard is kept as a **global backstop** (`OrgSpendBackstop`, active only with an admin key) and composed with the user budget via `CompositeBudgetStatusReader` — this composite is the gate for `/offers/match/ai`. The org `SpendProvider` port was left unchanged; a new `UserSpendProvider` port was introduced for token accounting.

---

## 2. How the multi-tenant pattern works (for adding the next per-user resource)
1. **Port** method takes `user_id` (e.g. `Repo.load(user_id)`).
2. **Use case** `execute(user_id, …)` threads it through.
3. **Route** adds `user: User = Depends(get_current_user)` and passes `user.id`.
4. **ORM row** gets a `user_id` `String(36)` FK to `users` (`ondelete="CASCADE"`), unique if 1-per-user.
5. **Postgres repo** queries `where(Row.user_id == user_id)`.
6. **Migration** `000N_*`: add column nullable → backfill (to earliest user, or delete) → set NOT NULL + unique + FK.
7. **Tests:** fake repo keyed by user_id; route-test harness already overrides `get_current_user` to a fixed fake user (`_build_client` in `tests/api/test_routes.py`); **integration test** must drop+recreate its table with the new schema and seed FK users (see `tests/integration/test_postgres_*` for the template).

---

## 3. ⚠️ Action required (database)
Repo constructors call `create_all` for their table but **do not add columns to a table that already exists**. During the test suite, integration tests rebuild `user_profile` / `selected_model` / `model_usage` with the new schema, but **nothing rebuilds `budget`**. So a dev DB that predates this work has a stale `budget` table (no `user_id`), and the first authenticated `/usage/*` or `/offers/match/ai` request will raise `column budget.user_id does not exist`.

**Fix (pick one):**
- Drop the `budget` table and restart the API (create_all rebuilds it with `user_id`), **or**
- Apply migrations on a clean DB: `uv run alembic upgrade head` (migrations `0005`–`0009`).

Note: mixing create_all-managed schemas with Alembic can conflict (create_all may have pre-created tables Alembic then tries to create/alter). On a fresh DB, migrations are the source of truth.

---

## 4. Known caveats / tech debt
- **Usage attribution under concurrency:** the in-memory usage tracker is process-shared, so two concurrent same-process AI matches can mis-attribute tokens (and thus per-user budget). Pre-existing posture; the budget is best-effort. Proper fix: request-scoped usage (a `contextvars.ContextVar` tracker, or carry usage on the returned `MatchScore` and have the use case collect it — note the `CachingAiScorer` must NOT cache usage so a cache hit reports $0).
- **Pricing is approximate:** `HardcodedModelPricingRegistry` uses public list prices via longest-prefix match; unknown models count as **$0** (spend is a lower bound).
- **`usage_since` time-filter** has unit coverage but no dedicated DB integration test (same query builder as `get_summary`, which is integration-tested).
- **`.env.example`** could not be updated (permission-protected). Add: `JWT_SECRET`, `SESSION_TTL_DAYS`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `AI_MATCH_CONCURRENCY`.
- **No login rate-limiting** (deferred from Phase 1 — needs a shared store for multi-worker correctness).

---

## 5. What could be done next
Roughly prioritized:
1. **(do first) Reconcile the dev DB** — drop `budget` (or migrate) so the app runs locally. See §3.
2. **Request-scoped usage** — fixes the concurrency mis-attribution in §4; makes per-user budgets exact.
3. **Login rate-limiting / brute-force protection** — per-IP/email attempt throttling (shared store).
4. **Token refresh** — currently a single 7-day cookie; add short access + long refresh cookies with `POST /auth/refresh` + rotation.
5. **Password change / reset** — wire `token_version` bump to invalidate sessions on change.
6. **Admin / org-wide view** — an aggregate usage & budget dashboard (the org-level external usage provider still exists, just no longer used per-user).
7. **`usage_since` integration test** + tighter pricing config (move prices to config / refresh source).
8. **CSRF/cookie hardening for prod** — verify `SameSite=None; Secure` over HTTPS for a cross-site deployment.

---

## 6. How to run & verify
```bash
# Backend
uv run pytest            # 441 tests (incl. real-DB integration tests, skipped if DB unreachable)
uv run ruff check
uv run alembic upgrade head   # apply migrations 0005–0009 on a clean DB
uv run python main.py    # http://localhost:8000

# Frontend
cd frontend && npm install && npm start   # http://localhost:4200
cd frontend && npm run build              # type-checks templates
```
Auth smoke (in-process, no server): `TestClient(main.app)` → `GET /health` 200, `GET /auth/me` 401, `POST /auth/register` 201 sets `access_token`+`csrf_token` cookies.

---

## 7. Decisions locked with the user (so you don't re-ask)
Multi-tenant · httpOnly cookie (not Bearer) · open registration · per-user **token-accounting** budget + org backstop · single 7-day session cookie · `token_version` revocation · UUID user PKs · backfill existing rows to the earliest user.
