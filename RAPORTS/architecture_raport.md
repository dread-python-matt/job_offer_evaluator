# Architecture & Design Patterns Report

**Date:** 2026-06-23  
**Scope:** Full backend codebase (`app/`, `main.py`, `tests/`)  
**Methodology:** Read every source file; patterns mapped against GoF catalogue and functional pipeline variants.

---

## Executive Summary

The project has a sound hexagonal architecture skeleton — Ports & Adapters, Repository, Strategy, Chain of Responsibility, and Composite are all already present. The issues below are not architectural rot but rather **inconsistencies** and **missed extensions** of patterns already started. The most impactful fixes are in `main.py` (composition root), `SalaryCalculator` (Strategy), the two matching use cases (Template Method), and the dual-role repository.

---

## Patterns Already Applied Well

| Pattern | Location | Notes |
|---|---|---|
| Repository | `ports.py`, `*_repository.py` | Clean port + adapter separation |
| Strategy | `scoring.py` + `scoring_strategies.py` + `llm_scoring_strategy.py` | `OfferScorer` hierarchy |
| Chain of Responsibility | `filters.py` (`FilterChain` + `OfferFilter`) | Clean composable chain |
| Composite | `composite_model_usage_tracker.py` | Correct pattern, clean code |
| Null Object | `no_external_usage_provider.py` | Exists, but not used consistently (see #4 below) |
| Factory Function | `translation_agents.py` | `build_*_agent()` functions |

---

## Findings: Where Patterns Are Missing or Broken

---

### 1. `main.py` — Composition Root is a God Function

**File:** `main.py` (all 140 lines)  
**Pattern needed:** Abstract Factory + Builder  

`main.py` is doing all of these at module level:
- Branching on `LLM_PROVIDER` to configure the SDK (twice, lines 60–69 and 98–102)
- Manually constructing every infrastructure object
- Wiring every `dependency_overrides` by hand
- Building the FastAPI app with middleware

Adding a third LLM provider (e.g., Anthropic), a new use case, or a second environment profile means editing this file in multiple places. The `if LLM_PROVIDER == "openai" / elif LLM_PROVIDER == "gemini"` branches will grow indefinitely.

**Recommended fix:**

Introduce an `LLMProviderFactory` (Abstract Factory) that encapsulates all provider-specific wiring:

```python
class LLMProviderFactory(ABC):
    @abstractmethod
    def configure_sdk(self) -> None: ...
    @abstractmethod
    def build_scorer(self, model: str | None) -> OfferScorer: ...
    @abstractmethod
    def build_external_usage_provider(self) -> ExternalUsageProvider: ...

class OpenAIProviderFactory(LLMProviderFactory): ...
class GeminiProviderFactory(LLMProviderFactory): ...
```

Then build a `AppFactory` / Builder that takes a `LLMProviderFactory` and assembles use cases, injecting the router overrides in one place.

**Benefit:** Adding a new provider is adding one new class, not touching existing branching logic. Testable in isolation.

---

### 2. `SalaryCalculator` — Partial Strategy: Dispatch Lives Inside the Class

**File:** `app/domain/salary_calculator.py:154–230`  
**Pattern needed:** Strategy (complete extraction)

`SalaryCalculator.calculate()` branches on `ContractType` and calls private methods `_b2b`, `_employment`, `_civil`. This is the Strategy pattern with the strategies still inside the class. Every new contract type (e.g., a B2B variant with linear tax) requires modifying `SalaryCalculator` itself, violating Open/Closed.

```python
# current
class SalaryCalculator:
    def calculate(self, contract_type, gross, ...):
        if contract_type is ContractType.B2B:
            return self._b2b(...)
        if contract_type is ContractType.EMPLOYMENT:
            return self._employment(...)
        return self._civil(...)
```

**Recommended fix:**

```python
class SalaryStrategy(ABC):
    @abstractmethod
    def calculate(self, gross: float, **options) -> NetSalaryBreakdown: ...

class B2BSalaryStrategy(SalaryStrategy): ...
class EmploymentSalaryStrategy(SalaryStrategy): ...
class CivilContractSalaryStrategy(SalaryStrategy): ...

_STRATEGIES: dict[ContractType, SalaryStrategy] = {
    ContractType.B2B: B2BSalaryStrategy(),
    ContractType.EMPLOYMENT: EmploymentSalaryStrategy(),
    ContractType.CIVIL: CivilContractSalaryStrategy(),
}

class SalaryCalculator:
    def calculate(self, contract_type, gross, **opts):
        return _STRATEGIES[contract_type].calculate(gross, **opts)
```

**Benefit:** Each strategy is independently testable; adding a new contract type requires zero changes to `SalaryCalculator`.

---

### 3. `MatchOffersUseCase` vs `MatchOffersWithAiUseCase` — Duplicated Pipeline

**File:** `app/application/use_cases.py:105–197`  
**Pattern needed:** Template Method (or explicit Pipeline)

Both use cases share an identical sequence:
1. Load offers from repository
2. Pass through `filter_chain`
3. Score each offer
4. Filter by `min_score`
5. Sort by `sort_by` / `sort_order`
6. Limit by `offers_limit`

The AI use case inserts an additional pre-ranking step between 2 and 3. This shared logic is copy-pasted, meaning bug fixes or new steps (e.g., deduplication, caching) must be applied in both places.

**Recommended fix (Template Method):**

```python
class BaseMatchOffersUseCase(ABC):
    def execute(self, criteria, offers_limit, sort_by, sort_order):
        candidates = self._load_candidates(criteria)
        scored = self._score_all(candidates, criteria)
        filtered = [m for m in scored if m.score >= criteria.min_score]
        sorted_ = sort_matched_offers(filtered, sort_by, sort_order)
        return sorted_[:offers_limit]

    def _load_candidates(self, criteria):
        return [o for o in self._offer_repository.list_offers()
                if self._filter_chain.passes(o, criteria)]

    @abstractmethod
    def _score_all(self, candidates, criteria) -> list[MatchedOffer]: ...

class MatchOffersUseCase(BaseMatchOffersUseCase):
    def _score_all(self, candidates, criteria):
        return [MatchedOffer(offer=o, score=self._scorer.score(criteria.candidate, o).overall_score, ...) for o in candidates]

class MatchOffersWithAiUseCase(BaseMatchOffersUseCase):
    def _score_all(self, candidates, criteria):
        ranked = sorted(candidates, key=lambda o: self._ranking_scorer.score(...), reverse=True)
        top = ranked[:self._offers_to_score]
        return [MatchedOffer(offer=o, score=self._ai_scorer.score(...).overall_score, ...) for o in top]
```

**Benefit:** The pipeline is defined once. Adding a step (caching, logging, deduplication) touches one place.

---

### 4. `GetModelUsageSummaryUseCase` — Null Object Pattern Used Inconsistently

**File:** `app/application/use_cases.py:200–228`, `app/infrastructure/no_external_usage_provider.py`

`NoExternalUsageProvider` exists and correctly implements the Null Object pattern. However, `GetModelUsageSummaryUseCase.__init__` still accepts `external_provider: ExternalUsageProvider | None = None` and guards against it:

```python
# use_cases.py:211
if self._external_provider:
    summaries = self._external_provider.get_today_usage()
    if summaries:
        return self._enrich(summaries)
```

This `if self._external_provider` branch defeats the entire purpose of the Null Object.

**Recommended fix:**

Remove the `None` option from the constructor signature. Always require an `ExternalUsageProvider`. In `main.py`, pass `NoExternalUsageProvider()` when not configured (which is already done). The `if self._external_provider` guard is then replaced by a plain call:

```python
class GetModelUsageSummaryUseCase:
    def __init__(self, repository, limits_registry, external_provider: ExternalUsageProvider) -> None:
        ...

    def execute(self):
        summaries = self._external_provider.get_today_usage()
        if summaries:
            return self._enrich(summaries)
        return self._enrich(self._repository.get_summary())
```

**Benefit:** The use case becomes honest about its dependencies; conditional branching drops by one level.

---

### 5. `PostgresModelUsageRepository` — Dual Interface (ISP Violation)

**File:** `app/infrastructure/postgres_model_usage_repository.py:10`  
**Pattern needed:** Adapter

```python
class PostgresModelUsageRepository(ModelUsageRepository, ModelUsageTracker):
```

This class implements two unrelated interfaces. Its `flush()` returns `[]` — a stub that is semantically incorrect for a `ModelUsageTracker` (flush means "give me what you buffered"). It also means the class is used in two different roles in `main.py` (line 84: as part of `CompositeModelUsageTracker`, and line 104: as a `ModelUsageRepository`).

**Recommended fix (Adapter):**

```python
class PostgresModelUsageRepository(ModelUsageRepository):
    def save(self, usage: ModelUsage) -> None: ...
    def get_summary(self) -> list[ModelUsageSummary]: ...

class PersistingModelUsageTracker(ModelUsageTracker):
    """Adapter: wraps a repository to satisfy the ModelUsageTracker port."""
    def __init__(self, repository: ModelUsageRepository) -> None:
        self._repository = repository

    def record(self, usage: ModelUsage) -> None:
        self._repository.save(usage)

    def flush(self) -> list[ModelUsage]:
        return []  # fire-and-forget: persisted on record(), nothing to flush
```

In `main.py`:
```python
model_usage_repository = PostgresModelUsageRepository(DATABASE_URL)
persisting_tracker = PersistingModelUsageTracker(model_usage_repository)
_composite_tracker = CompositeModelUsageTracker([_in_memory_tracker, persisting_tracker])
```

**Benefit:** Each class has a single responsibility; `flush()` semantics become honest.

---

### 6. `ListOffersUseCase._matches` — Filter Chain Inconsistency

**File:** `app/application/use_cases.py:94–102`  
**Pattern needed:** Chain of Responsibility (extend existing pattern)

`MatchOffersUseCase` and `MatchOffersWithAiUseCase` both use the injected `FilterChain` to gate candidates. `ListOffersUseCase` does its own filtering by calling free functions directly:

```python
def _matches(self, offer: Offer, filters: OfferBrowseFilters) -> bool:
    return (
        expired_matches(offer, filters.include_expired)
        and location_matches(offer, filters.location)
        and salary_meets_minimum(offer, filters.min_salary)
        and tech_stack_matches(offer, filters.tech)
        and text_matches(offer, filters.search)
        and level_matches(offer, filters.level)
    )
```

Adding a new browse filter (e.g., company name filter) means modifying this method, while the matching pipeline is modified by adding a new `OfferFilter` class. Two different extension mechanisms for the same concept.

**Recommended fix:**

Introduce a `BrowseFilterChain` factory (or method on `OfferBrowseFilters`) that builds a `FilterChain`-compatible structure from browse criteria:

```python
class TextFilter(OfferBrowseFilter):
    def passes(self, offer: Offer, filters: OfferBrowseFilters) -> bool:
        return text_matches(offer, filters.search)

class TechStackBrowseFilter(OfferBrowseFilter):
    def passes(self, offer: Offer, filters: OfferBrowseFilters) -> bool:
        return tech_stack_matches(offer, filters.tech)

# BrowseFilterChain composed in main.py / ListOffersUseCase constructor
```

Or simply accept a `Callable[[Offer, OfferBrowseFilters], bool]` chain built from the existing predicates. The key is that the extension point is uniform.

**Benefit:** Adding a browse filter requires adding one class, not editing `_matches`.

---

### 7. `llm_utils.company_from_model` — Chain of `startswith` Instead of Registry

**File:** `app/infrastructure/llm_utils.py:1–8`  
**Pattern needed:** Registry (lookup table)

```python
def company_from_model(model: str) -> str:
    if model.startswith("gemini"):
        return "Google"
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "OpenAI"
    if model.startswith("claude"):
        return "Anthropic"
    return "Unknown"
```

Adding a new provider means modifying the function body. Also, `company_from_model` is a utility that lives in `infrastructure/` but is called from `application/ports.py`-level logic — a layering smell.

**Recommended fix:**

```python
_COMPANY_REGISTRY: list[tuple[str | tuple[str, ...], str]] = [
    ("gemini", "Google"),
    (("gpt-", "o1-", "o3-", "o4-"), "OpenAI"),
    ("claude", "Anthropic"),
]

def company_from_model(model: str) -> str:
    for prefix, company in _COMPANY_REGISTRY:
        if model.startswith(prefix):
            return company
    return "Unknown"
```

Or use a `dict` with a helper to iterate prefixes. The registry can be loaded from config or environment as the provider list grows.

**Benefit:** Adding a provider requires adding one entry to `_COMPANY_REGISTRY`; no function body changes.

---

### 8. `sort_matched_offers` — Branching Sort Key Without Strategy

**File:** `app/domain/sorting.py:36–56`  
**Pattern needed:** Strategy (function registry)

```python
def sort_matched_offers(matched_offers, sort_by, sort_order):
    if sort_by == "score":
        return sorted(..., key=lambda m: m.score, ...)
    if sort_by == "score_recent":
        return sorted(..., key=lambda m: (m.score, m.offer.published or ""), ...)
    # fallthrough for "salary" and "recent" via offer_sort_key
```

Each new `MatchSortBy` literal requires adding an `if` branch here.

**Recommended fix:**

```python
_MATCH_SORT_KEY: dict[MatchSortBy, Callable] = {
    "score":        lambda m: (m.score,),
    "score_recent": lambda m: (m.score, m.offer.published or ""),
    "salary":       lambda m: (representative_monthly_salary(m.offer) or -1,),
    "recent":       lambda m: (m.offer.published or "",),
}

def sort_matched_offers(matched_offers, sort_by, sort_order):
    key = _MATCH_SORT_KEY[sort_by]
    with_value = [m for m in matched_offers if key(m) != (-1,)]
    without_value = [m for m in matched_offers if key(m) == (-1,)]
    with_value.sort(key=key, reverse=(sort_order == "desc"))
    return with_value + without_value
```

**Benefit:** Adding a new sort mode is a dict entry; the function body is stable.

---

### 9. `LLMScoringStrategy.__init__` — Construction Mixed with Business Logic

**File:** `app/infrastructure/llm_scoring_strategy.py:40–59`  
**Pattern needed:** Factory Method (class method)

`LLMScoringStrategy.__init__` optionally builds an `Agent` when none is provided:

```python
self._agent = agent or Agent(
    name="Offer Fit Scorer",
    model=model,
    instructions=_INSTRUCTIONS,
    output_type=AgentScore,
)
self._model = model or (getattr(agent, "model", None) or "")
```

The `_model` field is computed by probing `agent.model` via `getattr`, which is fragile — it works only by convention. Also, if both `model` and `agent` are passed, `model` is ignored for construction but stored separately, creating a potential inconsistency in `_run_tracked`.

**Recommended fix (Factory Method):**

```python
class LLMScoringStrategy(OfferScorer):
    @classmethod
    def create(cls, model: str | None = None, **kwargs) -> "LLMScoringStrategy":
        agent = Agent(
            name="Offer Fit Scorer",
            model=model,
            instructions=_INSTRUCTIONS,
            output_type=AgentScore,
        )
        return cls(agent=agent, model=model or "", **kwargs)

    def __init__(self, agent: Agent, model: str, ...) -> None:
        # all args required; no optional construction logic
        self._agent = agent
        self._model = model
        ...
```

In production use `LLMScoringStrategy.create(model=SCORING_AGENT_MODEL, ...)`. In tests inject `agent` and `model` directly.

**Benefit:** Removes fragile `getattr`; separates object construction from object use; test injection is clean.

---

### 10. `CalculateNetSalaryUseCase` — Self-Constructing Optional Dependency

**File:** `app/application/use_cases.py:53–54`  
**Pattern needed:** Dependency Injection (composition root responsibility)

```python
def __init__(self, calculator: SalaryCalculator | None = None) -> None:
    self._calculator = calculator or SalaryCalculator()
```

A use case constructing its own dependency is a violation of DI discipline — the use case can never be given a substitute without explicitly passing one, and the composition root's responsibility leaks into the application layer.

**Recommended fix:**

```python
def __init__(self, calculator: SalaryCalculator) -> None:
    self._calculator = calculator
```

In `main.py`:
```python
calculate_salary_use_case = CalculateNetSalaryUseCase(SalaryCalculator())
```

**Benefit:** The use case is a pure consumer; construction is the composition root's job.

---

## Pattern Opportunity Map

| # | Location | Pattern | Priority |
|---|---|---|---|
| 1 | `main.py` | Abstract Factory + Builder | High |
| 2 | `salary_calculator.py` | Strategy (extract per-contract) | High |
| 3 | `use_cases.py` (both match UCs) | Template Method | High |
| 4 | `use_cases.py` `GetModelUsageSummaryUseCase` | Null Object (consistent use) | Medium |
| 5 | `postgres_model_usage_repository.py` | Adapter (ISP fix) | Medium |
| 6 | `use_cases.py` `ListOffersUseCase._matches` | Chain of Responsibility (extend) | Medium |
| 7 | `llm_utils.py` | Registry | Low |
| 8 | `sorting.py` | Strategy (function registry) | Low |
| 9 | `llm_scoring_strategy.py` | Factory Method | Low |
| 10 | `use_cases.py` `CalculateNetSalaryUseCase` | DI (remove self-construction) | Low |

---

## What NOT to Change

- `FilterChain` + `OfferFilter` — already the cleanest code in the codebase; do not abstract further
- `CompositeModelUsageTracker` — textbook Composite, leave as-is
- `MatchScore.with_component` — immutable builder on a value object; correct and idiomatic
- `HardcodedModelLimitsRegistry` — simple and effective for the current scale; premature to generalize
