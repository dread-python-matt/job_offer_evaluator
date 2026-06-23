# QA Report — Evaluator Project

**Date:** 2026-06-22  
**Scope:** Full codebase inspection — backend, frontend, tests  
**Severity levels:** 🔴 Critical · 🟠 Major · 🟡 Minor · 🔵 Observation

---

## Backend

### Architecture & Design

**🔴 `matching.py` is a God File (248 lines, 7+ responsibilities)**

`app/domain/matching.py` conflates: domain value objects (`MatchedOffer`, `ScoreComponent`, `MatchScore`), criteria/filter value objects (`MatchCriteria`, `OfferBrowseFilters`), abstract interfaces (`OfferScorer`, `OfferFilter`, `FilterChain`), salary normalization helpers (`monthly_gross_amount`, `representative_monthly_salary`, `salary_meets_minimum`), filter predicates (`location_matches`, `tech_stack_matches`, `level_matches`, `text_matches`, `expired_matches`), and sort utilities (`sort_offers`, `sort_matched_offers`, `offer_sort_key`). This makes the file hard to navigate and couples unrelated concepts. Suggested split:

- `app/domain/scoring.py` — `MatchScore`, `ScoreComponent`, `OfferScorer`, `MatchedOffer`
- `app/domain/filters.py` — `OfferFilter`, `FilterChain`, `MatchCriteria`, predicate functions
- `app/domain/sorting.py` — sort functions and `SortBy`/`MatchSortBy` literals
- Salary normalization helpers moved to `salary_calculator.py` (they already depend on `Salary`)

---

**🔴 `ListOffersUseCase` loads all offers into memory before filtering and paginating**

`app/application/use_cases.py:83–87` — `self._offer_repository.list_offers()` fetches the entire `offers` table, then filters and slices in Python. As the scraper accumulates data this becomes a performance and memory problem. Filtering and pagination must be pushed down to SQL (`WHERE`, `LIMIT`, `OFFSET`).

The same pattern applies to `MatchOffersUseCase` and `MatchOffersWithAiUseCase` — they both call `list_offers()` to get all rows, then filter in Python. For matching this is arguably unavoidable (every offer must be scored), but trivially-filterable criteria like expired status and location should be pre-filtered at DB level.

---

**🔴 No async I/O despite FastAPI being async**

All SQLAlchemy sessions (`PostgresOfferRepository`, `PostgresModelUsageRepository`) use the synchronous `Session` and `create_engine`. All LLM calls use `Runner.run_sync`. FastAPI runs on an async event loop; blocking calls inside route handlers hold the entire loop, preventing other requests from being served concurrently. Migrate to `AsyncSession`, `create_async_engine`, and async runner.

---

**🟠 `MatchOffersWithAiUseCase` is typed against the concrete `InMemoryModelUsageTracker`**

`app/application/use_cases.py:150` — `usage_tracker: InMemoryModelUsageTracker | None = None`. The use case depends on `.flush()`, which is not part of the abstract `ModelUsageTracker` interface. This violates the Dependency Inversion Principle. Add a `Flushable` protocol or a `FlushableModelUsageTracker` abstract class and add `flush()` to the interface.

---

**🟠 `ports.py` mixes port interfaces with domain data structures and exceptions**

`app/application/ports.py` holds abstract ports (`UserProfileRepository`, `OfferRepository`, `ModelUsageRepository`, `ModelUsageTracker`, etc.), but also plain data classes (`ModelUsage`, `ModelLimits`, `ModelUsageSummary`, `ModelUsageWithLimits`) and `AiScoringError`. Data classes that are owned by the domain should live in `entities.py` or a dedicated `model_usage.py` in the domain. `AiScoringError` is a domain exception and belongs in the domain layer.

---

**🟠 `SkillBasedScorer` and `SkillFilter` duplicate `_practiced_skills` and `_weighted_ratio`**

`app/infrastructure/scoring_strategies.py:37–44` and `app/infrastructure/offer_filters.py:43–49` contain identical `_practiced_skills` static methods. `_weighted_ratio` logic is also equivalent. The comment in `SkillFilter` acknowledges this but a silent drift between the two is a real maintenance risk. Extract to a shared `_skill_weight(candidate, skills)` function in a module both can import.

---

