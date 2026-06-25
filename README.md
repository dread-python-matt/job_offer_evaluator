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
3. A **`FilterChain`** (composite of `OfferFilter`s, ANDed) drops offers that don't match the
   request before the expensive scoring runs.
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
| Auth | PyJWT (HS256), argon2-cffi (password hashing), email-validator |
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
│
├── domain/                   # Pure: entities, value objects, ports, algorithms (no frameworks)
│   ├── entities.py           #   Skill, Project, Experience, UserProfile, Offer, Salary
│   ├── auth.py               #   User (id, email, password_hash, token_version)
│   ├── budget.py             #   BudgetSettings, BudgetStatus(.exceeded)
│   ├── scoring.py            #   MatchScore, ScoreComponent, MatchedOffer, AiInsight, OfferScorer (port)
│   ├── filters.py            #   MatchCriteria, OfferBrowseFilters, OfferFilter (port), FilterChain, predicates
│   ├── sorting.py            #   Sort keys/types: sort_offers, sort_matched_offers
│   ├── salary_calculator.py  #   Net PL salary (B2B / employment / civil strategies) + net helpers
│   ├── errors.py             #   Domain errors (Auth, BudgetExceeded, AiScoring, CostUnavailable, …)
│   └── matching.py           #   Back-compat shim re-exporting the split modules above
│
├── application/              # Use cases + ports (orchestration; depends only on domain)
│   ├── ports.py              #   ALL repository/service ports + their DTOs (read this first)
│   ├── use_cases.py          #   Profile, offers, deterministic match, AI match, usage summary, salary
│   ├── auth_use_cases.py     #   RegisterUserUseCase, AuthenticateUserUseCase
│   ├── budget_service.py     #   BudgetService (per-user limit + token-accounted spend, cached)
│   └── ai_scoring_context.py #   AiScoringContext: resolves a user's model → AI use case (cached per model)
│
├── infrastructure/           # Adapters implementing the ports (the only layer with I/O)
│   ├── db.py, orm_models.py  #   Engine builder + SQLAlchemy ORM rows for app-owned + scraper tables
│   ├── postgres_*_repository.py   # user, user_profile, selected_model, model_usage, ai_score, budget, offer
│   ├── markdown_profile_repository.py  # Legacy profile adapter (test-only; not wired in main.py)
│   ├── scoring_strategies.py # SkillBasedScorer (deterministic); skill_utils.py = weighting math
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
│   ├── argon2_password_hasher.py, jwt_token_service.py        # Auth adapters
│   └── llm_logging.py, llm_utils.py                           # Debug logging; company_from_model, etc.
│
└── presentation/api/         # FastAPI entry points
    ├── routes.py             #   App router (profile, offers, match, salary, config/model, usage)
    ├── auth.py               #   public_router + private_router, get_current_user/verify_csrf guards, cookies
    ├── schemas.py            #   ALL Pydantic request/response models (the wire contract)
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
  `AI_MATCH_CONCURRENCY`) and is best-effort (a failed offer is dropped unless *all* fail).

---

## Authentication & multi-tenancy

Session auth via an **httpOnly JWT cookie** + **double-submit CSRF**; **open** self-serve
registration (auto-logs-in); **argon2** password hashing; `token_version` for
revocation / logout-everywhere.

- **Cookies:** `access_token` (httpOnly JWT, `sub`+`ver`+`exp`) and `csrf_token` (readable by
  the SPA). State-changing requests must echo the CSRF value in an `X-CSRF-Token` header.
- **Guards:** `get_current_user` resolves the user from the cookie (401 if missing/invalid/
  expired/revoked); `verify_csrf` enforces the header match on unsafe methods. Both are applied
  app-wide in `main.py` via `include_router(..., dependencies=[...])`.
- **Public routes** (no guard): `GET /health`, `POST /auth/register`, `POST /auth/login`.
  Everything else is gated.
- **Multi-tenant data.** App-owned tables carry a `user_id` FK (`ondelete="CASCADE"`); routes
  resolve `user: User = Depends(get_current_user)` and pass `user.id` into the use case, which
  threads it to the repository. Pattern to add a new per-user resource: port method takes
  `user_id` → use case threads it → route passes `user.id` → ORM row gets a `user_id` FK →
  repo filters on it → add a migration. (See `docs/auth-multitenancy.md`.)

Required env in production: **`JWT_SECRET`** (override the dev default). Cross-site HTTPS
deployments also need `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none`.

---

## AI matching & cost control

- **Providers.** LLM access goes through the OpenAI **Agents SDK**. `LLM_PROVIDER`
  (`gemini` default, or `openai`) selects only the *org-level* usage/cost wiring; the **scoring
  model is chosen per user** via the API and built with its own client, so selection never
  mutates global SDK state. Available models are listed from whichever provider keys are set
  (Gemini and/or OpenAI), then cached.
- **Pipeline.** For an AI match: filter → rank with `SkillBasedScorer` → send the top
  `offers_to_score` to the LLM → (optionally) translate the offer description to English →
  score → cache the result (content-addressed by model+candidate+offer) → record token usage.
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

---

## Data model

**App-owned** (created/migrated by this project, all keyed by `user_id` except `ai_score`):
`users`, `user_profile`, `selected_model`, `model_usage`, `budget`, `ai_score`.

**Scraper-owned, read-only** (do **not** migrate here): `offers`, `salaries`,
`normalized_salary`.

