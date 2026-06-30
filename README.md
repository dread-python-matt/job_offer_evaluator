# Job Offers Evaluator

Matches scraped job offers to a user's profile and (optionally) scores fit with an LLM.
The backend is a **FastAPI JSON API**; the frontend is a **standalone Angular app** that
talks to it over HTTP (CORS, cookie session) — there is no shared process. The app is
**multi-tenant**: every user has their own profile, selected model, usage, and budget.

> **For agents:** this file is the map. The dependency rule is *inward only*
> (`presentation`/`infrastructure` → `application` → `domain`). Business logic lives in
> `app/domain` and `app/infrastructure`; `main.py` is the composition root that wires every
> port to a concrete adapter via FastAPI `dependency_overrides`. Start there and in
> `app/presentation/api/routes.py`.

---

## What it does

1. A **user profile** (summary, skills with 1–5 ratings, projects, experience) is saved per
   user as a JSON document in Postgres. It can also be sent inline as the `candidate` of a
   match request.
2. **Job offers** live in a Postgres `offers` table owned by a separate scraper project —
   this app only **reads** it (plus the scraper's `salaries` / `normalized_salary` tables).
3. Candidate offers are fetched with the request's **structural filters pushed into SQL**
   (`OfferRepository.candidate_offers` — location, min net salary, level, expired), so the
   whole table is never materialized. A **`FilterChain`** (composite of `OfferFilter`s, ANDed)
   then applies exact filter semantics — including candidate skill overlap — before the
   expensive scoring runs.
4. Each surviving offer is scored by an **`OfferScorer`** that returns a **`MatchScore`** —
   named, weighted `ScoreComponent`s whose weighted average is `overall_score`.
   - **`SkillBasedScorer`** (deterministic): rating-weighted tech-stack overlap, no I/O.
   - **`LLMScoringStrategy`** (AI): combines the skill score (weight 4) with a model-rated
     `description` score (weight 1), and attaches an `AiInsight` (rate, pros, cons, reason).
5. Results are filtered by a minimum score and returned **sorted** (by score, recency, or
   net salary).

There is also a **net-salary calculator** (Polish 2026 tax/ZUS rules, per contract type) used
both for the `/salary/calculate` endpoint and to sort/filter offers by estimated take-home pay.

---

## Tech stack

| Area | Choices |
|---|---|
| Backend language | Python 3.13 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Web framework | FastAPI + Uvicorn, Pydantic v2 schemas |
| Persistence | PostgreSQL via SQLAlchemy 2.x + psycopg 3; **Alembic** migrations |
| LLM | OpenAI **Agents SDK** (`openai-agents`); supports OpenAI **and** Google Gemini models |
| Auth | PyJWT (HS256 access + rotating refresh tokens), argon2-cffi (hashing), email-validator, SMTP (stdlib) for confirm/reset email |
| Lint / test | ruff, pytest (+ pytest-cov) |
| Frontend | Angular 22 (standalone components, signals), Angular Material 22 |
| Frontend test | Vitest 4 (`ng test`), Prettier, TypeScript 6, npm |

---

## Repository layout

```
.
├── app/                  # Backend (Clean Architecture / Hexagonal) — see below
├── main.py               # Composition root: builds adapters, wires DI, creates FastAPI app
├── alembic/              # DB migrations (app-owned tables only)
├── tests/                # unit / integration / api  (pytest)
├── frontend/             # Angular SPA (separate process)
├── DATA/user_profile.md  # Legacy seed profile (used only by the test-only Markdown adapter)
├── docs/                 # Design/implementation reports (e.g. auth-multitenancy.md)
├── docker-compose.yml    # Postgres (+ optional api) for local dev
├── Dockerfile            # Backend image: runs `alembic upgrade head` then the API
├── pyproject.toml        # Backend deps (uv) + dev group
└── CLAUDE.md             # Agent/contributor instructions (skills, workflow, conventions)
```

---

## Backend architecture

Dependencies point **inward**: `presentation` and `infrastructure` depend on `application`,
which depends on `domain`. The domain has no knowledge of FastAPI, Postgres, or the OpenAI SDK.
Ports (abstract interfaces) are declared in `domain` and `application`; concrete adapters
(anything with I/O or a real algorithm) live in `infrastructure`. `main.py` is the only place
that knows every concrete type.

```
app/
├── config.py                 # Reads env (.env) into module constants — see Configuration
├── observability/            # Cross-cutting: structured logging setup + request-id contextvar
│
├── domain/                   # Pure: entities, value objects, ports, algorithms (no frameworks)
│   ├── entities.py           #   Skill, Project, Experience, UserProfile, Offer, Salary
│   ├── auth.py               #   User (id, email, password_hash, token_version, email_verified)
│   ├── budget.py             #   BudgetSettings, BudgetStatus(.exceeded)
│   ├── scoring.py            #   MatchScore, ScoreComponent, MatchedOffer, AiInsight, OfferScorer (port)
│   ├── skills.py             #   CanonicalSkill + SkillNormalizer (port) — one concept per skill
│   ├── filters.py            #   MatchCriteria, OfferBrowseFilters, OfferFilter (port), FilterChain, predicates
│   ├── sorting.py            #   Sort keys/types: sort_offers, sort_matched_offers
│   ├── salary_calculator.py  #   Net PL salary (B2B / employment / civil strategies) + net helpers
│   ├── errors.py             #   Domain errors (Auth, BudgetExceeded, AiScoring, CostUnavailable, …)
│   └── matching.py           #   Back-compat shim re-exporting the split modules above
│
├── application/              # Use cases + ports (orchestration; depends only on domain)
│   ├── ports.py              #   ALL repository/service ports + their DTOs (read this first)
│   ├── use_cases.py          #   Profile, offers, deterministic match, AI match, usage summary, salary
│   ├── auth_use_cases.py     #   Register, Authenticate, VerifyEmail, ChangePassword, Request/ResetPassword
│   ├── refresh_tokens.py     #   RefreshTokenService + RefreshTokenRepository port (rotation, reuse detection)
│   ├── budget_service.py     #   BudgetService (per-user limit + token-accounted spend, cached)
│   ├── skill_canonicalization.py # Rewrite a profile/offer's skills → canonical concepts (matching boundary)
│   └── ai_scoring_context.py #   AiScoringContext: resolves a user's model → AI use case (cached per model)
│
├── infrastructure/           # Adapters implementing the ports (the only layer with I/O)
│   ├── db.py, orm_models.py  #   Engine builder (tunable connection pool) + SQLAlchemy ORM rows for app-owned + scraper tables
│   ├── postgres_*_repository.py   # user, user_profile, selected_model, model_usage, ai_score, budget, offer
│   ├── markdown_profile_repository.py  # Legacy profile adapter (test-only; not wired in main.py)
│   ├── scoring_strategies.py # SkillBasedScorer (deterministic); skill_utils.py = evidence-aware weighting
│   ├── alias_map_skill_normalizer.py, data/skill_aliases.json  # Deterministic skill canonicalization + seed map
│   ├── llm_scoring_strategy.py     # LLMScoringStrategy (Agents SDK, retries/backoff, usage tracking)
│   ├── caching_ai_scorer.py  #   Content-addressed AI-score cache wrapper (skips re-paying for repeats)
│   ├── translation_agents.py #   Polish→English agent run on the offer description before scoring
│   ├── agent_models.py, *_client.py, llm_provider_factory.py  # Per-model chat client + provider wiring
│   ├── *_available_models_provider.py  # List models (Gemini/OpenAI), composite + caching
│   ├── *_model_usage_tracker.py, *_usage_provider.py          # Record/aggregate token usage
│   ├── model_pricing_registry.py, token_accounting_spend_provider.py  # Price usage → per-user spend
│   ├── org_spend_backstop.py, openai_spend_provider.py        # Global org $ guard (OpenAI admin key only)
│   ├── composite_budget_status_reader.py   # Compose user budget + org backstop into one gate
│   ├── model_limits_registry.py, offer_filters.py            # Rate-limit metadata; concrete filters
│   ├── argon2_password_hasher.py, jwt_token_service.py        # Password hashing + access-token JWTs
│   ├── jwt_verification_token_service.py, jwt_password_reset_token_service.py  # Purpose-scoped email/reset JWTs
│   ├── smtp_email_sender.py, console_email_sender.py, email_validators.py      # EmailSender (SMTP/console) + deliverability
│   ├── in_memory_rate_limiter.py, redis_rate_limiter.py, postgres_refresh_token_repository.py  # Login/forgot throttle (memory or Redis); hashed refresh-token store
│   └── llm_logging.py, llm_utils.py                           # Debug logging; company_from_model, etc.
│
└── presentation/api/         # FastAPI entry points
    ├── routes.py             #   App router (profile, offers, match, salary, config/model, usage)
    ├── auth.py               #   public_router + private_router, get_current_user/verify_csrf guards, cookies
    ├── schemas.py            #   ALL Pydantic request/response models (the wire contract)
    ├── request_logging.py    #   ASGI middleware: per-request correlation id + structured access log
    ├── security_headers.py   #   ASGI middleware: defense-in-depth response headers
    └── error_handlers.py     #   Catch-all → generic 500 (never leak internals)
```

### Key cross-cutting patterns

- **DI by override.** Routers declare `get_*_use_case()` providers that `raise
  NotImplementedError`; `main.py` replaces each via `app.dependency_overrides[...]`. Tests do
  the same with fakes (`tests/fakes.py`).
- **Per-user model selection.** `AiScoringContext` reads a user's chosen model from
  `SelectedModelRepository` (default = first advertised model), builds the AI use case **once
  per model**, and shares it across users on that model. Switches survive restarts and are
  consistent across workers because the selection is persisted.
- **Scoring is a port.** Both scorers implement `OfferScorer.score`/`score_async`; the AI match
  use case scores the top-ranked candidates concurrently (`asyncio`, bounded by
  `AI_MATCH_CONCURRENCY`) and is best-effort (a failed offer is dropped unless *all* fail). The
  AI match route is **async** and awaits scoring (`execute_async`), so the slow LLM round-trips
  don't pin a thread-pool worker for the whole request.
- **Skill normalization.** Before any skill comparison, raw tokens (candidate skills + offer
  tech stacks) are collapsed to canonical concepts by a `SkillNormalizer` (deterministic alias
  map + case/diacritic/separator folding) at the matching boundary, on scoring-only copies — so
  "JS"/"JavaScript", "k8s"/"Kubernetes" and PL/EN variants match while the originals stay intact
  for display. Unknown tokens are logged on `app.skills` to grow the map, and scoring weights
  **evidenced** skills (used in a real project/experience) above self-claimed ratings. See
  `docs/skills-normalization.md`.

---

## Authentication & multi-tenancy

Session auth via a short-lived **httpOnly JWT access cookie** + a rotating **refresh token**,
with **double-submit CSRF**, **argon2** password hashing, and **email-confirmed** self-serve
registration. `token_version` (in the JWT) gives instant revocation / logout-everywhere.

- **Cookies:** `access_token` (httpOnly JWT `sub`+`ver`+`exp`, short-lived —
  `ACCESS_TOKEN_TTL_MINUTES`), `refresh_token` (httpOnly, `path=/auth`, long-lived —
  `REFRESH_TOKEN_TTL_DAYS`), and `csrf_token` (readable by the SPA). State-changing requests
  must echo the CSRF value in an `X-CSRF-Token` header.
- **Guards:** `get_current_user` resolves the user from the access cookie (401 if missing/
  invalid/expired/revoked); `verify_csrf` enforces the header match on unsafe methods. Both are
  applied app-wide in `main.py` via `include_router(..., dependencies=[...])`.
- **Public routes** (no guard): `GET /health` and the `/auth` entry points `register`,
  `verify-email`, `login`, `forgot-password`, `reset-password`, `refresh`. Everything else is gated.
- **Registration is email-confirmed.** `register` creates an *unverified* account, emails a
  confirmation link, and issues **no** session (202). `login` returns **403** until the account
  is verified; following the emailed link (`verify-email`) marks it verified and logs the user
  in. Pre-existing accounts were grandfathered as verified (migration `0010`).
- **Password reset & change.** `forgot-password` emails a single-purpose reset link and always
  returns the same **202** (enumeration-resistant); `reset-password` sets the new password,
  revokes the user's other sessions, and logs them in. `POST /auth/password` (authenticated)
  verifies the current password and bumps `token_version` to sign out other devices.
- **Token refresh (rotation + reuse detection, RFC 9700).** Access tokens are short-lived;
  `POST /auth/refresh` swaps the refresh cookie for a fresh access token and **rotates** the
  refresh token. Replaying a consumed token is treated as theft → the whole token *family* is
  revoked → 401. `logout` revokes the current family; password change/reset revoke all of the
  user's families. Refresh tokens are stored **hashed** (SHA-256), never in plaintext
  (`refresh_tokens`, migration `0011`).
- **Brute-force throttle.** `login` is rate-limited per `(client IP, email)` — only wrong
  attempts count and a success clears the counter; over the limit → **429** + `Retry-After`.
  `forgot-password` is throttled the same way. The `RateLimiter` is pluggable: in-memory
  per-process by default (single-worker correct), or a shared **Redis** store for multi-worker
  deployments (`RATE_LIMITER_BACKEND=redis`).
- **Email delivery.** Confirmation/reset emails go through an `EmailSender` port. With no
  `SMTP_HOST` configured the app uses a **console fallback that only logs the link** — see
  [Email delivery](#email-delivery) for setup and the `app/scripts/verify_link.py` helper.
- **Multi-tenant data.** App-owned tables carry a `user_id` FK (`ondelete="CASCADE"`); routes
  resolve `user: User = Depends(get_current_user)` and pass `user.id` into the use case, which
  threads it to the repository. Pattern to add a new per-user resource: port method takes
  `user_id` → use case threads it → route passes `user.id` → ORM row gets a `user_id` FK →
  repo filters on it → add a migration. (See `docs/auth-multitenancy.md`.)

Required env in production: **`JWT_SECRET`** (override the dev default). Cross-site HTTPS
deployments also need `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none`. To send real email
(not just log it), set the `SMTP_*` / `EMAIL_FROM` / `APP_BASE_URL` vars.

---

## AI matching & cost control

- **Providers.** LLM access goes through the OpenAI **Agents SDK**. `LLM_PROVIDER`
  (`gemini` default, or `openai`) selects only the *org-level* usage/cost wiring; the **scoring
  model is chosen per user** via the API and built with its own client, so selection never
  mutates global SDK state. Available models are listed from whichever provider keys are set
  (Gemini and/or OpenAI), filtered to **scoring-capable** models (structured-output-capable
  OpenAI models; text-generation Gemini models only — embeddings, image/audio/TTS, live,
  computer-use and robotics models are excluded), then cached.
- **Pipeline.** For an AI match: fetch candidates (filters pushed into SQL) → apply the
  `FilterChain` → rank with `SkillBasedScorer` → send the top `offers_to_score` to the LLM →
  (optionally) translate the offer description to English → score → cache the result
  (content-addressed by model+candidate+offer) → record token usage. Note each scored offer is
  **two** model calls when translation runs (translate + score), so a match issues up to
  `2 × offers_to_score` requests.
- **Rate limiting (Gemini).** Google's free tier is RPM/RPD-capped **per project + model**, so a
  burst of scoring calls easily trips `429`. Google calls are paced client-side to the selected
  model's real RPM (from the model-limits registry; `GOOGLE_RPM_LIMIT` is the fallback/kill-switch)
  with no initial over-burst, and the scorer honors a `429`/`503` `Retry-After`. OpenAI is not
  paced. A daily-RPD exhaustion still surfaces as `429` until it resets (midnight Pacific).
- **Budgets (per user, best-effort).** Before scoring, the AI match checks a budget gate
  (`CompositeBudgetStatusReader`) that combines:
  1. the user's **token-accounting budget** — their recorded usage priced by
     `HardcodedModelPricingRegistry` (`TokenAccountingSpendProvider` + `BudgetService`), and
  2. a global **org-spend backstop** (`OrgSpendBackstop`) protecting the owner's real provider
     bill — **active only when an OpenAI admin key is configured**.
  If any budget is exceeded → `BudgetExceededError` → **HTTP 402**. If spend can't be read,
  the match proceeds (fail-open) unless `BUDGET_FAIL_CLOSED=true`, which raises **503**.
  Caveats: usage attribution can drift under concurrent same-process matches; unknown-model
  pricing counts as $0 (spend is a lower bound).
- **Usage accuracy (OpenAI).** Local accounting prices each call's reported `usage`; for OpenAI
  it reads `input_tokens_details.cached_tokens` and prices prompt-cache hits at the model's
  discounted cached rate (the scoring prompt's constant instructions + candidate profile repeat
  across offers, so cache hits are common and full-input pricing would overstate cost). Gemini is
  unchanged (no cached rate → priced at the normal input rate). When an **`OPENAI_ADMIN_KEY`** is
  set, `/usage/org-spend` and `/usage/org-usage` expose the provider's *authoritative* org-wide
  real-$ cost and per-model token usage from OpenAI's admin Usage/Costs API — queried per-model
  (`group_by=["model"]`), in daily buckets, and paginated to completion.

---

## Data model

**App-owned** (created/migrated by this project; per-user tables carry a `user_id` FK):
`users`, `user_profile`, `selected_model`, `model_usage`, `budget`, `ai_score`,
`refresh_tokens`, `user_api_key`. (`ai_score` is a global content-addressed cache;
`refresh_tokens` holds SHA-256 hashes only; `user_api_key` holds encrypted provider keys —
never raw tokens or plaintext keys.)

**Scraper-owned, read-only** (do **not** migrate here): `offers`, `salaries`,
`normalized_salary`.

Migrations live in `alembic/versions/` (`0001`–`0014`): baseline → app tables (`user_profile`,
`ai_score`, `selected_model`, `users`) → per-user `user_id` FKs (`0006`–`0009`) →
`users.email_verified` (`0010`) → `refresh_tokens` (`0011`) → `user_api_key` (`0012`) →
`model_usage (user_id, created_at)` index (`0013`) → `model_usage.estimated` (`0014`).

> ⚠️ **Schema caveat.** Each Postgres repo calls `create_all` for *its* table but does **not**
> add columns to a table that already exists. On a pre-existing dev DB, apply migrations
> (`uv run alembic upgrade head`) or drop the stale table so `create_all` rebuilds it. On a
> fresh DB, **migrations are the source of truth** — don't mix create_all with Alembic.

---

## API reference

All paths are JSON. **Auth** = requires the session cookie; state-changing methods also require
the `X-CSRF-Token` header.

| Method | Path | Auth | Description |
|---|---|:--:|---|
| GET  | `/health` | – | Liveness probe (`{"status":"ok"}`) |
| POST | `/auth/register` | – | Create an **unverified** account + email a confirmation link; no session (202; 409 if email taken; 422 if undeliverable) |
| POST | `/auth/verify-email` | – | Confirm the email from the emailed token → verify + log in (200; 400 if invalid/expired) |
| POST | `/auth/login` | – | Log in, set session + refresh cookies (401 bad creds; 403 unverified; 429 throttled) |
| POST | `/auth/forgot-password` | – | Email a reset link if the address exists; always 202 (enumeration-resistant; 429 throttled) |
| POST | `/auth/reset-password` | – | Set a new password from the emailed token → revoke other sessions + log in (200; 400 if invalid/expired) |
| POST | `/auth/refresh` | – | Rotate the refresh cookie → fresh access token (200; 401 if missing/invalid/reused) |
| POST | `/auth/logout` | ✓ | Revoke this device's refresh family + clear cookies (204) |
| GET  | `/auth/me` | ✓ | Current user (`id`, `email`) |
| POST | `/auth/password` | ✓ | Change password (verifies current, signs out other devices) (204; 401 if wrong) |
| POST | `/profile` | ✓ | Save the caller's profile |
| GET  | `/profile` | ✓ | Get the caller's profile (404 if none) |
| GET  | `/offers/count` | ✓ | Total offers in the DB |
| GET  | `/offers` | ✓ | Browse offers, paged + filtered (`limit`, `offset`, `location`, `min_salary`, `tech`, `search`, `include_expired`, `level`, `sort_by`, `sort_order`) |
| POST | `/offers/match` | ✓ | Deterministic match for a `candidate` (skills-based scoring) |
| POST | `/offers/match/ai` | ✓ | LLM-scored match (402 if budget exceeded, 503 if AI unavailable / fail-closed) |
| POST | `/salary/calculate` | ✓ | Net monthly PL take-home for a gross + contract type (optional personal `under_26` / `is_student` / `applies_tax_credit` and B2B `b2b_tax_form` / `b2b_zus_scheme` inputs) |
| GET  | `/config/model` | ✓ | The caller's active scoring model |
| GET  | `/config/models` | ✓ | Available models grouped by company + the active one |
| PUT  | `/config/model` | ✓ | Select the caller's scoring model (404 if not available) |
| GET  | `/usage/cost` | ✓ | Budget spend vs limit (`null` when spend is unknown) |
| PUT  | `/usage/limit` | ✓ | Set the caller's budget limit |
| POST | `/usage/reset` | ✓ | Reset the caller's usage tracking anchor to now |
| GET  | `/usage/summary` | ✓ | Per-model token totals for the caller (+ rate limits) |
| GET  | `/usage/org-spend` | ✓ | Org-wide real-$ provider spend today, from the OpenAI admin usage API (`null` without an admin key) |
| GET  | `/usage/org-usage` | ✓ | Org-wide authoritative per-model token usage today, from the OpenAI admin usage API (`null` without an admin key) |

Interactive docs at `http://localhost:8000/docs`. CORS allows `CORS_ORIGINS`
(default `http://localhost:4200`) with credentials, so the SPA can send cookies.

---

## Configuration

Loaded by `app/config.py` from `.env`. **`DATABASE_URL` is required** (read at import).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(required)* | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5433/db` |
| `DB_POOL_SIZE` | `5` | SQLAlchemy connection-pool size |
| `DB_MAX_OVERFLOW` | `10` | Extra connections allowed beyond the pool under load. Keep `WORKERS * (DB_POOL_SIZE + DB_MAX_OVERFLOW)` under the DB's max connections |
| `LLM_PROVIDER` | `gemini` | Org-level provider wiring: `gemini` or `openai` |
| `GEMINI_API_KEY` | `""` | Required when `LLM_PROVIDER=gemini`; also enables Gemini model listing |
| `OPENAI_API_KEY` | `""` | Required when `LLM_PROVIDER=openai`; also enables OpenAI model listing |
| `OPENAI_ADMIN_KEY` | `""` | **Optional, OpenAI only.** An admin key (scope `api.usage.read`) unlocks the provider's *authoritative* org-wide figures: the real-$ **org-spend backstop**/readout (`/usage/org-spend`) and per-model **org token usage** (`/usage/org-usage`), both for the current UTC day. Without it those endpoints return `null` and per-request local accounting is used instead. Org-wide — not attributable per user |
| `JWT_SECRET` | dev default | **Override in prod.** Signs session JWTs |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` | Access-token (JWT cookie) lifetime; refresh keeps the session alive |
| `REFRESH_TOKEN_TTL_DAYS` | `14` | Refresh-token lifetime + auth-cookie `max_age`; rotated on each `/auth/refresh` |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `5` | Wrong-credential attempts per (IP, email) before **429** |
| `LOGIN_RATE_LIMIT_WINDOW_MINUTES` | `15` | Window for the login / forgot-password throttle |
| `RATE_LIMITER_BACKEND` | `memory` | `memory` (per-process, single-worker) or `redis` (shared across workers/instances). `redis` needs `REDIS_URL` + the optional redis package (`uv sync --extra redis`) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL, used when `RATE_LIMITER_BACKEND=redis` |
| `APP_BASE_URL` | `http://localhost:4200` | Frontend base used to build emailed confirm/reset links |
| `SMTP_HOST` | `""` | SMTP server. **Empty → console fallback that only logs links** (dev) |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | `""` | SMTP credentials (leave empty for an open local relay) |
| `SMTP_USE_TLS` | `true` | Issue STARTTLS before sending |
| `EMAIL_FROM` | `no-reply@localhost` | From address on confirmation / reset emails |
| `EMAIL_VERIFICATION_TTL_HOURS` | `24` | Confirmation-link lifetime |
| `PASSWORD_RESET_TTL_HOURS` | `1` | Reset-link lifetime |
| `EMAIL_CHECK_DELIVERABILITY` | `false` | If `true`, MX-check the email domain at registration (needs DNS) |
| `COOKIE_SECURE` | `false` | Set `true` for HTTPS (required cross-site) |
| `COOKIE_SAMESITE` | `lax` | Set `none` for cross-site prod over HTTPS |
| `CORS_ORIGINS` | `http://localhost:4200` | Comma-separated allowed origins |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Bind address (use `0.0.0.0` in containers) |
| `WORKERS` | `1` | Uvicorn worker processes. DB-backed state (profiles, models, usage, refresh tokens) is shared, but the **in-memory login/forgot throttle and the model/use-case caches are per-process**: for `>1`, set `RATE_LIMITER_BACKEND=redis` so login throttling stays correct across workers (the app logs a startup warning otherwise) |
| `DEFAULT_BUDGET_USD` | `5.0` | Seeds a user's budget limit on first use + the org backstop limit |
| `AI_MATCH_CONCURRENCY` | `3` | Max offers scored by the LLM in parallel per request (low by default to respect free-tier provider limits) |
| `GOOGLE_RPM_LIMIT` | `10` | Client-side pacing for Google/Gemini calls. Known models are paced to their own free-tier RPM (from the model-limits registry); this is the fallback RPM for unknown models and the kill-switch (`0` disables Google pacing). OpenAI is never paced |
| `LLM_TIMEOUT_SECONDS` | `60.0` | Timeout for outbound LLM/provider calls |
| `BUDGET_SPEND_CACHE_TTL_SECONDS` | `60.0` | Cache TTL for the per-user spend figure |
| `BUDGET_FAIL_CLOSED` | `false` | If `true`, block AI match when spend can't be read |
| `MODELS_CACHE_TTL_SECONDS` | `300.0` | Cache TTL for the available-models list |
| `LOG_LEVEL` | `INFO` | Root log level: `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `LOG_FORMAT` | `json` (prod) / `console` (dev) | `json` = one structured object per line for log aggregators; `console` = human-readable. Default depends on `APP_ENV` |
| `LLM_DEBUG` | `false` | Verbose LLM request/response logging (raises `httpx`/`httpcore`/`openai` to DEBUG; logs full prompts/PII — never enable in production) |

Postgres credentials (`POSTGRES_USER/PASSWORD/DB/HOST/PORT`) are also read by
`docker-compose.yml` and typically composed into `DATABASE_URL`.

---

## Logging & observability

Logs are **structured and written to stdout** (12-factor: the platform ships them — the
`Dockerfile` / compose already capture stdout). Setup is centralized in
`app/observability/logging_config.py` and wired once from `main.py`, so every module that already
does `logging.getLogger(__name__)` is upgraded with no call-site changes and **no new dependency**
(stdlib `logging` + a JSON formatter).

- **Format / level.** `LOG_FORMAT=json` (default in production) emits one JSON object per line for
  aggregators (Loki / ELK / Datadog / CloudWatch); `LOG_FORMAT=console` (default in dev) is
  human-readable. `LOG_LEVEL` sets the root level.
- **Correlation id.** Each request adopts an inbound `X-Request-ID` header or mints a UUID, binds
  it in a `contextvar` (so it follows `await` hops and the AI match's concurrent scoring tasks),
  and echoes it in the `X-Request-ID` response header. **Every** log line emitted while handling
  the request carries it as `request_id`, so a request's app logs and its access log can be queried
  together (`app/observability/request_context.py`).
- **Access log.** `RequestLoggingMiddleware` (outermost middleware) logs one line per request:
  method, path (query string omitted, so tokens never land in logs), status, and `duration_ms`.
  `/health` is logged at DEBUG (orchestration probes hit it constantly); failures / 5xx at ERROR.
- **Unified server + app.** `uvicorn.run(..., log_config=None, access_log=False)` lets uvicorn's
  own loggers propagate into the same handler (one format for server + app) while the middleware
  owns the richer access log.
- **Adding fields.** Attach structured context with `extra={...}`
  (e.g. `log.info("scored offer", extra={"offer_id": 7})`) — it becomes JSON keys. Never log
  secrets, credentials, request bodies, or PII.

---

## Email delivery

Registration-confirmation and password-reset links are sent through an `EmailSender` port:

- **No `SMTP_HOST` (default):** a **console fallback** logs the email (including the link) to the
  API's stdout instead of sending it — handy for local dev. Watch the `uv run python main.py`
  console for `[email] not sending over SMTP …` and open the printed link.
- **`SMTP_HOST` set:** mail is sent over SMTP (`SMTP_*`, `EMAIL_FROM`). For local testing,
  [Mailpit](https://github.com/axllent/mailpit) is easiest (`SMTP_HOST=localhost`,
  `SMTP_PORT=1025`, `SMTP_USE_TLS=false`, web UI at `:8025`); for real inboxes use a provider
  (Gmail with a free App Password, Brevo, Mailgun, …).

Stuck without SMTP? Print a working confirmation link for an already-registered account:

```bash
uv run python -m app.scripts.verify_link you@example.com
```

(The link is a live, single-purpose login credential until it expires — treat it like a password.)

---

## Setup

Requires Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js, and Docker (for Postgres).

```bash
uv sync                       # backend deps (incl. dev group)
docker-compose up -d db       # start Postgres
uv run alembic upgrade head   # create app-owned tables on a fresh DB
cd frontend && npm install    # frontend deps
```

Create a `.env` with at least `DATABASE_URL` and a provider key (see Configuration). Example:

```
POSTGRES_USER=offers
POSTGRES_PASSWORD=offers
POSTGRES_DB=offers
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
GEMINI_API_KEY=...            # or OPENAI_API_KEY with LLM_PROVIDER=openai
JWT_SECRET=change-me-in-prod
```

---

## Running

```bash
uv run python main.py                 # API  → http://localhost:8000 (docs at /docs)
cd frontend && npm start              # SPA  → http://localhost:4200
```

Full stack via Docker (API runs migrations on boot, binds `0.0.0.0:8000`):

```bash
docker-compose up --build
```

---

## Testing

```bash
uv run pytest        # backend: unit + integration + api
uv run ruff check    # lint
cd frontend && npm test   # frontend (Vitest via `ng test`)
```

- `tests/unit/` — domain, application, infrastructure (no real I/O; uses `tests/fakes.py`).
- `tests/integration/` — real Postgres repos; **self-skip when the DB is unreachable**.
- `tests/api/` — FastAPI routes via `TestClient`, with use cases overridden by fakes; the
  harness overrides `get_current_user` to a fixed fake user.

CI (`.github/workflows/ci.yml`): on every push/PR — `uv sync --dev`, `ruff check`, `pytest`,
plus an advisory `pip-audit`.

---

## Frontend

Standalone Angular 22 SPA in `frontend/`, calling the API over HTTP with cookies. No shared
process with the backend.

```
frontend/src/app/
├── app.config.ts        # provideRouter, provideHttpClient(withInterceptors([authInterceptor])), Material defaults
├── app.routes.ts        # lazy routes; feature routes behind authGuard
├── app.ts / app.html    # shell: toolbar + tab nav (hidden when logged out), email + sign-out
├── core/
│   ├── guards/auth.guard.ts            # redirect to /login when unauthenticated
│   ├── interceptors/auth.interceptor.ts# withCredentials + X-CSRF-Token; on 401 → shared /auth/refresh + retry once, else /login
│   ├── services/api.service.ts         # typed HttpClient wrapper over every endpoint
│   ├── services/auth.service.ts        # signals; loadCurrentUser hydrates (falls back to /auth/refresh); shared refreshSession()
│   ├── models/                         # TS interfaces mirroring app/presentation/api/schemas.py
│   ├── constants/ , utils/             # offer levels; offer formatting/row helpers
└── features/
    ├── auth/{login,register,change-password,forgot-password,reset-password}  # Material auth forms
    ├── profile/                        # profile editor/viewer (summary, skills, projects, experience)
    ├── match-offers/                   # deterministic match
    ├── ai-match-offers/                # AI match (+ ai-match-state.service.ts)
    ├── browse-offers/                  # paginated offer browser with filters
    └── model-usage/                    # model selection, usage summary, budget controls
```

Routes: `/` → `/profile` (default), `/login`, `/register`, `/forgot-password`,
`/reset-password`, `/profile`, `/change-password`, `/match-offers`, `/ai-match-offers`,
`/browse-offers`, `/model-usage`.

---

## Development workflow & conventions

This project follows **TDD** and **Clean Architecture** (see `CLAUDE.md`, which is the
authoritative contributor guide and lists the expected skills):

1. Write a plan and confirm with the user before coding.
2. Write tests first.
3. Implement the feature.
4. Run `uv run pytest` (and `uv run ruff check`) and confirm passing.
5. Update `CLAUDE.md` / this README if new patterns or surfaces emerge.