**🟠 `salary_calculator.py` imports from `matching.py` creating a cross-domain dependency**

`app/domain/salary_calculator.py:14` — `from app.domain.matching import monthly_gross_amount`. The matching module should not be a dependency of the salary calculator. `monthly_gross_amount` operates only on `Salary` and belongs in `salary_calculator.py` or `entities.py`, not `matching.py`.

---

**🟠 Dependency injection pattern is non-standard and brittle**

`app/presentation/api/routes.py:34–67` defines stub provider functions that `raise NotImplementedError`. Real instances are wired in `main.py` via `app.dependency_overrides`. This pattern is unconventional and breaks IDE navigation, makes it impossible to run the router in isolation, and forces every test to replicate the override map. Use FastAPI's standard `Depends()` with a proper factory or a request-scoped dependency container.

---

**🟠 CORS origin is hardcoded**

`main.py:101` — `allow_origins=["http://localhost:4200"]`. This should come from a `CORS_ORIGINS` environment variable to support deployment to any environment without code changes.

---

**🟡 `PostgresModelUsageRepository` implements both `ModelUsageRepository` and `ModelUsageTracker`**

`app/infrastructure/postgres_model_usage_repository.py:10` — The class inherits from two abstract bases and `record()` simply delegates to `save()`. This conflates read/write concerns. More critically, every `.record()` call opens a DB connection and commits a transaction, which will be slow under concurrent LLM scoring. Use a batched/buffered writer or let the composite tracker absorb the write-through pattern.

---

**🟡 `main.py` confusing tracker wiring**

In `main.py:73–85`, `_in_memory_tracker` is shared between `_composite_tracker` (which also includes the DB repository) and `MatchOffersWithAiUseCase`. The `LLMScoringStrategy` is given `_composite_tracker` so it writes to both in-memory and DB. The use case is given `_in_memory_tracker` so it flushes only the in-memory side. This is correct but opaque — a future developer may easily misread or mis-wire it. Add inline comments or extract to a factory function.

---

**🟡 Custom markdown parser in `MarkdownUserProfileRepository` is fragile**

`app/infrastructure/markdown_profile_repository.py` hand-rolls section splitting, skill parsing, and project/experience parsing with regex. Deviations in whitespace, dash style, or section ordering silently lose or corrupt data with no error raised. Consider using a structured format (JSON/YAML) stored in a `.json`/`.yaml` file, or at minimum add validation and raise `ValueError` on malformed input.

---

**🟡 `NoExternalUsageProvider` is a null-object that could just be `None`**

`app/infrastructure/no_external_usage_provider.py` — a 4-line class. The `GetModelUsageSummaryUseCase` already handles `external_provider=None` explicitly. The null-object pattern is fine conceptually but adds a file for negligible benefit when `None` is already handled. If the null-object is kept, remove the `None` branch from `GetModelUsageSummaryUseCase.execute()`.

---

**🟡 `OfferBrowseFilters` `tech` field typing mismatch**

`app/domain/matching.py:80` — `tech: list[str]`. The route correctly uses `Query(default_factory=list)`, but the `ListOffersUseCase` tests (`test_use_cases.py:485`) pass `OfferBrowseFilters(tech="python")` — a `str` where `list[str]` is expected. Python won't raise at runtime but `tech_stack_matches` then iterates over individual characters of the string, producing incorrect behavior. This is both a test bug and reveals a lack of runtime validation on the dataclass.

---

**🔵 `HardcodedModelLimitsRegistry` only covers Gemini models**

`app/infrastructure/model_limits_registry.py` has no OpenAI model limits. If the provider is switched to OpenAI, all limits will return `None`. Add OpenAI entries or make the registry configurable from a YAML/JSON file.

---

**🔵 `company_from_model` is placed in `llm_scoring_strategy.py` but has wider use**

The function is imported by both `main.py` and `openai_usage_provider.py`. It is a generic utility that does not belong inside the LLM scoring strategy. Move it to a shared `infrastructure/llm_utils.py`.

---

## Frontend

### Architecture & Design

**🟠 `MatchedOfferRow` interface and `toRow()`/`scoreClass()` methods are duplicated across two components**

