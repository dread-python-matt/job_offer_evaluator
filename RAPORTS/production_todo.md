# Production Readiness — Remaining TODO

What's still outstanding for a production deployment. The application hardening (auth,
multi-tenancy, login throttling, password change/reset, token refresh, salary/net handling)
is done in-repo; these items need a deploy-target decision, external setup, or owner action.

## Deploy-environment dependent
- [ ] **Observability** — wire metrics / tracing / error monitoring (e.g. Sentry DSN,
      OpenTelemetry endpoint). Needs provider + credentials.
- [ ] **Secrets management** — inject secrets via the platform (env), or Vault / cloud
      secrets manager. Decide per target.
- [ ] **CORS** — set `CORS_ORIGINS` to the real production origin(s); it currently
      defaults to `http://localhost:4200`.
- [ ] **Build & verify the container** on the target: `docker compose up --build`
      (image wasn't built in the hardening environment).

## Owner-only
- [ ] **Rotate leaked credentials + purge git history** — full runbook in
      `RAPORTS/secret_rotation_checklist.md`. Rotate FIRST. (The OpenAI key is already
      rotated; the **Gemini key** and **Postgres password** are still the leaked values,
      and `.env` / `DATA/user_profile.md` remain in git history.)

## Backend tech debt
- [ ] **Request-scoped usage accounting** — the in-process token-usage tracker is shared
      across requests, so two concurrent same-process AI matches can mis-attribute tokens
      (and thus per-user budget). Fix: a `contextvars` request-scoped tracker, or carry usage
      on the returned `MatchScore` (the `CachingAiScorer` must not cache usage). Makes
      per-user budgets exact.

## Optional / nice-to-have
- [ ] Coverage threshold gate in CI (CI currently runs ruff + pytest + advisory pip-audit).
- [ ] Minor: `model-usage.scss` is ~115 bytes over the 6 kB component-style budget (warning only).
