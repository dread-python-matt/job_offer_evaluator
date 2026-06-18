# Job Offers Evaluator

Matches scraped job offers to a user profile based on shared tech-stack skills. A FastAPI JSON API (backend) is consumed by a standalone Angular app (frontend).

## How It Works

1. A **user profile** (summary, skills with 1–5 ratings, projects, experience) is stored as a Markdown file at `DATA/user_profile.md`, or sent inline as the `candidate` in a match request.
2. **Job offers** live in a Postgres `offers` table owned by an external scraper (this app only reads from it).
3. For each offer, a pluggable `ScoringStrategy` (the domain port) returns a `Score` with `skills_score` and `description_score` — e.g. plain skill overlap, rating-weighted overlap, or an LLM-based fit assessment. `Score.overall_score` blends them 4:1 in favor of skills, and is what's used for filtering/sorting.
4. Offers are filtered by a minimum score threshold and returned sorted by score, descending.

## Tech Stack

- Backend: Python 3.13, uv (package manager), FastAPI, SQLAlchemy + psycopg (Postgres access)
- Frontend: Angular, Angular Material
- pytest + ruff (backend), Vitest (frontend)

## Architecture

The backend follows Clean Architecture / Hexagonal style, organized in `app/`:

```
app/
├── config.py         # env/config loading
├── domain/           # Entities and matching logic — no framework dependencies
│   ├── entities.py   # Skill, Project, Experience, UserProfile, Offer
│   └── matching.py   # MatchedOffer, ScoringStrategy (abstract port only)
├── application/      # Use cases orchestrating the domain via ports
│   ├── ports.py       # UserProfileRepository, OfferRepository (abstract interfaces)
│   └── use_cases.py    # SaveUserProfileUseCase, MatchOffersUseCase
├── infrastructure/   # Adapters implementing the ports
│   ├── orm_models.py                   # SQLAlchemy ORM models
│   ├── markdown_profile_repository.py  # reads/writes DATA/user_profile.md
│   ├── postgres_offer_repository.py    # read-only adapter over the `offers` table
│   ├── scoring_strategies.py           # SkillOverlapScoringStrategy, WeightedSkillScoringStrategy
│   └── llm_scoring_strategy.py         # LLMScoringStrategy — OpenAI Agents SDK-backed fit scoring
└── presentation/     # Entry points into the application
    └── api/           # FastAPI routes + Pydantic schemas
```

Dependencies point inward: `presentation` and `infrastructure` depend on `application`, which depends on `domain`. The domain only defines `ScoringStrategy` as a port — every concrete implementation (pure or LLM-backed) lives in `infrastructure`, same as the repository adapters. The domain has no knowledge of FastAPI, Postgres, or the OpenAI SDK.

The frontend is a fully separate Angular app in `frontend/`, calling the API over HTTP — there's no shared process or mounting between the two.

```
frontend/
└── src/app/
    ├── core/
    │   ├── models/      # TypeScript interfaces mirroring app/presentation/api/schemas.py
    │   └── services/    # ApiService — HttpClient wrapper around the FastAPI endpoints
    ├── features/
    │   ├── profile/        # Profile form (summary, skills, projects, experience)
    │   └── match-offers/   # Offers limit / min score filters + results table
    ├── app.routes.ts    # /profile (default), /match-offers
    └── app.config.ts    # provideHttpClient, provideRouter, provideAnimationsAsync
```

## Setup

Requires Python 3.13, [uv](https://docs.astral.sh/uv/), and Node.js (for the Angular frontend).

```bash
uv sync
```

Copy `.env` (or create your own) with the Postgres connection details:

```
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
```

Start Postgres:

```bash
docker-compose up -d
```

Install frontend dependencies:

```bash
cd frontend && npm install
```

## Running

Backend (FastAPI, JSON API only):

```bash
uv run python main.py
```

- API docs: http://localhost:8000/docs

Frontend (Angular dev server, separate process):

```bash
cd frontend && npm start
```

- App: http://localhost:4200

The backend allows CORS requests from `http://localhost:4200` (configured in `main.py`) so the Angular dev server can call the API directly.

### API Endpoints

| Method | Path            | Description                              |
|--------|------------------|-------------------------------------------|
| POST   | `/profile`       | Save the user profile                      |
| GET    | `/profile`        | Get the saved user profile (404 if none)   |
| POST   | `/offers/match`    | List matched offers for a `candidate` (body: `candidate`, `min_score`, `offers_limit`) |

## Testing

Backend:

```bash
uv run pytest
```

- `tests/unit/` — domain entities, matching logic, use cases (no I/O)
- `tests/integration/` — Markdown profile repository, Postgres offer repository
- `tests/api/` — FastAPI route tests

Frontend:

```bash
cd frontend && npm test
```

## Development Workflow

This project follows TDD and Clean Architecture (see `CLAUDE.md`):

1. Write a plan and confirm with the user before coding.
2. Write tests first.
3. Implement the feature.
4. Run `uv run pytest` and confirm passing.
5. Update `CLAUDE.md` if new patterns emerge.
