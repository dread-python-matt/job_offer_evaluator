# Job Offers Evaluator - Claude Instructions

## Source of Truth

README.md is the project map. Read it first for:

* project purpose
* architecture
* setup
* API reference
* configuration
* authentication
* data model
* frontend structure

This file defines how Claude should work in this repository.

Do not duplicate README-level documentation here. If details are needed, inspect README.md, code, tests, migrations, docs, or ISSUES.

## Project Summary

This is a Python/FastAPI backend with a separate Angular frontend.

The app matches job offers to a user's profile and optionally scores fit with an LLM. Backend and frontend are separate processes and communicate over HTTP with CORS and cookie-based sessions.

## Stack

* Backend: Python 3.13, FastAPI, uv, pytest, ruff
* Frontend: Angular standalone components, Angular Material, npm
* Persistence: PostgreSQL, SQLAlchemy, Alembic
* Architecture: Clean Architecture / Hexagonal Architecture
* Workflow: TDD-first for behavior changes

## Required Skills

Use these project skills when relevant:

* `/tdd`
* `/clean-ddd-hexagonal`
* `/clean-code`
* `/fastapi`
* `/angular-component`

## Repository Orientation

Start with these files when investigating behavior:

* `README.md` — project map
* `main.py` — composition root and dependency wiring
* `app/presentation/api/routes.py` — main API routes
* `app/presentation/api/auth.py` — auth routes and guards
* `app/application/ports.py` — application ports
* `tests/` — expected behavior and regression coverage
* `alembic/versions/` — schema history
* `frontend/` — Angular app

## Key Commands

Run exactly one command per tool call.

Backend:

```bash
uv sync
```

```bash
uv run ruff check
```

```bash
uv run ruff format
```

```bash
uv run pytest
```

```bash
uv run mypy
```

```bash
uv run alembic upgrade head
```

```bash
uv run python main.py
```

Frontend:

```bash
npm --prefix frontend install
```

```bash
npm --prefix frontend start
```

```bash
npm --prefix frontend run build
```

```bash
npm --prefix frontend test
```

## Command Execution Policy

Run exactly one shell command per tool call.

Do not combine commands with:

* `&&`
* `||`
* `;`
* `|`
* `|&`
* background operators
* command substitution
* multiline shell commands

Do not use `cd frontend && ...`.

Use:

```bash
npm --prefix frontend ...
```

Good:

```bash
uv run ruff check
```

```bash
uv run pytest -q
```

```bash
npm --prefix frontend run build
```

Bad:

```bash
uv run ruff check && uv run pytest -q
```

```bash
uv run ruff check 2>&1 | tail -30
```

```bash
cd frontend && npm test
```

If multiple checks are needed, run them sequentially as separate tool calls.

## Development Workflow

For non-trivial work:

1. State a concise plan.
2. Proceed without asking for confirmation unless the change is destructive, ambiguous, security-sensitive, or requires external network/spend.
3. Write or update tests first when behavior changes.
4. Implement the smallest correct change.
5. Run focused tests first.
6. Run `uv run ruff check`.
7. Run broader tests when the change affects shared behavior.
8. Update README.md and pyproject.toml when the change affects setup, tooling, dependencies, architecture, API behavior, configuration, data model, authentication flow, frontend structure, or developer workflow.
9. Summarize changed files and commands run.
10. Summarize changes with oneline git summary (or multiple when changes are major):

```text
<type>(<optional scope>): <imperative summary>
```

Allowed types:

* `feat`
* `fix`
* `refactor`
* `perf`
* `docs`
* `style`
* `test`
* `build`
* `ci`
* `chore`
* `revert`


## Coding Rules

* Follow Clean Architecture boundaries.
* Keep domain logic independent from FastAPI, SQLAlchemy, Angular, and provider SDKs.
* Keep business logic out of route handlers.
* Prefer ports in application/domain layers and adapters in infrastructure.
* Do not introduce framework-level dependencies without a clear reason.
* Use explicit types for public functions.
* Do not silently swallow exceptions.
* Prefer small, focused changes over broad rewrites.
* Follow existing patterns before adding abstractions.

## Architecture Invariants

* Dependencies point inward.
* `presentation` and `infrastructure` may depend on `application`.
* `application` may depend on `domain`.
* `domain` must not depend on FastAPI, SQLAlchemy, Angular, provider SDKs, or environment config.
* `main.py` is the composition root.
* FastAPI dependency overrides wire ports to concrete adapters.
* Tests may override use cases and ports with fakes.

## Testing Rules

* Add or update tests for behavior changes.
* For bug fixes, prefer a regression test first.
* Use focused test commands before full-suite runs.
* Do not delete failing tests unless the tested behavior is intentionally removed.
* Keep tests deterministic.
* Do not hit real provider APIs unless the test is explicitly integration-scoped and configured for that purpose.


## Documentation Updates

Update README.md when a change affects:

- setup or running the app
- architecture or dependency wiring
- API behavior
- configuration or environment variables
- authentication/session behavior
- database schema or migrations
- frontend structure or routes
- developer workflow

Do not duplicate README-level documentation in this file. Keep CLAUDE.md focused on agent instructions and invariants.

## Dependency Source of Truth

`pyproject.toml` is the source of truth for backend Python dependencies, Python version constraints, dependency groups, and tool configuration.

When a change affects Python dependencies or tooling:

- update `pyproject.toml`
- run `uv lock` only when dependency resolution must change
- run `uv sync` after dependency changes
- do not edit `uv.lock` manually
- do not install Python packages with `pip install`
- do not add dependencies that are unused or only temporarily needed
- remove dependencies from `pyproject.toml` when they are no longer used
- keep README.md consistent with `pyproject.toml` when setup or tooling changes

Before adding a dependency:

1. Check whether the project already has an equivalent dependency.
2. Prefer standard library functionality when sufficient.
3. Justify why the dependency is needed.
4. Keep runtime dependencies separate from dev/test dependencies.


  
  