`match-offers.ts:23–34` and `ai-match-offers.ts:22–33` define the identical `MatchedOfferRow` interface. The `toRow()` and `scoreClass()` private methods are also byte-for-byte identical. Extract to a shared `offer-row.ts` utility file or a `OfferResultsComponent` reusable component.

---

**🟠 `ApiService.matchOffers` and `matchOffersWithAi` take too many positional parameters**

`api.service.ts:31–53` — nine positional parameters; `matchOffersWithAi` has eleven. Callers must count argument positions carefully. Replace with an options interface (`MatchOffersOptions`) to make call sites self-documenting and easier to extend.

---

**🟠 No cancellation of in-flight HTTP requests**

`browse-offers.ts:104–117` — `loadPage()` fires an HTTP request on every page/filter change with no `takeUntil` or `switchMap` to cancel the prior request. Fast interactions (rapid pagination, quick filter changes) will cause out-of-order response races and flicker. Use `switchMap` on a dedicated trigger stream, or unsubscribe in `ngOnDestroy`.

Same issue in `match-offers.ts:124` and `ai-match-offers.ts:122` — the `search()` method does not cancel any prior in-flight request.

---

**🟠 Routes are eagerly loaded**

`app.routes.ts` imports all five feature components at the top level. With Angular's standalone components, lazy loading is trivial:
```ts
{ path: 'profile', loadComponent: () => import('./features/profile/profile').then(m => m.Profile) }
```
Eager loading increases the initial bundle and time-to-interactive.

---

**🟡 `AiMatchOffers` is missing the `score-recent` sort option that `MatchOffers` has**

`match-offers.ts:36–54` defines `score-recent` as a valid `MatchSortOption`. `ai-match-offers.ts:35–46` does not include it despite the backend supporting `score_recent` for the AI endpoint. This is a feature gap with no justification.

---

**🟡 Error handling is inconsistent between components**

`match-offers.ts` uses `MatSnackBar` for errors. `ai-match-offers.ts` uses a `signal<string | null>` shown inline. Pick one approach and apply it consistently. The inline signal approach is better for recoverable errors that the user should be able to see while retrying.

---

**🟡 `OfferFilters.tech` is typed as `string | null` limiting to one tech filter**

`profile.model.ts:83` — `tech: string | null`. The match-offers component supports a `string[]` chip list for tech filters, but browse-offers uses a plain text input (single string). The backend accepts `list[str]`, so the browse-offers filter silently passes at most one tech. Align with the match-offers chip pattern and update the type to `string[] | null`.

---

**🟡 Profile form has insufficient validation**

`profile.ts` — `summary`, `company`, `description`, `date_from`, `date_to`, and `repository_link` have no `Validators.required`. A user can save a profile with empty or blank required fields, which will produce poor match results silently.

---

**🟡 `MatSnackBar` undo subscription is never explicitly unsubscribed**

`profile.ts:231–233` — `ref.onAction().subscribe(undo)`. If the component is destroyed before the snack bar dismisses, the subscription will try to manipulate a destroyed form. Pipe with `takeUntilDestroyed()` or use the `DestroyRef` injection token.

---

**🔵 `Salary.net_monthly` is missing from the frontend model**

`profile.model.ts:31–37` — the `Salary` interface does not include `net_monthly: number | null`, yet the backend returns it and the browse-offers and match-offers pages could display it. Add the field to the model and display it in the salary label.

---

**🔵 `formatDate` in `profile.ts` duplicates date parsing logic**

`profile.ts:207–212` and `profile.ts:219–224` both parse `YYYY-MM` strings. Extract to a `parseYearMonth`/`formatYearMonth` utility in `core/utils/date-format.ts`.

---

## Tests

### Test Quality & Coverage

**🔴 `test_use_cases.py:485` passes wrong type for `tech` field**

`filters=OfferBrowseFilters(tech="python")` — a bare string is passed where `list[str]` is expected. The test accidentally passes because `tech_stack_matches` iterates over the string and individual characters like `'p'`, `'y'`, `'t'`, `'h'`, `'o'`, `'n'` happen to be substrings of `"Python"`. The correct call is `OfferBrowseFilters(tech=["python"])`. This is both a test bug and a false green that hides the real filtering behaviour.

---

**🟠 Test utilities defined in a test module are imported by another test module**

