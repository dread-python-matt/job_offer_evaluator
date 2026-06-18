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

