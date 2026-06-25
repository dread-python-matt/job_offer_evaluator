# Security & Quality Audit — Evaluator (Job Offer Matcher)

**Date:** 2026-06-25
**Auditor:** Senior QA (security focus)
**Scope:** Full backend (`app/`, `main.py`, `alembic/`), deployment (`Dockerfile`, `docker-compose.yml`, CI), and frontend auth surface (`frontend/src`).
**Method:** Manual code review + git-history inspection. No code was modified.

---

## 0. Executive summary

The application is, on the whole, **built with good security instincts**: Argon2id hashing, httpOnly session cookies (no tokens in `localStorage`), double-submit CSRF with constant-time comparison, rotating + reuse-detecting refresh tokens stored hash-only, parameterized SQL (no injection found), per-tenant data scoping with no IDOR, and a catch-all 500 handler that prevents stack-trace leakage. These are real strengths and are listed in §6.

However, it is **not yet production-ready**. There are **2 Critical** and **2 High** issues that must be fixed before any internet-facing deployment, plus several Medium items around abuse-resistance and deployment safety.

| # | Severity | Title |
|---|----------|-------|
| C1 | **Critical** | Live secrets (Gemini key, Postgres password, DB URL) + PII committed to git history |
| C2 | **Critical** | Default `JWT_SECRET` shipped in a public repo, with no startup guard — forgeable sessions |
| H1 | **High** | Cross-tenant token-usage misattribution via a shared in-memory tracker (budget bypass) |
| H2 | **High** | Password-reset / email-verification tokens are replayable for their full TTL (re-takeover) |
| M1 | Medium | No rate limit on `/auth/register` — email bombing + Argon2 CPU DoS |
| M2 | Medium | Budget gate is check-then-act + fail-open → AI spend overrun under concurrency |
| M3 | Medium | In-memory rate limiter is per-process; `WORKERS>1` silently defeats login throttling |
| M4 | Medium | No security response headers (HSTS/CSP/X-Content-Type-Options/X-Frame-Options) |
| M5 | Medium | Insecure cookie defaults with no production enforcement |
| M6 | Medium | Unbounded work in `/offers/match` (full-table load + in-Python scoring) — DoS |
| L1–L8 | Low | Enumeration, login/refresh CSRF, CORS parsing, token GC, prompt injection, etc. |

---

## 0a. Remediation status (updated 2026-06-25)

Fixes were applied for everything except **C1** (the owner has decided not to publish `.git`, accepting the history-leak risk — rotation/purge remains advisable if that ever changes). All 600 backend tests pass; new tests were added per item.

