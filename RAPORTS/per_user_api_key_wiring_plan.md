# Implementation Plan — Wire per-user API keys into the AI scoring path

**Status:** not started (handoff for a fresh agent)
**Author:** prepared 2026-06-25 during the per-user-API-key effort
**Goal:** make the OpenAI Agents SDK calls (offer scoring + translation) use the **caller's own
provider API key, decrypted from the DB**, instead of the global `OPENAI_API_KEY` / `GEMINI_API_KEY`
from `.env`.

This plan is self-contained: it names the exact files/classes involved and includes code
sketches. Follow the project conventions in `CLAUDE.md` (TDD: write tests first; `uv run pytest`;
`uv run ruff check`; Clean Architecture — keep adapters behind ports).

---

## 1. Background: how it works today

- A user picks a scoring model via the API; their selection is persisted per user
  (`SelectedModelRepository` / `AiScoringContext.active_model_for(user_id)`).
- For a match request, `main.py::_ai_use_case_for_request(user)` →
  `AiScoringContext.use_case_for(user.id)` returns a `MatchOffersWithAiUseCase` that is **cached
  per model** (`AiScoringContext._use_cases_by_model[model]`) and **shared across all users** on
  that model.
- The use case's scorer/translator run through an **`OpenAIChatCompletionsModel`** built by
  `app/infrastructure/agent_models.py::build_chat_model(model, openai_api_key=…, gemini_api_key=…)`.
  That function constructs an `AsyncOpenAI(api_key=…, base_url=… if Google)` client and wraps it.
  **This `AsyncOpenAI` client is the single place the API key is injected.**
- Today `main.py::_build_ai_use_case(model)` passes the **env** keys
  (`OPENAI_API_KEY` / `GEMINI_API_KEY` from `app/config.py`) into `build_chat_model`.

The per-model cache + shared use case is exactly what must change: a key is per user, so a use case
(and its client) can no longer be shared across users.

## 2. The pieces already built by the API-key feature (reuse these)

- `app/application/ports.py`
  - `ApiKeyRecord` (`user_id, api_provider, key_ciphertext, key_hint, limit_usd, tracking_since, created_at`)
  - `ApiKeyRepository.get(user_id, api_provider) -> ApiKeyRecord | None` (+ add/list/delete/update_budget)
  - `KeyCipher.encrypt/decrypt`
  - `UserProviderSpendProvider.spend_since(user_id, company, since)` (for the budget step)
- `app/infrastructure/postgres_api_key_repository.py::PostgresApiKeyRepository`
- `app/infrastructure/fernet_key_cipher.py::FernetKeyCipher(secret)` (secret = `API_KEY_ENCRYPTION_KEY` in `app/config.py`)
- `app/domain/api_providers.py`
  - `company_for_provider("openai") -> "OpenAI"`, `provider_for_company("Google") -> "google"`
  - `provider_for_company` returns `None` for companies the user can't key (e.g. Anthropic / Unknown)
- `app/infrastructure/llm_utils.py::company_from_model(model) -> "OpenAI" | "Google" | "Anthropic" | "Unknown"`

## 3. The resolution chain (model → which user key)

```
model  --company_from_model-->  "OpenAI"/"Google"
       --provider_for_company--> "openai"/"google"   (api_provider id; None if unsupported)
ApiKeyRepository.get(user_id, provider) -> ApiKeyRecord | None
KeyCipher.decrypt(record.key_ciphertext) -> plaintext key  ->  AsyncOpenAI(api_key=…)
```

---

## 4. Steps

### Step A — key-aware chat-model builder
In `app/infrastructure/agent_models.py`, add (or refactor `build_chat_model` to delegate to) a
builder that takes one already-resolved key:

```python
def build_chat_model_for_key(model_name: str, api_key: str, timeout: float = 60.0) -> OpenAIChatCompletionsModel:
    if company_from_model(model_name) == "Google":
        client = AsyncOpenAI(api_key=api_key, base_url=GEMINI_BASE_URL, timeout=timeout)
    else:
        client = AsyncOpenAI(api_key=api_key, timeout=timeout)
    return OpenAIChatCompletionsModel(model=model_name, openai_client=client)
```

### Step B — a resolver (model + user → decrypted key)
New domain error + a small resolver. Put the error in `app/domain/errors.py`:

```python
class NoApiKeyConfiguredError(Exception):
    """The caller has no usable provider API key for the selected model's provider."""
    def __init__(self, provider_or_model: str) -> None:
        super().__init__(f"No API key configured for {provider_or_model}")
        self.detail = provider_or_model
```

Resolver (an application service or a function — keep it behind the ports):

```python
def resolve_user_api_key(user_id: str, model: str, api_keys: ApiKeyRepository, cipher: KeyCipher) -> str:
    provider = provider_for_company(company_from_model(model))
    if provider is None:
        raise NoApiKeyConfiguredError(model)          # provider the user can't key (Anthropic/Unknown)
    record = api_keys.get(user_id, provider)
    if record is None:
        raise NoApiKeyConfiguredError(provider)       # user hasn't added a key for this provider
    return cipher.decrypt(record.key_ciphertext)
```

### Step C — build the use case per request (drop the per-model cache for scoring)
In `main.py`, split the env-bound builder into a key-bound one and resolve per request:

