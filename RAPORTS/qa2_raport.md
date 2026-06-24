# QA Report #2 — Whole-Project Audit

**Date:** 2026-06-24
**Scope:** Full project (FastAPI backend + Angular frontend), security / correctness / performance / production-readiness.
**Method:** Static review of source, dependency inspection, git-tracking checks, SDK behaviour verification. No code was changed.

---

## 1. Executive summary

The codebase is **architecturally strong** (clean hexagonal layering, ports/adapters, ~362 passing unit tests, TDD discipline, good docstrings, ruff-clean) but is **not production-ready**. The blocking problems are operational/security concerns rather than design flaws:

- **Live secrets are committed to git** (real OpenAI + Gemini keys, DB password).
- **No authentication, authorization, or rate limiting** on any endpoint, while the app spends real money per request and binds to `0.0.0.0`.
- **Concurrency hazards** around the process-global LLM client and a shared mutable model-selection singleton.
- **Performance**: per-request full-table loads and sequential LLM calls; the budget check makes a live OpenAI API call on every match.

**Verdict:** Safe for local/single-trusted-user development. **Do not expose publicly** until at least the CRITICAL and HIGH items are resolved.

Severity counts: **2 Critical · 4 High · 8 Medium · 9 Low**.

> **Correction (2026-06-24):** an earlier draft flagged `httpx2` as a possible typosquat (C3). That was **wrong** — verified false. `httpx2` is a legitimate maintained fork of httpx that **Starlette 1.3.x prefers** for its `TestClient` (bundled in `starlette[full]`); all dependencies resolve from official PyPI with no custom index. The item has been removed from Critical and downgraded to a minor note (L9, loose version pin).

---

## 1a. Remediation progress (2026-06-24)

**Implemented (tested, suite green at 392):**
- **H1** — eliminated global LLM-client mutation: each agent is built with its own per-model client (`agent_models.build_chat_model` + `chat_model` on the scorer/translator); model selection no longer touches global SDK state. Concurrency-safe.
- **L5** — Alembic adopted: `alembic/` with baseline + `user_profile` + `ai_score` migrations (validated via offline SQL), scraper tables excluded; `create_all` retained as a dev/test fallback.
- **M6** — user profile moved to Postgres (`PostgresUserProfileRepository`, JSON document, atomic upsert) in place of the Markdown file.
- **M2** — AI scores persisted in Postgres (`PostgresAiScoreRepository`) behind a content-hash `CachingAiScorer` (sync + async), so identical (model, candidate, offer) scoring is paid for once.
- **C1** — `.env` + `DATA/` untracked & git-ignored; `.env.example` added. *(Key rotation + history purge still owed by the owner.)*
- **C2** — bind host now config-driven, defaults to `127.0.0.1`. App-level auth deferred by decision.
- **C3** — withdrawn (false positive); `httpx2` pin tightened to `>=2.4` (L9).
- **H4** — outbound timeouts (`LLM_TIMEOUT_SECONDS`) on scoring/translation clients, spend provider, and model-list providers.
- **H2** — budget spend cached with a TTL (`BUDGET_SPEND_CACHE_TTL_SECONDS`, anchor-keyed); configurable fail-closed (`BUDGET_FAIL_CLOSED`).
- **H3** — `configure_llm_logging` now logs a loud warning that `LLM_DEBUG` exposes PII; off by default.
- **M5** — single shared `pool_pre_ping` engine (`infrastructure/db.py`) across all repos.
- **M7** — available-models list cached with a TTL (`MODELS_CACHE_TTL_SECONDS`).
- **L7** — dependency-free `GET /health`.
- **M8** — global exception handler (generic 500, no internal leak) + base logging config.
- **M1** (partial, by parallel work) — AI scoring now runs concurrently (`AI_MATCH_CONCURRENCY`).