Migrations live in `alembic/versions/` (`0001`–`0009`): baseline → app tables (`user_profile`,
`ai_score`, `selected_model`, `users`) → per-user `user_id` FKs (`0006`–`0009`).

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
| POST | `/auth/register` | – | Create account, auto-login (201; 409 if email taken) |
| POST | `/auth/login` | – | Log in, set session cookies (401 on bad credentials) |
| POST | `/auth/logout` | ✓ | Clear session cookies (204) |
| GET  | `/auth/me` | ✓ | Current user (`id`, `email`) |
| POST | `/profile` | ✓ | Save the caller's profile |
| GET  | `/profile` | ✓ | Get the caller's profile (404 if none) |
| GET  | `/offers/count` | ✓ | Total offers in the DB |
| GET  | `/offers` | ✓ | Browse offers, paged + filtered (`limit`, `offset`, `location`, `min_salary`, `tech`, `search`, `include_expired`, `level`, `sort_by`, `sort_order`) |
| POST | `/offers/match` | ✓ | Deterministic match for a `candidate` (skills-based scoring) |
| POST | `/offers/match/ai` | ✓ | LLM-scored match (402 if budget exceeded, 503 if AI unavailable / fail-closed) |
| POST | `/salary/calculate` | ✓ | Net monthly PL take-home for a gross + contract type (optional `under_26` / `is_student` / `applies_tax_credit` tax inputs) |
| GET  | `/config/model` | ✓ | The caller's active scoring model |
| GET  | `/config/models` | ✓ | Available models grouped by company + the active one |
| PUT  | `/config/model` | ✓ | Select the caller's scoring model (404 if not available) |
| GET  | `/usage/cost` | ✓ | Budget spend vs limit (`null` when spend is unknown) |
| PUT  | `/usage/limit` | ✓ | Set the caller's budget limit |
| POST | `/usage/reset` | ✓ | Reset the caller's usage tracking anchor to now |
| GET  | `/usage/summary` | ✓ | Per-model token totals for the caller (+ rate limits) |

Interactive docs at `http://localhost:8000/docs`. CORS allows `CORS_ORIGINS`
(default `http://localhost:4200`) with credentials, so the SPA can send cookies.

---

## Configuration

Loaded by `app/config.py` from `.env`. **`DATABASE_URL` is required** (read at import).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(required)* | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5433/db` |
| `LLM_PROVIDER` | `gemini` | Org-level provider wiring: `gemini` or `openai` |
| `GEMINI_API_KEY` | `""` | Required when `LLM_PROVIDER=gemini`; also enables Gemini model listing |
| `OPENAI_API_KEY` | `""` | Required when `LLM_PROVIDER=openai`; also enables OpenAI model listing |
| `OPENAI_ADMIN_KEY` | `""` | Enables the org-spend backstop + external usage (OpenAI only) |
| `JWT_SECRET` | dev default | **Override in prod.** Signs session JWTs |
| `SESSION_TTL_DAYS` | `7` | Session cookie / token lifetime |
| `COOKIE_SECURE` | `false` | Set `true` for HTTPS (required cross-site) |
| `COOKIE_SAMESITE` | `lax` | Set `none` for cross-site prod over HTTPS |
| `CORS_ORIGINS` | `http://localhost:4200` | Comma-separated allowed origins |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Bind address (use `0.0.0.0` in containers) |
| `WORKERS` | `1` | Uvicorn worker processes (>1 is safe — state is persisted) |
| `DEFAULT_BUDGET_USD` | `5.0` | Seeds a user's budget limit on first use + the org backstop limit |
| `AI_MATCH_CONCURRENCY` | `10` | Max offers scored by the LLM in parallel per request |
| `LLM_TIMEOUT_SECONDS` | `60.0` | Timeout for outbound LLM/provider calls |
| `BUDGET_SPEND_CACHE_TTL_SECONDS` | `60.0` | Cache TTL for the per-user spend figure |
| `BUDGET_FAIL_CLOSED` | `false` | If `true`, block AI match when spend can't be read |
| `MODELS_CACHE_TTL_SECONDS` | `300.0` | Cache TTL for the available-models list |
| `LLM_DEBUG` | `false` | Verbose LLM request/response logging |

Postgres credentials (`POSTGRES_USER/PASSWORD/DB/HOST/PORT`) are also read by
`docker-compose.yml` and typically composed into `DATABASE_URL`.

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
│   ├── interceptors/auth.interceptor.ts# withCredentials + X-CSRF-Token; 401 → /login
│   ├── services/api.service.ts         # typed HttpClient wrapper over every endpoint
│   ├── services/auth.service.ts        # signals; loadCurrentUser hydrates from the cookie
│   ├── models/                         # TS interfaces mirroring app/presentation/api/schemas.py
│   ├── constants/ , utils/             # offer levels; offer formatting/row helpers
└── features/
    ├── auth/login , auth/register      # Material auth forms
    ├── profile/                        # profile editor/viewer (summary, skills, projects, experience)
    ├── match-offers/                   # deterministic match
    ├── ai-match-offers/                # AI match (+ ai-match-state.service.ts)
    ├── browse-offers/                  # paginated offer browser with filters
    └── model-usage/                    # model selection, usage summary, budget controls
```

Routes: `/` → `/profile` (default), `/login`, `/register`, `/profile`, `/match-offers`,
`/ai-match-offers`, `/browse-offers`, `/model-usage`.

---

## Development workflow & conventions

This project follows **TDD** and **Clean Architecture** (see `CLAUDE.md`, which is the
authoritative contributor guide and lists the expected skills):

1. Write a plan and confirm with the user before coding.
2. Write tests first.
3. Implement the feature.
4. Run `uv run pytest` (and `uv run ruff check`) and confirm passing.
5. Update `CLAUDE.md` / this README if new patterns or surfaces emerge.
