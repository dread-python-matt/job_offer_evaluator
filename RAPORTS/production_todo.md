# Production Readiness — Remaining TODO

Items left after the backend hardening pass (see `qa2_raport.md`). These need a
deploy-target decision or external setup, so they weren't auto-implemented.

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
- [ ] **C1 — rotate leaked credentials + purge git history.** Full runbook in
      `RAPORTS/secret_rotation_checklist.md`. Do rotation FIRST.

## Deferred features / decisions
- [ ] **C2 — authentication** (static API key + Angular interceptor) before any public
      exposure. Intentionally deferred; cheap to add later.
- [x] **M3/M4 — salary standardized on NET everywhere** (browse + match): `Salary` carries
      normalized net; filter on net floor; sort by recent + net min/mid/max (asc/desc);
      display estimated net with disclaimer.
- [ ] **Profile fields to refine net accuracy** (age<26, PPK, preferred contract) — next step.

## Optional / nice-to-have
- [ ] Coverage threshold gate in CI (CI currently runs ruff + pytest + advisory pip-audit).
- [x] Frontend production environment config (L6) — `environment.prod.ts` + `angular.json`
      fileReplacements (set `apiUrl` to the API origin before a prod build).
- [ ] Minor: `model-usage.scss` is ~115 bytes over the 6 kB component-style budget (warning only).