- **L1** — renamed `DailyCostSchema` → `UsageCostSchema` (JSON contract unchanged) and documented that `cost_usd` is cumulative, not daily.
- **M3/M4** — salary filtering & sorting pushed into SQL via the scraper's new `normalized_salary` table (read-only ORM model). `browse_offers` now joins offers→salaries→normalized_salary and filters/orders by the offer's best net (`max(net_of_max)`) in the database — no more full-table load + Python pass. Verified against live data (sort + min_salary) with 4 integration tests.
- **CI gate** — `.github/workflows/ci.yml` runs ruff + pytest + an advisory `pip-audit` on push/PR (uv-based; integration tests self-skip without a DB).
- **Containerization** — `Dockerfile` (uv, non-root, runs `alembic upgrade head` then serves) + `.dockerignore`; `docker-compose.yml` gains an `api` service wired to the DB with a `/health` healthcheck and `depends_on: service_healthy`. *(Image not built in this environment — needs `docker build` to verify on the target.)*
- **L8** — active model now **persisted** (`PostgresSelectedModelRepository`, single row); `AiScoringContext` reads it per request and rebuilds when it changes, so all workers agree. Added a configurable `WORKERS` setting (uvicorn import-string form when >1). This supersedes the earlier "in-memory only" model-selection choice — by owner decision, the selection now survives restarts and is shared across workers.

**Done (2026-06-24):** M3/M4 — salary handling standardized on **net everywhere**. The `Salary` value object now carries the scraper's normalized net (`net_min/net_mid/net_max`); filtering compares the **net floor** (`net_of_min`), sorting offers **recent + net min/mid/max** (asc/desc), across **both** browse (SQL pushdown) and match (Python on the net-bearing `Offer`). Display shows estimated net (midpoint as `net_monthly`, plus min/max) with a frontend disclaimer. The app's gross→net `SalaryCalculator` is retained only for the explicit `/salary/calculate` tool. *Next step (owner):* optional profile fields (age<26, PPK, contract pref) to refine the net estimate.
**Won't-do (assessed):** L2 (move DTOs from `ports.py` into domain) — high import churn across ~10+ files for a naming-consistency nit; keeping application DTOs beside their ports is a defensible convention. L3/L4 are acceptable as-is (L3 has `# noqa`; L4 is a domain-expert review item, not code).
**Still open:** L6 (frontend production environment config) — frontend work. C1 key rotation + git-history purge remain the owner's to do.

**Backend status: complete** — every backend finding is implemented, deliberately deferred, or assessed won't-do. Only the frontend (L6) and owner-only ops (C1 rotation/purge) remain.

---

## 2. Critical (fix before any deployment)

### C1 — Live secrets committed to the repository
- **Evidence:** `git ls-files` lists `.env`; `.gitignore` does **not** contain `.env`. The tracked `.env` holds a real `OPENAI_API_KEY` / `OPENAI_ADMIN_KEY` (`sk-proj-…`), `GEMINI_API_KEY`, and `POSTGRES_USER=admin` / `POSTGRES_PASSWORD=password`.
- **Impact:** Anyone with repo access (or anyone the history is ever pushed to) has working paid API keys and DB credentials. The keys are already in git **history**, so deleting the file is insufficient.
- **Action:**
  1. **Rotate every credential now** (OpenAI key, OpenAI admin key, Gemini key, DB password) — assume all are compromised.
  2. Add `.env` (and `DATA/`) to `.gitignore`; `git rm --cached .env`; commit.
  3. Purge from history (`git filter-repo` / BFG) if the repo is or will be shared.
  4. Provide a committed `.env.example` with placeholder values only.
  5. Move to a secrets manager / injected env vars for deployment.

### C2 — No authentication / authorization, app is internet-bindable and spends money
- **Evidence:** No auth dependency on any route in `routes.py`; `main.py:195` runs `uvicorn.run(app, host="0.0.0.0", …)`.
- **Impact:** If reachable, an anonymous caller can:
  - `POST /offers/match/ai` → trigger paid LLM scoring → **unbounded spend**.
  - `PUT /usage/limit` → raise/disable the only cost guard.
  - `POST /usage/reset` → zero out usage tracking.
  - `PUT /config/model` → switch models (cost/behaviour impact).
  - `GET`/`POST /profile` → read and overwrite the user profile (data integrity).
- **Action:** Add authentication (API key/JWT/session) and per-principal authorization before exposure; protect mutating + paid endpoints especially. Add rate limiting (see H2/M1). Bind to localhost or put behind an authenticated gateway until then.
- **Status (2026-06-24):** Partial mitigation applied — the bind host is now config-driven and **defaults to `127.0.0.1`** (`config.HOST`/`PORT`, used by `main.main()`), so the API is no longer reachable off-box by default. App-level **auth is deferred** by decision: a static API-key dependency on the router (+ an Angular HTTP interceptor) can be added later with no business-logic/data changes. Must be in place before setting `HOST=0.0.0.0` / any public exposure.