`test_routes.py:38–43` imports `FakeModelUsageRepository`, `FakeOfferRepository`, `FakeUserProfileRepository`, and `ScoreByLinkScorer` directly from `tests/unit/application/test_use_cases.py`. Test files should not be each other's dependencies. Extract shared fakes to `tests/conftest.py` or `tests/fakes.py`.

---

**🟠 Tests access private attributes of the system under test**

`test_llm_scoring_strategy.py:162–168`:
```python
assert strategy._agent.model == "gpt-test-model"
assert strategy._agent is sentinel_agent
```
Tests should not depend on internal `_` attributes. Verify observable behaviour instead (e.g., what agent is called, what prompt is constructed). If the internal state must be inspectable, expose it as a read-only property.

---

**🟠 Angular component unit tests are missing**

`match-offers.spec.ts`, `ai-match-offers.spec.ts`, `browse-offers.spec.ts` are likely scaffolded stubs. None of the feature components have meaningful unit tests covering: form validation, API call arguments, result rendering, error states, loading state transitions, or filter interactions. This is the most significant coverage gap in the project.

---

**🟡 Integration tests have no visible setup/teardown or database seeding**

`tests/integration/test_postgres_offer_repository.py` and `tests/integration/test_postgres_model_usage_repository.py` presumably hit a real database. There is no evidence of a `conftest.py` with transaction rollback, schema reset, or test data seeding. Shared DB state between tests causes order-dependent failures.

---

**🟡 `company_from_model` has no unit tests**

The function in `llm_scoring_strategy.py:13–20` is tested only indirectly through the tracker tests for Gemini and GPT. There are no tests for the `claude` prefix, `o1-`/`o3-`/`o4-` prefixes, or the `"Unknown"` fallback.

---

**🟡 No tests for `MarkdownUserProfileRepository` parse edge cases**

`test_markdown_profile_repository.py` (in integration tests) likely covers the happy path. Missing: malformed skill line, missing section header, project with no tech stack, experience with missing company, duplicate section headers, empty file, encoding edge cases.

---

**🟡 No property-based tests for numerical logic**

The salary calculator, `monthly_gross_amount`, `representative_monthly_salary`, and score normalization (`overall_score`) are all pure numerical functions. These are ideal candidates for property-based testing with Hypothesis (e.g., `take_home` must always be ≤ `gross`, `overall_score` must be in `[0, 1]` for normalized inputs). Only example-based tests exist.

---

**🔵 `_build_client()` in `test_routes.py` rebuilds the `FilterChain` in every test**

`test_routes.py:71–73` — each test that calls `_build_client()` constructs the full filter chain. The `filter_chain` construction is not the thing being tested. Define a module-level default `_DEFAULT_FILTER_CHAIN` or use a fixture.

---

**🔵 No test for `sort_offers` when `sort_by=None`**

`matching.py:188–189` — the `None` guard path (`return offers` as-is) is not covered by a named test. It is exercised implicitly through the `ListOffersUseCase` tests with default `OfferBrowseFilters()`, but there is no isolated unit test for it.

---

**🔵 Missing test for `AiMatchOffers` 503 error detail display**

The backend returns `{"detail": "..."}` on 503 and the component reads `err.error?.detail`. This path has no test verifying the detail message is surfaced correctly to the user.

---

## Summary Table

| Area | Critical | Major | Minor | Observation |
|------|----------|-------|-------|-------------|
| Backend | 3 | 6 | 5 | 3 |
| Frontend | 0 | 4 | 5 | 2 |
| Tests | 1 | 3 | 5 | 3 |
| **Total** | **4** | **13** | **15** | **8** |

### Top Priorities

1. **Push filtering and pagination to SQL** — current full-table load will not scale.
2. **Migrate to async SQLAlchemy + async LLM runner** — blocking event loop under concurrent load.
3. **Fix `OfferBrowseFilters(tech="python")` type error in tests** — silent false green masking a real bug.
4. **Extract shared fakes to `conftest.py`** — test-to-test imports are a structural smell.
5. **De-duplicate `MatchedOfferRow` + `toRow()`/`scoreClass()`** — identical code in two components.
6. **Add `switchMap` / request cancellation** — prevent out-of-order responses in paginated browsing.
7. **Split `matching.py`** — reduce coupling and improve navigability.
