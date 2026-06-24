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
- Every API route is gated except `/health`, `/auth/register`, `/auth/login`. Sessions are a JWT in an **httpOnly cookie** (`access_token`) plus a readable `csrf_token` cookie; state-changing requests must echo it in an `X-CSRF-Token` header (double-submit CSRF). Registration auto-logs-in. `token_version` in the JWT enables revocation/logout-everywhere.
- Backend: `app/presentation/api/auth.py` (public/private routers, `get_current_user` + `verify_csrf` guards) wired in `main.py` via `include_router(router, dependencies=[...])`; ports/use cases in `app/application`; `Argon2PasswordHasher` + `JwtTokenService` adapters.
- Frontend: `core/services/auth.service.ts`, `core/interceptors/auth.interceptor.ts` (sends cookies + CSRF header, redirects to /login on 401), `core/guards/auth.guard.ts`.
- Required env: `JWT_SECRET` (override the dev default in prod). Cross-site prod also needs `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none`.

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