> *(Former C3 "`httpx2` typosquat" was investigated and found to be a **false positive** — see the correction note in §1 and L9. Dependency provenance is clean: all packages resolve from official PyPI, no custom index.)*

---

## 3. High

### H1 — Process-global LLM client + shared mutable model state is not concurrency-safe
- **Evidence:** `AiScoringContext.select_model` (`ai_scoring_context.py`) calls `configure_sdk` → `main._configure_sdk_for_model` → `set_default_openai_client(...)`, which (verified) mutates **process-global** `agents` config. `AiScoringContext` is a single shared mutable instance (`main.py`). FastAPI runs the **sync** route handlers in a threadpool, so requests are concurrent.
- **Impact:** A `PUT /config/model` (or two users implicitly on different providers) reconfigures the global client mid-flight; an in-progress `POST /offers/match/ai` can issue calls against the wrong provider/base-URL/key. No locking. Hard-to-reproduce, data-correctness/cost bugs under concurrency.
- **Action:** Make per-request client selection explicit (pass the configured client/agent into the scorer rather than mutating global state), or serialize model switches and in-flight scoring with a lock, or run single-worker with documented single-active-model semantics. At minimum, document the constraint and guard it.

### H2 — Budget enforcement is fragile and easily over/under-shot
- **Evidence:** `MatchOffersWithAiUseCase.execute` gates on `BudgetStatusReader.status()`; `BudgetService.status()` calls `SpendProvider.spend_since()` (a live OpenAI costs API call) on **every** AI-match request.
- **Impact:**
  - **Fail-open:** without an admin key (or on any cost-API error) `used_usd` is `None` → never blocks → unbounded spend (intentional, but a production risk worth an explicit decision/alert).
  - **Latency + new failure mode:** every match pays a network round-trip to OpenAI before scoring, which can itself 429/5xx.
  - **Accuracy:** OpenAI cost data is eventually-consistent/delayed, so a burst of matches can overshoot the limit substantially within a reporting window.
  - **Granularity:** the budget is global, not per-user/key.
- **Action:** Cache the spend figure with a short TTL; consider tracking spend locally (you already persist token usage) and reconciling against OpenAI periodically; make fail-open vs fail-closed configurable and alert on "budget unknown"; consider per-principal budgets.

### H3 — PII / data-governance: profile + job text sent to third-party LLMs and logged
- **Evidence:** `LLMScoringStrategy._build_prompt` sends candidate summary, project summaries, and job descriptions to OpenAI/Gemini; translation sends full descriptions. `llm_logging.configure_llm_logging` (when `LLM_DEBUG=true`) sets `openai`/`httpx` loggers to DEBUG, which logs **full request/response bodies** (prompts incl. PII) to stdout.
- **Impact:** Personal data leaves the system to third parties with no documented consent/retention; debug logs may persist PII (and potentially sensitive headers) wherever stdout is shipped.
- **Action:** Document data flows and a retention/consent policy; ensure `LLM_DEBUG` is off in production and never logs to durable sinks; consider redaction; review provider data-retention settings.

### H4 — No timeouts on outbound calls
- **Evidence:** `Runner.run_sync` (scoring + translation), `OpenAI().models.list()`, `OpenAISpendProvider.spend_since` — none set explicit timeouts.
- **Impact:** A hung provider connection holds a threadpool worker indefinitely; combined with sequential scoring (M1), a few stalls can exhaust the server's worker pool and wedge unrelated endpoints.
- **Action:** Set explicit client/request timeouts everywhere; add an overall per-request deadline and a concurrency cap for scoring.

---

## 4. Medium