```python
def _build_ai_use_case_for(model: str, api_key: str) -> MatchOffersWithAiUseCase:
    chat_model = build_chat_model_for_key(model, api_key, timeout=LLM_TIMEOUT_SECONDS) if model else None
    ai_scorer = CachingAiScorer(
        LLMScoringStrategy.create(
            model=model, chat_model=chat_model,
            translator_agent=build_polish_to_english_agent(chat_model=chat_model),
            usage_tracker=_in_memory_tracker),
        _ai_score_repository, model=model)
    return MatchOffersWithAiUseCase(
        offer_repository, filter_chain, SkillBasedScorer(), ai_scorer,
        usage_tracker=_in_memory_tracker, usage_repository=model_usage_repository,
        budget=_budget_gate, max_concurrency=AI_MATCH_CONCURRENCY, fail_closed=BUDGET_FAIL_CLOSED)

def _ai_use_case_for_request(user: User = Depends(get_current_user)) -> MatchOffersWithAiUseCase:
    model = _ai_scoring_context.active_model_for(user.id)   # keep AiScoringContext for model SELECTION only
    api_key = resolve_user_api_key(user.id, model, _api_key_repository, _key_cipher)
    return _build_ai_use_case_for(model, api_key)
```

Wire the two new singletons in `main.py`:
`_api_key_repository = PostgresApiKeyRepository(_engine)` and
`_key_cipher = FernetKeyCipher(API_KEY_ENCRYPTION_KEY)`.

Notes:
- Keep `AiScoringContext` for `active_model_for` / `select_model` (model persistence). **Stop using
  its `use_case_for` cache on the scoring path** — it's keyed per model and would reuse the first
  user's key. (You can leave the class as-is and simply not call `use_case_for`.)
- `set_tracing_disabled(True)` once at startup is enough; you don't need per-build SDK config.

### Step D — surface the missing-key error
In `app/presentation/api/routes.py::match_offers_ai`, map `NoApiKeyConfiguredError` to a clear
**400** (or **402**), e.g. `detail="Add an API key for this provider to run AI matching."`
Otherwise a missing key becomes a raw provider 401 → generic 500.

---

## 5. Pitfalls (do not skip)

1. **Never use the global SDK client.** Keep per-instance `AsyncOpenAI` clients (Step A). Do **not**
   call `set_default_openai_client` / `configure_gemini` / `configure_openai` on the scoring path —
   they are process-global and would leak one user's key into another request. (The codebase already
   uses per-instance clients — the "H1 fix" comment in `agent_models.py`. Don't regress it.)
2. **Don't cache the key-bound agents** (or invalidate on key change). Per-request build means a user
   who rotates/deletes a key immediately stops using the stale one. If caching for perf, key on
   `(user_id, provider, record.created_at)` and invalidate — but start with no cache; construction is
   cheap, the cost is the network round-trip, and `CachingAiScorer` (DB) still avoids re-scoring.
3. **Missing key → 400/402, not 500** (Step D).
4. **Per-key budget is a separate step** (see §6). Token attribution already works: the request-scoped
   tracker records usage under the calling user + company.

---

## 6. Out of scope here / coordinate

- **Per-key budget gate.** Enforce the key's own `limit_usd` vs provider usage since
  `tracking_since` (use `UserProviderSpendProvider.spend_since(user_id, company, since)`) before
  scoring. Today `_budget_gate` is `CompositeBudgetStatusReader([_budget_service, OrgSpendBackstop])`;
  add/replace with a per-key reader. Do this as a follow-up once keys are wired.
- **Env keys / `OrgSpendBackstop`.** `build_llm_provider_factory` + the org admin-key spend backstop
  are a separate path. Leave them; with per-user keys you may later drop the backstop (each user pays
  via their own key).
- **Coordination:** `main.py`, `ports.py`, `errors.py`, `schemas.py` are also touched by the API-key
  agent — rebase/coordinate before editing.

---

## 7. Tests (TDD — write first)

- `resolve_user_api_key`: returns the decrypted key for a stored (user, provider); raises
  `NoApiKeyConfiguredError` when no record, and when the model's provider is unsupported
  (Anthropic/Unknown). Use `InMemoryApiKeyRepository` (already in `tests/fakes.py`) + a fake/real
  `KeyCipher` (FernetKeyCipher with a generated key is fine).
- `build_chat_model_for_key`: routes Google models to the Gemini base URL and others to the default;
  the returned model carries a client built with the given key. (Assert on the client's
  `api_key`/`base_url` — keep it light; it's a thin adapter.)
- Route test (`tests/api/test_routes.py`): `POST /offers/match/ai` with no key for the active model's
  provider → 400/402 (override `get_match_offers_ai_use_case` / the resolver to raise).
- Integration (guarded — see `tests/integration/conftest.py`): a stored encrypted key decrypts and is
  usable end-to-end is optional; the unit tests above are the core.

## 8. Acceptance criteria

- An AI match uses the **caller's** key for the active model's provider; no `.env` key is read on the
  scoring path.
- Two users with different keys, scoring concurrently, never cross keys (per-instance clients).
- A user with no key for the selected provider gets a 400/402 with an actionable message.
- `uv run pytest` green; `uv run ruff check` clean.

---

### Quick reference — files

| Concern | File |
|---|---|
| Key injection point | `app/infrastructure/agent_models.py` (`build_chat_model`) |
| Per-request use-case wiring | `main.py` (`_build_ai_use_case`, `_ai_use_case_for_request`) |
| Model selection (keep) | `app/application/ai_scoring_context.py` |
| Scorer/translator agents | `app/infrastructure/llm_scoring_strategy.py`, `app/infrastructure/translation_agents.py` |
| Key storage / crypto | `app/infrastructure/postgres_api_key_repository.py`, `app/infrastructure/fernet_key_cipher.py`, `ApiKeyRepository`/`KeyCipher` in `app/application/ports.py` |
| Provider/model mapping | `app/domain/api_providers.py`, `app/infrastructure/llm_utils.py` |
| Error surfacing | `app/domain/errors.py`, `app/presentation/api/routes.py` (`match_offers_ai`) |
