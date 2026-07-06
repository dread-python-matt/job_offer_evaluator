# Job Offers Evaluator

![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.137-009688?logo=fastapi&logoColor=white)
![Angular 22](https://img.shields.io/badge/Angular-22-DD0031?logo=angular&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-SQLAlchemy%202.x-4169E1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/tests-pytest%20%7C%20vitest-0A9EDC)
![Lint: ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

<!-- Once this repo is hosted on GitHub, add a live CI badge:
![CI](https://github.com/dread-python-matt/job_offer_evaluator/actions/workflows/ci.yml/badge.svg) -->

Matches job offers to a user's profile and (optionally) scores fit with an LLM.
The backend is a **FastAPI JSON API**; the frontend is a **standalone Angular app** that
talks to it over HTTP (CORS, cookie session) — there is no shared process. The app is
**multi-tenant**: every user has their own profile, selected model, usage, and budget.

> **For agents:** this file is the map. The dependency rule is *inward only*
> (`presentation`/`infrastructure` → `application` → `domain`). Business logic lives in
> `app/domain` and `app/infrastructure`; `main.py` is the composition root that wires every
> port to a concrete adapter via FastAPI `dependency_overrides`. Start there and in
> `app/presentation/api/routes.py`.

## Highlights

- **Two matching modes** — fast **deterministic** skill-overlap scoring (no I/O), or **LLM-scored** fit with pros, cons, and a rationale.
- **Bring-your-own-key & multi-tenant** — each user adds their own OpenAI/Google key; per-user profile, model selection, usage, and budgets.
- **Cost & rate-limit guardrails** — per-user USD budgets, an org-spend backstop (OpenAI admin key), Gemini free-tier per-day request caps, and client-side RPM pacing.
- **Skill canonicalization** — an alias map + case/diacritic/separator folding collapse `JS`/`JavaScript`, `k8s`/`Kubernetes`, and PL/EN variants to one concept before matching (and for SQL browse filters).
- **Production-grade auth** — email-confirmed registration, argon2 hashing, httpOnly JWT + rotating refresh tokens (reuse detection), double-submit CSRF, and login throttling.
- **Polish net-salary calculator** — 2026 tax/ZUS rules per contract type (B2B / employment / civil).
- **Clean / Hexagonal architecture** — the domain has zero framework dependencies; ports & adapters with a single `main.py` composition root.
- **Observability & 12-factor** — structured JSON logs with per-request correlation ids, a readiness probe, and a tunable connection pool.
- **Zero-config demo** — `docker compose up` + ~50 seed offers; browsing, deterministic matching, and the salary calculator work with **no API keys**.

## Table of contents

- [Quickstart](#quickstart)
- [What it does](#what-it-does)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Backend architecture](#backend-architecture)
- [Authentication & multi-tenancy](#authentication--multi-tenancy)
- [AI matching & cost control](#ai-matching--cost-control)
- [Data model](#data-model)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [Logging & observability](#logging--observability)
- [Email delivery](#email-delivery)
- [Setup](#setup)
- [Running](#running)
- [Testing](#testing)
- [Frontend](#frontend)
- [Contributing](#contributing)
- [License](#license)

---

## Quickstart

Get the app running **with sample data and no API keys** in a few commands. Browsing offers,
deterministic matching and the salary calculator need no provider key; AI matching uses a
per-user key you add later in the UI.

### Get the code

```bash
git clone https://github.com/dread-python-matt/job_offer_evaluator.git   # or download the ZIP and unzip
cd job_offer_evaluator
```

Every command below runs from the repository root (`job_offer_evaluator/`), and
`cp .env.example .env` gives you a working config with no edits needed for the demo.

### A. Docker (recommended)

Starts Postgres + the API + the Angular UI (migrations run on boot). Needs only Docker.

```bash
cp .env.example .env              # defaults work as-is for the demo
docker compose up -d --build      # start Postgres + API + frontend (UI at :4200)
docker compose run --rm seed      # load ~50 demo offers + the demo login (idempotent)
```

* **UI**  → http://localhost:4200 — sign in with the seeded demo account below
* **API** → http://localhost:8000

The `frontend` container runs `ng serve`, and its **first** start installs npm deps — give it a
minute before the UI answers. Then log in with the demo account the `seed` step created:

| Email | Password |
|---|---|
| `demo@example.com` | `Demo1234!` |

This account is **already email-verified**, so it skips the confirmation step and signs in
immediately. (Registering your own account still emails a confirmation link — see below.)

### B. Local (Postgres in Docker, app on your machine)

Needs Python 3.13, [uv](https://docs.astral.sh/uv/), and Docker (for Postgres only).

```bash
uv sync                                     # backend deps
cp .env.example .env                        # defaults point at the Docker Postgres below
docker compose up -d db                     # just Postgres
uv run alembic upgrade head                 # create app-owned tables
uv run python -m app.scripts.seed_offers    # load ~50 diverse demo offers
uv run python -m app.scripts.seed_user      # create the demo login (demo@example.com / Demo1234!)
uv run python main.py                       # API → http://localhost:8000
```

> **`.env.example` already sets `APP_ENV=development`,** so copying it (above) is all the local
> run needs. `APP_ENV` otherwise defaults to `production` (secure by default), which refuses to
> boot with the committed dev secrets / non-secure cookies. A real deployment sets
> `APP_ENV=production` and supplies its own strong secrets (the Docker Compose path sets
> `development` just for the demo).

Frontend (separate terminal): `npm --prefix frontend install` then
`npm --prefix frontend start` → http://localhost:4200, then sign in as `demo@example.com` /
`Demo1234!`.

### Demo data (fixtures)

The seed script (`app/scripts/seed_offers.py`) fills the externally-owned
`offers` / `salaries` / `normalized_salary` tables — which Alembic does **not** create (they
belong to the external offers source) — with ~50 recent, diverse offers: many tech stacks, **7 job portals**,
**every seniority** (Intern → Expert) and **all three contract types** (B2B / permanent /
civil), each with NET salaries computed by the app's own calculator. It is **idempotent**
(re-running replaces only the `seed-*` rows and never touches real external data). Preview
without writing anything:

```bash
uv run python -m app.scripts.seed_offers --dry-run
```

A companion script seeds the **demo login** (`app/scripts/seed_user.py`): an already-verified
`demo@example.com` / `Demo1234!` account, so you can sign in without the email-confirmation step.
It is idempotent and never overwrites an existing account's password. `docker compose run --rm
seed` runs both seeders; locally, run it yourself:

```bash
uv run python -m app.scripts.seed_user
```

### Try AI matching (optional)

Log in as the demo account (or register your own), then add a provider API key (OpenAI or
Google) on the **Model & usage** page — AI matching requires *your own* key (there is no shared
key). With no SMTP configured, a *self-registered* account's email-confirmation link is printed
to the API console; you can also mint one with
`uv run python -m app.scripts.verify_link you@example.com`.

---

## What it does

1. A **user profile** (summary, skills with 1–5 ratings, projects, experience) is saved per
   user as a JSON document in Postgres. It can also be sent inline as the `candidate` of a
   match request.
2. **Job offers** live in a Postgres `offers` table owned by a separate, external offers source —
   this app only **reads** it (plus the external `salaries` / `normalized_salary` tables).
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
| Lint / type / test | ruff, mypy, pytest (+ pytest-cov) |
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
├── docker-compose.yml    # Postgres + API + Angular UI (+ opt-in seed) for local dev
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
│   ├── db.py, orm_models.py  #   Engine builder (tunable connection pool) + SQLAlchemy ORM rows for app-owned + external tables
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
  for display. Unknown tokens are logged on `app.skills`, and the unmapped corpus tail is
  persisted to an `unknown_skill_token` table (`mine_skill_corpus --persist`) ranked by frequency
  so the map grows from real data (the suggester reads it via `suggest_skill_aliases --from-db`).
  Scoring weights
  **evidenced** skills (used in a real project/experience) above self-claimed ratings, and **caps**
  an un-evidenced self-claim at `UNEVIDENCED_SELF_RATING_CAP` (the main calibration knob in
  `skill_utils.py`) so a high rating needs evidence to count fully. The same canonical map also
  powers **browsing's tech filter**: an `offer_skill` index (one row per offer×concept, rebuilt
  by `uv run python -m app.scripts.index_offer_skills`) lets the offers list filter by concept in
  SQL, so a `k8s` filter finds `Kubernetes` offers. The Docker image rebuilds the index on start
  (after migrations, best-effort, and a no-op before any offers are loaded); each build stamps
  `offer_skill_index_meta` with the alias-map version, so a stale or unbuilt index is visible via
  `… index_offer_skills --status` rather than silently matching nothing. Rebuild after new offers are loaded or
  whenever the alias map changes. See `docs/skills-normalization.md`.

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
- **Public routes** (no guard): `GET /health`, `GET /health/ready`, and the `/auth` entry points
  `register`, `verify-email`, `login`, `forgot-password`, `reset-password`, `refresh`. Everything
  else is gated.
- **Registration is email-confirmed.** `register` creates an *unverified* account, emails a
  confirmation link, and issues **no** session (202). `login` returns **403** until the account
  is verified; following the emailed link (`verify-email`) marks it verified and logs the user
  in. Pre-existing accounts were grandfathered as verified (migration `0010`).
- **Password strength.** New passwords (register, reset, change) must be **at least 8 characters
  and include a lowercase letter, an uppercase letter, a number, and a special character**. The
  rule lives in `app/domain/password_policy.py`, is enforced server-side by the auth request
  schemas (422 on violation), and is mirrored by the Angular validators for instant feedback.
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

Required env in production: **`JWT_SECRET`** and **`API_KEY_ENCRYPTION_KEY`** (override both dev
defaults — the app refuses to boot with them when `APP_ENV=production`). Cross-site HTTPS
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
- **USD budgets (dollar-priced providers, e.g. OpenAI).** Before scoring, an AI match against a
  USD-budgeted provider checks a budget gate (`CompositeBudgetStatusReader`) that combines:
  1. the user's **token-accounting budget** — their recorded usage priced by
     `HardcodedModelPricingRegistry` (`TokenAccountingSpendProvider` + `BudgetService`), and
  2. a global **org-spend backstop** (`OrgSpendBackstop`) protecting the owner's real provider
     bill — **active only when an OpenAI admin key is configured**.
  If any budget is exceeded → `BudgetExceededError` → **HTTP 402**. If spend can't be read,
  the match proceeds (fail-open) unless `BUDGET_FAIL_CLOSED=true`, which raises **503**.
  Caveats: usage attribution can drift under concurrent same-process matches; unknown-model
  pricing counts as $0 (spend is a lower bound). **Gemini/Google matches skip this USD gate** —
  their free tier is budgeted by requests/day, not dollars (see below).
- **Per-day request budget (Gemini free tier).** The budget for Gemini matches — it **replaces**
  the USD gate for Google (a Google key carries no dollar budget). Gated in `main.py` by passing
  `budget=None` for Google models, leaving `TokenAccountingDailyRequestUsageReader` as the sole
  gate: it counts the user's recorded requests for the model's provider since the daily reset
  (midnight US/Pacific) against a cap — the user's override on their key
  (`user_api_key.daily_request_limit`), else the model's free-tier requests-per-day from the limits
  registry. When today's requests reach the cap the AI match raises `DailyRequestLimitExceededError`
  → **HTTP 402**. Applies only to keyable Gemini models with a stored key; anything else is ungated
  (fail-open). Read/adjust via `GET`/`PUT /usage/daily-requests`.
- **Usage accuracy (OpenAI).** Local accounting prices each call's reported `usage`; for OpenAI
  it reads `input_tokens_details.cached_tokens` and prices prompt-cache hits at the model's
  discounted cached rate (the scoring prompt's constant instructions + candidate profile repeat
  across offers, so cache hits are common and full-input pricing would overstate cost). Gemini is
  unchanged (no cached rate → priced at the normal input rate). This figure is an **estimate**
  (approximate list prices) and `/usage/summary` returns it per model as `cost_usd` (**API-only** —
  the model-usage page no longer shows per-model token counts or the estimate; it surfaces the
  authoritative org spend from the admin key instead). When an **`OPENAI_ADMIN_KEY`** (or the
  caller's saved admin key) is set, `/usage/org-spend`
  exposes the **authoritative** org-wide real-$ spend **month-to-date (UTC)** — matching OpenAI's
  usage page "this month" total — and `/usage/org-usage` the authoritative per-model token usage
  (today), both from OpenAI's admin Usage/Costs API, queried per-model (`group_by=["model"]`), in
  daily buckets, and paginated to completion. The admin client authenticates with `admin_api_key=`
  (these org routes reject a normal `api_key=`).

---

## Data model

**App-owned** (created/migrated by this project; per-user tables carry a `user_id` FK):
`users`, `user_profile`, `selected_model`, `model_usage`, `budget`, `ai_score`,
`refresh_tokens`, `user_api_key`, `openai_admin_key`. (`ai_score` is a global
content-addressed cache; `refresh_tokens` holds SHA-256 hashes only; `user_api_key` holds
encrypted provider keys and `openai_admin_key` the user's encrypted OpenAI admin key
(one per user) — never raw tokens or plaintext keys.)

**Externally-owned, read-only** (do **not** migrate here): `offers`, `salaries`,
`normalized_salary`. On a database without an external offers source, populate them with demo data via
`uv run python -m app.scripts.seed_offers` (see [Quickstart → Demo data](#demo-data-fixtures)).

Migrations live in `alembic/versions/` (`0001`–`0020`): baseline → app tables (`user_profile`,
`ai_score`, `selected_model`, `users`) → per-user `user_id` FKs (`0006`–`0009`) →
`users.email_verified` (`0010`) → `refresh_tokens` (`0011`) → `user_api_key` (`0012`) →
`model_usage (user_id, created_at)` index (`0013`) → `model_usage.estimated` (`0014`) →
`model_usage.cost` (`0015`) → `openai_admin_key` (`0016`) →
`user_api_key.daily_request_limit` (`0017`, the optional per-day request cap) →
`offer_skill` (`0018`, the app-owned canonical skill index for concept-based browse filtering) →
`offer_skill_index_meta` (`0019`, single-row bookkeeping recording which alias-map version built
the index, for staleness detection) → `unknown_skill_token` (`0020`, the persisted unmapped
skill-token tail, ranked by frequency, for alias-map curation).

> **Alembic is the single source of truth for the app-owned schema.** Repositories no longer
> create their tables at construction (`create_all` was removed), so the app can start and serve
> `/health` even when the database is temporarily down. Always run `uv run alembic upgrade head`
> against a fresh database before starting the app; the Docker image does this automatically (see
> the `Dockerfile` `CMD`). Integration tests build the schema themselves via a fixture in
> `tests/integration/conftest.py`.
>
> The engine (`app/infrastructure/db.py`) sets a 10s libpq `connect_timeout`, so an
> unreachable database fails fast with a clear error instead of hanging for the OS TCP timeout
> (~2 minutes), and uses `pool_pre_ping` to transparently recycle stale/dropped connections.

---

## API reference

All paths are JSON. **Auth** = requires the session cookie; state-changing methods also require
the `X-CSRF-Token` header.

| Method | Path | Auth | Description |
|---|---|:--:|---|
| GET  | `/health` | – | Liveness probe (`{"status":"ok"}`); dependency-free, stays green even if the DB/providers are degraded |
| GET  | `/health/ready` | – | Readiness probe: `SELECT 1` against the DB → `{"status":"ready"}` (200), or **503** when the DB is unreachable. Point orchestrator/load-balancer readiness checks here |
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
| GET  | `/usage/summary` | ✓ | Per-model token totals for the caller (+ rate limits + estimated `cost_usd` from approximate list prices). **API-only** — the UI no longer displays per-model usage or the estimate |
| GET  | `/usage/daily-requests` | ✓ | Per-day request budget for the caller's selected model: requests used today vs the cap (the user's override, else the model's free-tier requests-per-day default). `null` when there's no cap to show (e.g. an OpenAI model, or a Gemini model with no stored key) |
| PUT  | `/usage/daily-requests` | ✓ | Set (a number) or clear (`limit: null` → revert to the free-tier default) the per-day request cap on the key backing the selected model (404 if no keyable model is selected or no key exists) |
| GET  | `/usage/org-spend` | ✓ | Org-wide real-$ provider spend **month-to-date (UTC)** — matches OpenAI's usage page "this month" — from the OpenAI admin usage API. Uses the caller's saved admin key, else the env `OPENAI_ADMIN_KEY` (`null` when neither is set) |
| GET  | `/usage/org-usage` | ✓ | Org-wide authoritative per-model token usage today, from the OpenAI admin usage API. Uses the caller's saved admin key, else the env `OPENAI_ADMIN_KEY` (`null` when neither is set) |
| GET  | `/api-keys/providers` | ✓ | The fixed list of providers you can register a key for (drives the picker UI) |
| GET  | `/api-keys` | ✓ | The caller's stored provider keys — masked hint + per-key USD budget/usage |
| POST | `/api-keys` | ✓ | Add a provider key, validated against the provider before storing (**201**; 400 invalid/unsupported; 409 if that provider already has a key) |
| PATCH | `/api-keys/{api_provider}` | ✓ | Update a stored key's USD budget (404 if no such key) |
| DELETE | `/api-keys/{api_provider}` | ✓ | Remove a stored provider key (204; 404 if none) |
| GET  | `/admin-key` | ✓ | The caller's saved OpenAI admin key as a masked hint (`null` when none is set) |
| PUT  | `/admin-key` | ✓ | Save/rotate the caller's OpenAI admin key (verified against the org costs API; 400 if rejected) |
| DELETE | `/admin-key` | ✓ | Remove the caller's saved admin key (idempotent, 204) |

The API base URL is `http://localhost:8000`. CORS allows `CORS_ORIGINS`
(default `http://localhost:4200`) with credentials, so the SPA can send cookies.

### Example

```bash
curl -s http://localhost:8000/health
# → {"status":"ok"}
```

Every other route needs a session cookie + a CSRF header on unsafe methods, obtained by logging
in through the SPA (or `POST /auth/login`).

---

## Configuration

Loaded by `app/config.py` from `.env`. **`DATABASE_URL` is required** (read at import).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(required)* | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5433/db` |
| `DB_POOL_SIZE` | `5` | SQLAlchemy connection-pool size |
| `DB_MAX_OVERFLOW` | `10` | Extra connections allowed beyond the pool under load. Keep `WORKERS * (DB_POOL_SIZE + DB_MAX_OVERFLOW)` under the DB's max connections |
| `LLM_PROVIDER` | `gemini` | Org-level provider wiring: `gemini` or `openai` |
| `GEMINI_API_KEY` | `""` | **Optional.** Org-level Gemini wiring only; the app boots without it and AI scoring uses each user's own key. Leave unset for the no-AI demo |
| `OPENAI_API_KEY` | `""` | **Optional.** Org-level OpenAI wiring only; the app boots without it and AI scoring uses each user's own key. Leave unset for the no-AI demo |
| `OPENAI_ADMIN_KEY` | `""` | **Optional, OpenAI only.** A fallback admin key (scope `api.usage.read`) unlocking the provider's *authoritative* org-wide figures: the real-$ **org-spend backstop**/readout (`/usage/org-spend`) and per-model **org token usage** (`/usage/org-usage`), both for the current UTC day. Users can also save their own admin key in-app (`PUT /admin-key`), which takes precedence over this for the readouts; this env key remains the backstop's source. Without either, those readouts return `null` and per-request local accounting is used instead. Org-wide — not attributable per user |
| `APP_ENV` | `production` | Deployment environment. Anything other than an explicit `development`/`dev`/`test`/`local` is treated as **production** and runs fail-fast config validation (`app/config_validation.py`): the app refuses to boot with the committed dev `JWT_SECRET`/`API_KEY_ENCRYPTION_KEY`, non-secure cookies, or wildcard CORS. **Defaults to `production` so forgetting to set it fails closed** — local dev / CI must opt in with `APP_ENV=development` (docker-compose sets it for the demo) |
| `JWT_SECRET` | dev default | **Override in prod.** Signs session JWTs. The committed dev default is rejected at boot unless `APP_ENV` is an explicit dev/test value |
| `API_KEY_ENCRYPTION_KEY` | dev default | **Override in prod.** Fernet key encrypting users' stored provider/admin API keys at rest (symmetric — the keys must be replayed to the provider, so they're encrypted, never hashed). The committed dev default is rejected at boot in production, and **rotating it makes existing stored keys undecryptable**. Generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
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
| `DEFAULT_BUDGET_USD` | `5.0` | Seeds a user's budget limit on first use (and is the default for `ORG_DAILY_BUDGET_USD`) |
| `ORG_DAILY_BUDGET_USD` | = `DEFAULT_BUDGET_USD` | Org-wide daily spend cap for the OpenAI **org-spend backstop** (all tenants summed; active only when an admin key is configured). Decoupled from the per-user default so a multi-tenant OpenAI deployment isn't capped by one shared $5/day |
| `AI_MATCH_CONCURRENCY` | `3` | Max offers scored by the LLM in parallel per request (low by default to respect free-tier provider limits) |
| `GOOGLE_RPM_LIMIT` | `10` | Client-side pacing for Google/Gemini calls. Known models are paced to their own free-tier RPM (from the model-limits registry); this is the fallback RPM for unknown models and the kill-switch (`0` disables Google pacing). Under `WORKERS > 1` the per-model budget is split across workers so the fleet stays under the one per-project provider cap. OpenAI is never paced |
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
  The probe paths `/health` and `/health/ready` are logged at DEBUG (orchestration hits them
  constantly); failures / 5xx (including a 503 from a failed readiness check) at ERROR.
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
For the fastest path see the [Quickstart](#quickstart); the steps below are the full reference.

```bash
uv sync                                     # backend deps (incl. dev group)
cp .env.example .env                        # config — working local defaults
docker compose up -d db                     # start Postgres
uv run alembic upgrade head                 # create app-owned tables on a fresh DB
uv run python -m app.scripts.seed_offers    # load ~50 demo offers (optional, populates the UI)
npm --prefix frontend install               # frontend deps
```

`.env.example` ships working local defaults, so `cp .env.example .env` is enough to start.
`DATABASE_URL` is the only required variable; a provider key is **optional** — the app boots
without one and AI matching uses a per-user key added in the UI (see [Configuration](#configuration)).

---

## Running

```bash
uv run python main.py                 # API  → http://localhost:8000
npm --prefix frontend start           # SPA  → http://localhost:4200
```

Full stack via Docker (API runs migrations on boot; Angular UI served at `:4200`):

```bash
docker compose up --build         # Postgres + API + frontend
docker compose run --rm seed      # optional: load ~50 demo offers + the demo login
```

---

## Testing

```bash
uv run pytest        # backend: unit + integration + api
uv run ruff check    # lint
npm --prefix frontend test   # frontend (Vitest via `ng test`)
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
    ├── model-usage/                    # host page: active-model selector + composes the cards below
    ├── api-keys/                       # provider keys (OpenAI shows a USD budget; the Google row embeds the daily budget + a Delete)
    ├── admin-key/                      # OpenAI admin key + org spend (month-to-date)
    └── daily-requests/                 # Gemini free-tier per-day request budget (embedded in the Google api-keys row)
```

Routes: `/` → `/profile` (default), `/login`, `/register`, `/forgot-password`,
`/reset-password`, `/profile`, `/change-password`, `/match-offers`, `/ai-match-offers`,
`/browse-offers`, `/model-usage`.

---

## Contributing

This project follows **TDD** and **Clean Architecture**; [`CLAUDE.md`](CLAUDE.md) is the
authoritative contributor guide (layer boundaries, conventions, and the expected skills).

1. Branch off `main`.
2. **Write or update tests first** — `tests/` (backend) or `*.spec.ts` (frontend).
3. Implement the smallest correct change that respects the dependency rule (the domain stays
   framework-free).
4. Run the checks below and confirm they pass.
5. Update `README.md` / `CLAUDE.md` when a change affects setup, configuration, the API, the
   data model, auth, or the frontend structure.
6. Use a Conventional-Commit-style title (`feat`, `fix`, `refactor`, `perf`, `docs`, `style`,
   `test`, `build`, `ci`, `chore`).

```bash
uv run ruff check            # backend lint
uv run mypy                  # backend types
uv run pytest                # backend tests
npm --prefix frontend test   # frontend tests
```

---

## License

Released under the [MIT License](LICENSE) — free to use, modify, and distribute with attribution
and without warranty.