### M1 — AI match does full-table load + sequential LLM calls (root cause of the 429s)
- **Evidence:** `MatchOffersWithAiUseCase.execute` → `_load_candidates` uses `OfferRepository.list_offers()` (loads the **entire** offers table), filters & ranks in Python, then scores the top `offers_to_score` **sequentially**, each with a scoring call **plus** a translation call.
- **Impact:** Up to ~2×N serial network round-trips per request (N=20 → ~40). Slow, and bursts trip provider per-minute limits (the observed 429). O(N) memory/CPU per request.
- **Action:** Bounded-concurrency scoring (e.g. asyncio/gather with a semaphore tuned to the model's RPM), client-side throttling, and push candidate pre-filtering into SQL so the whole table isn't materialized.

### M2 — No caching/memoization of AI scores
- **Evidence:** Scores are computed fresh each request; nothing persists `(candidate, offer, model) → score/insight`.
- **Impact:** Identical re-scoring on every search = repeated cost and latency.
- **Action:** Cache/persist AI scores keyed by candidate+offer+model (with invalidation on offer/profile change).

### M3 — `browse_offers` salary path paginates in Python
- **Evidence:** `postgres_offer_repository.py:36-43` — when `min_salary` is set or `sort_by == "salary"`, **all** matching rows are loaded, filtered/sorted in Python, then sliced. Salary isn't a real column (it's parsed from free text), so it can't be pushed to SQL.
- **Impact:** O(N) memory and no DB-side pagination; degrades as the offers table grows.
- **Action:** Persist a normalized monthly-salary column (ideally in the scraper schema) to enable SQL filtering/sorting/pagination.