**Fixed**
- **C2 / M5 / M3** — `APP_ENV` + `app/config_validation.py::validate_runtime_config()` (called at the top of `main.py`): in production it **refuses to boot** on the dev/short `JWT_SECRET`, non-secure cookies, or a wildcard CORS origin, and warns when `WORKERS>1` uses the in-memory limiter. Tests: `tests/unit/test_config_validation.py`.
- **H1** — `app/infrastructure/request_scoped_usage_tracker.py` (contextvars) replaces the shared in-process tracker; `MatchOffersWithAiUseCase.execute` opens a fresh scope (`begin()`) before scoring. Concurrent matches no longer cross-attribute tokens. Tests: `tests/unit/infrastructure/test_request_scoped_usage_tracker.py`, plus a use-case scope test.
- **H2** — reset tokens are now bound to `token_version` (single-use; a completed reset invalidates the link even within TTL); verification links are single-use (already-verified → `409`). Tests in `test_auth_use_cases.py`, `test_auth_routes.py`, `test_jwt_password_reset_token_service.py`.
- **M1** — `/auth/register` is rate-limited per `(IP, email)`. Test: `test_register_is_throttled_after_repeated_attempts`.
- **M4** — `SecurityHeadersMiddleware` adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, a strict `Content-Security-Policy`, and HSTS (when cookies are Secure). Tests: `tests/api/test_security_headers.py`.
- **M6 / L7** — request schema bounds: `offers_limit` (1–200), candidate `summary`/`skills`/`projects`/`experience` caps, and `Skill.rating` (1–5) so bad input is a clean `422` not a `500`.
- **L3** — `CORS_ORIGINS` entries are now stripped/blank-dropped.
- **L6** — scoring prompt hardened to treat candidate/offer text as untrusted data, not instructions.
- **L8** — `SmtpEmailSender` rejects CR/LF in `to`/`subject` (header-injection defense-in-depth).
- **L4** — `refresh_tokens` rows are now garbage-collected: `RefreshTokenRepository.delete_expired()` (real DELETE in the Postgres adapter, no-op default elsewhere) is swept opportunistically by `RefreshTokenService.rotate()` at most once per hour, and is also exposed as `purge_expired()` for a scheduled job. Bounds previously-unbounded table growth. Tests: `tests/unit/application/test_refresh_token_service.py`.
- **Login timing enumeration** (additional hardening, beyond the report's L1) — `AuthenticateUserUseCase` now runs a verify against a throwaway hash when the email is unknown, so a missing account costs the same time as a wrong password and login response timing can't be used to discover registered emails. Test in `test_auth_use_cases.py`.
- **Cleanup** — removed dead config (`USER_PROFILE_PATH`, `SESSION_TTL_DAYS`) and the dead `MarkdownUserProfileRepository` (obsolete since the move to multi-tenant Postgres) plus its integration test; corrected the inaccurate `BudgetExceededError` message; fixed a pre-existing time-bomb test in `test_jwt_verification_token_service.py` (hardcoded date + real-clock verify) that fails once wall-clock passes the token's expiry.

**Deferred (by design / needs infrastructure)**
- **C1** — accepted by owner (no `.git` publication). Rotation + history purge still recommended if that changes.
- **M2** — the budget check-then-act race is only fully closable with a shared reservation/pre-charge store (same class of problem as M3's limiter). Per-user token accounting + the org-spend backstop remain as guards; flagged for a shared-store follow-up.
- **L1** — register `409` (email-taken) enumeration is an accepted registration UX trade-off.
- **L2** — login/refresh CSRF (low impact) left as-is.

---

## 1. CRITICAL

### C1 — Live secrets and PII committed to git history

**Evidence (confirmed):**
- `.env` was added in commit `4c35081`, present through `8b77a00`, removed in `aff9efe`. It is now correctly git-ignored (`.gitignore`) and docker-ignored, **but it remains in history**.
- The committed `.env` blob contains (values masked here):
  - `GEMINI_API_KEY` — a real 53-char key (`AQ.…`)
  - `POSTGRES_PASSWORD` — `password` (8 chars)
  - `POSTGRES_USER` — `admin`
  - `DATABASE_URL` — full connection string **with the password inline** (109 chars)
- `DATA/user_profile.md` (PII) is also in history (commits `aff9efe`, `f18be60`, `e87b4fc`).
- `RAPORTS/secret_rotation_checklist.md` and `RAPORTS/production_todo.md` already acknowledge this and state the **Gemini key and Postgres password are still the leaked values** (only the OpenAI key was rotated).

**Impact:** Anyone with repo (or history) access — and anyone who ever saw the repo if it was pushed to a remote — has a working Gemini API key (financial abuse against the owner's quota) and the database credentials. If the DB is network-reachable with those credentials, this is full data compromise.

**Recommendation (order matters):**
1. **Rotate first** — the Gemini key and the Postgres password/`DATABASE_URL` are compromised; rotation is the only thing that neutralizes them. Follow `secret_rotation_checklist.md` Part 1.
2. **Then purge history** (`git filter-repo --invert-paths --path .env --path DATA/user_profile.md`) and force-push; everyone re-clones. (Part 2 of the checklist.)
3. Move secrets to a platform secret manager / injected env for the deploy target (already on the production TODO).
4. Add a pre-commit secret scanner (`gitleaks` / `detect-secrets`) to prevent recurrence — currently nothing blocks a re-commit.

> The runbook already exists; this report's contribution is to **confirm the leak is real and still live** and to raise it to the top of the production blocker list.

---

### C2 — Default `JWT_SECRET` in a public repo with no production guard

**Location:** `app/config.py:47`
```python
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-change-me-0123456789abcdef")
```
This single secret signs **session tokens** (`JwtTokenService`), **email-verification tokens**, and **password-reset tokens**.

**Impact:** If the app is ever started in production without `JWT_SECRET` set, it falls back to a hard-coded value that is **publicly visible in this repository**. An attacker who knows it can:
- Forge a session JWT for any `user_id` with any `token_version` → **complete authentication bypass / account takeover of every account**.
- Mint valid password-reset and email-verification tokens for any account.

There is **no fail-fast check** (confirmed: no `sys.exit`/`RuntimeError`/prod-mode guard references the secret). A misconfigured deploy silently runs insecure.

**Recommendation:**
- At startup, **refuse to boot** if `JWT_SECRET` equals the dev default (or is shorter than, say, 32 bytes) unless an explicit `ENV=dev`/`DEBUG` flag is set. Fail closed.
- Consider deriving/holding **separate secrets** for session vs verification vs reset tokens (defense in depth — see L5).
- Document the minimum entropy and generation command (`python -c "import secrets;print(secrets.token_urlsafe(48))"`).

---

## 2. HIGH

### H1 — Cross-tenant token-usage misattribution → per-user budget bypass

**Location:** `main.py:170` (single shared `_in_memory_tracker = InMemoryModelUsageTracker()`), consumed in `app/application/use_cases.py:227` (`_persist_usage` → `self._usage_tracker.flush()`), recorded in `app/infrastructure/llm_scoring_strategy.py:177` (`_record_usage`). Tracker impl: `app/application/ports.py:54`.

**The defect:** There is exactly **one** usage tracker instance for the whole process. `MatchOffersWithAiUseCase.execute` scores offers concurrently (`asyncio.run(self._score_concurrently(...))`, up to `AI_MATCH_CONCURRENCY=10`), each scoring appending to the shared tracker. After scoring, `_persist_usage(user_id)` calls `flush()`, which **drains every record currently in the tracker** and stamps them **all** with the *calling* request's `user_id`.

FastAPI runs these sync endpoints in a threadpool, so two users' AI matches overlap in the same process. The result:
- User B's expensive token usage can be flushed and attributed to **User A** (whoever calls `flush()` first), or split arbitrarily.
- Per-user budgets are computed from `model_usage` (`TokenAccountingSpendProvider`), so **a user can stay under their own budget while their real spend lands on another tenant**, and an innocent tenant can be pushed over budget by someone else's traffic.

This is a **multi-tenant integrity violation and a budget-enforcement bypass**, not merely an accounting nicety. (`production_todo.md` lists it as "tech debt"; from a security standpoint it is a High-severity isolation bug.)

**Recommendation:** Make usage request-scoped. Either:
- Carry usage on the returned `MatchScore`/result object (and stop the `CachingAiScorer` from caching usage), or
- Use a `contextvars`-based tracker bound per request, or
- Instantiate a fresh tracker per `execute()` call and pass it into the scorer for that call only.

---

### H2 — Password-reset and email-verification tokens are replayable for their entire TTL

**Location:** `app/infrastructure/jwt_password_reset_token_service.py` (and `jwt_verification_token_service.py`); flow in `app/application/auth_use_cases.py:233` (`ResetPasswordUseCase`).

**The defect:** Reset/verification tokens are **stateless JWTs** with no server-side single-use tracking. `ResetPasswordUseCase` bumps `token_version` (which invalidates *sessions*) but the **reset token itself does not encode `token_version`** and is never recorded as consumed. So `verify()` keeps accepting the same token until `exp`.

The code comment claims a reset link "works exactly once in practice because the first use bumps the user's token_version" — **this reasoning is incorrect.** `token_version` gates session JWTs, not the reset token. The reset token remains valid for the full `PASSWORD_RESET_TTL_HOURS` (default 1h).

**Impact:** An attacker who captures a reset link (shoulder-surf, proxy/referer leak, the `ConsoleEmailSender` dev log, browser history, mail forwarding) can **re-reset the victim's password even after the victim already used the link** — within the TTL window — taking over the account. The email-verification token has the same replay property (lower impact: it re-verifies + auto-logs-in).

**Recommendation:**
- Make these tokens **single-use server-side**: store a `jti` (or token hash) and reject on second use, or bind the token to `token_version` and reject when stale, or store a `password_reset_at`/nonce on the user and require it to match.
- Shorten the reset TTL further and ensure `ResetPasswordUseCase` also revokes refresh families (it does call `revoke_user` at the route layer — good — but the token replay remains).

---

## 3. MEDIUM

### M1 — No rate limiting on `/auth/register` (email bombing + CPU DoS)

**Location:** `app/presentation/api/auth.py:207` (`register`); confirmed no limiter on any data route either.

`/auth/register` (a) sends a confirmation email to the **submitted address** and (b) runs an Argon2id hash (deliberately CPU-expensive). Neither is throttled.

**Impact:**
- **Email bombing:** an attacker scripts registrations for `victim@example.com` (and variations) to flood a victim's inbox with "confirm your account" mail and burn the SMTP reputation/quota.
- **CPU DoS:** a burst of registrations ties up worker threads in Argon2 hashing.

**Recommendation:** Apply the existing `RateLimiter` to `/auth/register` keyed per `(IP)` and per `(email)` (reuse the `forgot:` pattern). Consider a global registration cap. Also rate-limit/queue the expensive `/offers/match/ai` per user beyond the budget gate.

### M2 — Budget gate is check-then-act and fail-open by default

**Location:** `app/application/use_cases.py:202-210`; defaults `BUDGET_FAIL_CLOSED=false` (`app/config.py:77`).

The budget is checked **before** scoring against already-persisted usage; the current request's cost is persisted only **after** it completes. So:
- A single request always proceeds if prior usage `< limit`, then overshoots by one request's cost.
- Under concurrency, N simultaneous requests all observe "under limit" and all proceed (TOCTOU race) → overspend by ~N requests.
- With `fail_closed=false` (default) and no admin key configured, `OrgSpendBackstop` returns `used_usd=None` and **never blocks**; the only real cap is the per-user token accounting, which the race above defeats.

Combined with **H1**, a user can both overshoot and shift the cost onto other tenants → financial DoS against the owner's provider bill.

**Recommendation:** Reserve/debit budget before dispatch (pre-charge an estimate, reconcile after), or serialize per-user AI matches, or add a per-user concurrency cap. Consider defaulting `BUDGET_FAIL_CLOSED=true` for production.

### M3 — Per-process in-memory rate limiter defeated by multiple workers

**Location:** `app/infrastructure/in_memory_rate_limiter.py`; `WORKERS` (`app/config.py:69`).

The login/forgot-password throttle lives in process memory. The code/comments correctly note this is single-worker-only, but **nothing enforces it**: setting `WORKERS>1` (supported in `main.py:402`) silently splits the counter per worker, multiplying the effective brute-force allowance by the worker count. The fixed-window design also allows up to `2×max_attempts` across a window boundary.

**Recommendation:** For any multi-worker / multi-instance deploy, back the `RateLimiter` with a shared store (Redis). At minimum, log a loud warning (or refuse to start) when `WORKERS>1` with the in-memory limiter.

### M4 — No security response headers

**Location:** `main.py` (middleware stack) — only `CORSMiddleware` is registered.

No `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`, or `Content-Security-Policy` is emitted by the API, and `frontend/src/index.html` has no CSP meta (confirmed). While the API is JSON, missing HSTS and nosniff are real gaps, and the SPA has no CSP backstop against injected script.

**Recommendation:** Add a small middleware setting HSTS (prod/HTTPS), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and a restrictive CSP for the frontend (served via the web server / reverse proxy).

### M5 — Insecure cookie defaults with no production enforcement

**Location:** `app/config.py:61-62` (`COOKIE_SECURE=false`, `COOKIE_SAMESITE=lax` defaults); applied in `app/presentation/api/auth.py:140-170`.

Sensible for local dev, but there is **no guard** ensuring `COOKIE_SECURE=true` (and `SameSite=None` for cross-site) in production. A prod deploy that forgets these env vars will transmit session/refresh cookies over plaintext-eligible, non-secure cookies.

**Recommendation:** Tie cookie hardening to an explicit environment flag and fail-fast (or warn loudly) if running in production with `COOKIE_SECURE=false`. Document the cross-site prod combo (`COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`) as mandatory.

### M6 — Unbounded work in the non-AI match path

**Location:** `app/application/use_cases.py:96-101` (`_load_candidates` → `OfferRepository.list_offers()`), `app/infrastructure/postgres_offer_repository.py:20` (`select(OfferRow)` with no limit), schema `app/presentation/api/schemas.py:147` (`offers_limit: int | None`, unbounded).

`/offers/match` loads the **entire** offers table (with `selectin` salary joins) into memory and scores every row in Python on each request. `offers_limit` only trims the *output*; it doesn't bound the work. The candidate profile (skills/projects/experience lists) is also unbounded.

**Impact:** Authenticated DoS — memory/CPU spike per request that grows with the offers table; concurrent calls amplify it.

**Recommendation:** Push filtering/pagination into SQL for the match path too (as `browse_offers` already does), cap candidate-collection sizes in the schema, and bound `offers_limit`.

---

## 4. LOW / INFORMATIONAL

- **L1 — User enumeration.** `/auth/register` returns `409 "Email already registered"` (`auth.py:219`) and `/auth/login` returns `403 "Please confirm your email"` for a correct-but-unverified credential pair (`auth.py:272`) — both reveal account existence. `forgot-password` and the generic login `401` are correctly enumeration-resistant. Accept the register tradeoff consciously; consider neutral messaging where feasible.
- **L2 — Login / refresh CSRF.** Public auth endpoints carry no CSRF guard (correct — no session yet), but this enables *login CSRF* (forcing a victim into the attacker's session). `/auth/refresh` (`auth.py:327`) also has no CSRF guard; the comment relies on `SameSite`, but in cross-site prod (`SameSite=None`) the refresh cookie *is* sent cross-site. Impact is low (it only rotates the victim's own session and the response is unreadable cross-origin), but consider a CSRF token on refresh and a signed "state" on login.
- **L3 — CORS parsing.** `CORS_ORIGINS.split(",")` (`app/config.py:39`) doesn't `strip()` entries, so `"a.com, b.com"` yields a non-matching `" b.com"`. A frustrated operator may "fix" this with `*`, which with `allow_credentials=True` is a serious misconfiguration. Strip + validate origins; reject `*` when credentials are allowed.
- **L4 — Refresh-token table grows unbounded.** Expired/consumed `refresh_tokens` rows are never garbage-collected (`postgres_refresh_token_repository.py`). Add a periodic purge of expired rows.
- **L5 — Single secret for three token types.** Session, verification, and reset tokens all use `JWT_SECRET`. Substitution is prevented by the `purpose` claim and the session token's required `ver` claim (good — see §6), but one secret compromise breaks all three. Consider per-purpose secrets.
- **L6 — LLM prompt injection.** Scraped offer descriptions and user-supplied profile text are interpolated into the scoring/translation prompts (`llm_scoring_strategy.py:194`). Output is constrained (`rate` 1–5 via `output_type=AgentScore`), limiting blast radius, but `pros`/`cons`/`rate_reason` are free text echoed to the UI. Angular auto-escapes (no `innerHTML`/`bypassSecurityTrust` found — good), so no stored XSS today; still, treat model output as untrusted and keep escaping. A malicious offer can bias its own score.
- **L7 — Domain `ValueError` surfaces as 500.** `SkillSchema.rating` is an unbounded `int` in the schema, but `Skill.__post_init__` enforces 1–5 (`app/domain/entities.py:11`). Invalid input therefore raises `ValueError` inside the route → generic `500` instead of a `422`. Validate bounds in the Pydantic schema (`Field(ge=1, le=5)`) so clients get a proper validation error.
- **L8 — Email header injection surface.** `SmtpEmailSender` sets `To`/`Subject` from inputs (`smtp_email_sender.py:35`). Currently safe because addresses pass `EmailStr` and subjects/bodies are app constants, but if these ever take free user input, `EmailMessage` header handling must be reconfirmed. Note for defense in depth.

---

## 5. Code smells, inefficiency, dead code

**Dead code / unused:**
- `app/infrastructure/markdown_profile_repository.py` — `MarkdownUserProfileRepository` is **not wired anywhere** in `app/` or `main.py` (only referenced by tests). Superseded by `PostgresUserProfileRepository` under multi-tenancy. Remove or clearly mark as legacy.
- `app/config.py:9` `USER_PROFILE_PATH` — defined, never used (the markdown repo it fed is dead).
- `app/config.py:48` `SESSION_TTL_DAYS` — defined, never used (sessions use `ACCESS_TOKEN_TTL_MINUTES`). Misleading; remove.

**Inefficiency:**
- `get_current_user` (`auth.py:108`) performs a DB `get_by_id` on **every authenticated request**. Correct (enables `token_version` revocation), but consider a short cache if it becomes hot.
- `_load_candidates` re-loads the whole offers table for both match paths (see M6); the AI path also full-loads then ranks in Python before taking the top N.
- `DEFAULT_BUDGET_USD` reads a `DAILY_BUDGET_USD` fallback (`config.py:16`) — naming drift between "default" and "daily"; the value is no longer daily. Rename for clarity.

**Style / clarity:**
- `main.py` import block is large and ungrouped; the `_disable_tracing(model)` / `configure_sdk` plumbing ignores its `model` argument and only disables tracing — the abstraction reads heavier than what it does. Consider simplifying now that per-model clients are built in `build_chat_model`.
- The incorrect comment in `JwtPasswordResetTokenService` (and `auth_use_cases.ResetPasswordUseCase`) about reset links being "exactly once" should be corrected once H2 is addressed — it currently documents a security guarantee that does not hold.

---

## 6. Positive controls (verified — keep these)

- **Password hashing:** Argon2id via `argon2-cffi` (`argon2_password_hasher.py`), OWASP-recommended; verify failures are swallowed safely.
- **Session storage:** access + refresh cookies are `httpOnly`; CSRF cookie is intentionally readable; **no tokens in `localStorage`/`sessionStorage`** (confirmed in frontend).
- **CSRF:** double-submit with `secrets.compare_digest` constant-time check (`auth.py:129`).
- **Refresh tokens:** rotation with reuse detection that burns the whole family (`refresh_tokens.py`), **hash-only** persistence (SHA-256), family/user revocation on logout/password change.
- **Token separation:** `purpose` claim on verification/reset tokens + required `ver` claim on session tokens prevents cross-substitution even under a shared secret.
- **Revocation:** `token_version` bump invalidates all sessions on password change/reset.
- **SQL:** all queries use SQLAlchemy Core/ORM with bound parameters incl. `LIKE` terms — **no SQL injection found** (`postgres_offer_repository.py`, repos).
- **Tenant isolation:** every data route derives `user.id` from the authenticated session; **no endpoint accepts a client-supplied `user_id`** → no IDOR found. AI-score cache key includes the full candidate, so no cross-tenant cache bleed.
- **Error handling:** global handler logs server-side and returns a generic 500 (`error_handlers.py`) — no stack-trace/DB-detail leakage.
- **Login throttling:** per `(IP, email)`, only wrong-credential attempts count, success resets, `429` + `Retry-After` (within the single-worker caveat of M3).
- **Transport bounds:** outbound LLM calls have timeouts; LLM base URLs are hard-coded (no SSRF surface from user input).
- **Container:** runs as non-root `appuser`, `.env` excluded via `.dockerignore`, healthcheck present.

---

## 7. Prioritized remediation order

1. **C1** — rotate the Gemini key + Postgres password now; then purge git history. *(blocker)*
2. **C2** — fail-fast on default/weak `JWT_SECRET`; generate a strong one per environment. *(blocker)*
3. **H2** — make reset/verification tokens single-use server-side. *(blocker for password-reset feature)*
4. **H1** — request-scope token-usage accounting (fixes budget integrity).
5. **M2 / M3 / M1** — budget pre-charge + per-user AI concurrency cap; shared-store rate limiter (or guard `WORKERS>1`); rate-limit registration.
6. **M5 / M4** — enforce secure cookies in prod; add security headers + CSP.
7. **M6** + Low items + dead-code cleanup.

*No code was changed during this audit, per instructions.*