### M4 — JSON columns filtered via `cast(…, Text) LIKE '%…%'`
- **Evidence:** `_apply_sql_filters` casts `locations`/`levels`/`tech_stack` JSON to text and `LIKE`-matches substrings.
- **Impact:** Non-sargable full scans (no index use); substring matching on serialized JSON is brittle (loose matches for location/tech; levels are quote-guarded but tech/location aren't).
- **Action:** Use proper JSON/array containment operators or normalized join tables with indexes; tighten matching semantics.

### M5 — Multiple un-tuned DB engines
- **Evidence:** `PostgresOfferRepository`, `PostgresModelUsageRepository`, `PostgresBudgetRepository` each call `create_engine` on the same `DATABASE_URL`.
- **Impact:** Separate connection pools, no `pool_pre_ping`/`pool_size`/recycle tuning → stale-connection errors and inefficient connection use under load.
- **Action:** Share one engine/sessionmaker; configure pooling and `pool_pre_ping`.

### M6 — Profile stored as a single non-atomic Markdown file
- **Evidence:** `MarkdownUserProfileRepository.save` uses `write_text` (truncate-then-write, no lock); custom regex parser silently skips malformed lines.
- **Impact:** Concurrent saves can corrupt/partial-write the file; inherently single-user; parser data-loss is silent.
- **Action:** For multi-user/production, store profiles in the DB; if keeping files, write atomically (temp file + rename) and validate on parse.

### M7 — Provider model list fetched on every relevant request (no cache)
- **Evidence:** `get_available_models` and `select_model` call `ListAvailableModelsUseCase.execute()` (network `models.list()`); startup also blocks on `_pick_initial_model`.
- **Impact:** Extra latency and provider-quota consumption on UI loads and model switches.
- **Action:** Cache available models with a TTL; refresh out-of-band.

### M8 — No global error handling / structured error contract
- **Evidence:** Only `BudgetExceededError`→402 and `AiScoringError`→503 are mapped (`routes.py`); other failures (DB down, provider 5xx on `models.list`, etc.) surface as bare 500s. Logging is ad-hoc (`logging.getLogger(__name__)` in a couple of places, no config in app).
- **Action:** Add a global exception handler with a consistent error schema, request IDs, and structured logging.

---

## 5. Low / code smells

- **L1 — Naming drift around budget/cost.** `/usage/cost` returns `DailyCostSchema` but the value is now **cumulative** (not daily); frontend still calls it `getDailyCost`/`dailyCost`/`costPct`; `BudgetSchema` overlaps. Consolidate naming and consider deprecating `DailyCostSchema` in favour of `BudgetSchema`.
- **L2 — Inconsistent VO placement.** Budget value objects live in `app/domain/budget.py`, but similar DTOs (`ModelUsage`, `AvailableModel`, `ModelLimits`, …) live in `application/ports.py`. Pick one convention.
- **L3 — Broad excepts.** `main._pick_initial_model` catches `Exception` (has `noqa`, acceptable) and `LLMScoringStrategy._run_tracked` catches `openai.APIError` broadly. Acceptable but worth narrowing/commenting.
- **L4 — Salary calculator is a dated approximation.** Many 2026 PLN tax/ZUS constants hardcoded (`salary_calculator.py`); correct-by-documentation but will silently go stale and isn't validated by a domain expert. Add a dated "review by" process and tests asserting bracket edges.
- **L5 — No migrations despite `alembic` dependency.** `alembic` is declared but there are no migration files; `budget` and `model_usage` tables are created via `Base.metadata.create_all` at startup. Adopt Alembic (or remove the dep) so schema changes are versioned/reviewable.
- **L6 — Frontend has a single hardcoded environment.** `frontend/src/environments/environment.ts` hardcodes `apiUrl: http://localhost:8000`; no production environment / file-replacement configured → not deployable to non-local without edits.
- **L7 — No health/readiness/version endpoint.** Nothing for orchestration probes or release verification.
- **L8 — Dev-style server entrypoint.** `main.main()` runs a single-process uvicorn with no workers and no graceful-shutdown/timeout config; no container/process manager. *(Host/port are now env-configurable and default to localhost — see C2 status.)*
- **L9 — Loose dependency pin.** `httpx2>=0.1.0` (dev) is legitimate (Starlette's preferred TestClient client) but the `>=0.1.0` floor is far below the installed `2.4.0`; a clean resolve could in theory pick an ancient release. Tighten to the real fork line (e.g. `>=2.4`). Add `pip-audit`/dependency scanning to CI generally.

---

## 6. Performance hotspots (consolidated)

| Path | Cost per request |
|---|---|
| `POST /offers/match/ai` | full offers-table load + Python filter/rank + **N sequential** scoring calls + N translation calls + **1 live OpenAI costs call** (budget gate) |
| `GET /offers` with `min_salary`/salary sort | entire filtered result set materialized & paginated in Python |
| `GET /config/models`, `PUT /config/model` | uncached provider `models.list()` network call |
| cost/usage providers | new `OpenAI()` client constructed per call |

Biggest wins: bounded-concurrency + caching for AI scoring (M1/M2), cache the budget spend figure (H2), share one tuned DB engine (M5).

---

## 7. Production-readiness checklist (gaps)

- [ ] Secrets out of git + rotated + secrets manager (C1)
- [ ] AuthN/AuthZ + rate limiting + per-user budget (C2, H2)
- [ ] Dependency scanning (`pip-audit`) in CI + tighten loose pins (L9)
- [ ] Concurrency-safe LLM client / model switching (H1)
- [ ] Timeouts + concurrency caps + circuit breaking on outbound calls (H4, M1)
- [ ] Observability: structured logs, request IDs, metrics, tracing, error monitoring (M8)
- [ ] DB: single tuned engine + pooling; Alembic migrations; indexes for filters (M3–M5, L5)
- [ ] PII/data-flow policy; `LLM_DEBUG` off in prod; redaction (H3)
- [x] Deployment: container + `/health` healthcheck (L7), multi-worker server (L8), per-env config — *done*; CORS still must be locked to prod origins at deploy time
- [ ] Frontend prod environment config (L6)
- [ ] Profile storage in a real DB for multi-user (M6)
- [x] CI gate: ruff + pytest + advisory `pip-audit` (`.github/workflows/ci.yml`); coverage threshold still optional

---

## 8. What's already good (keep it)

- Clean hexagonal/DDD layering; dependencies point inward; behaviour behind ports.
- Broad, fast unit-test suite (~362 tests) with shared fakes and TDD discipline; ruff-clean.
- Deliberate graceful degradation (`CostUnavailableError` fail-open, startup model auto-pick fallback).
- Retry/backoff with capped attempts on scoring; per-model/company usage tracking.
- Strong, accurate docstrings and `README`; clear `CLAUDE.md` workflow.

---

## 9. Suggested remediation order

1. **C1** — rotate/remove secrets, ignore `.env`, add `.env.example`. (hours)
2. **C2** — add auth + rate limiting; keep bound to localhost until done. (days)
3. **H1, H4** — concurrency safety + timeouts. (days)
4. **H2, M1, M2** — budget caching, bounded-concurrency scoring, score caching (also fixes the 429s). (days)
5. **H3, M8** — data-flow policy + observability/error contract. (days)
6. **M3–M7, L-series** — DB/perf/config hardening and cleanup. (incremental)

*End of report.*
