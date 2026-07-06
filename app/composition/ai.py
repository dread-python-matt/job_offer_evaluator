"""Composition of AI matching: user-supplied provider keys (validation, resolution, the cached
per-user model picker), the per-(user, model) AI match factory and its Google pacing, and the
`AiScoringContext` that resolves and caches a use case for each user's selected model. Depends on
the shared `Foundation` and on `UsageComponents` (budget gate, daily-request reader, per-provider
spend).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agents import set_tracing_disabled
from fastapi import Depends

from app.application.ai_scoring_context import AiScoringContext
from app.application.api_key_resolver import UserApiKeyResolver
from app.application.api_key_use_cases import (
    AddApiKeyUseCase,
    DeleteApiKeyUseCase,
    ListApiKeysUseCase,
    SetApiKeyBudgetUseCase,
)
from app.application.use_cases import ListAvailableModelsUseCase, MatchOffersWithAiUseCase
from app.composition.foundation import Foundation
from app.composition.usage import UsageComponents
from app.config import (
    AI_MATCH_CONCURRENCY,
    BUDGET_FAIL_CLOSED,
    GOOGLE_RPM_LIMIT,
    LLM_TIMEOUT_SECONDS,
    MODELS_CACHE_TTL_SECONDS,
    WORKERS,
)
from app.domain.api_providers import provider_for_company
from app.domain.auth import User
from app.domain.errors import MissingProviderApiKeyError
from app.infrastructure.agent_models import build_chat_model_with_key
from app.infrastructure.caching_ai_scorer import CachingAiScorer
from app.infrastructure.gemini_available_models_provider import GeminiAvailableModelsProvider
from app.infrastructure.google_pace_limiter_cache import GooglePaceLimiterCache
from app.infrastructure.keyed_user_available_models_provider import (
    CachingUserAvailableModelsProvider,
    KeyedUserAvailableModelsProvider,
)
from app.infrastructure.llm_scoring_strategy import LLMScoringStrategy
from app.infrastructure.llm_utils import company_from_model
from app.infrastructure.model_listing_api_key_validator import ModelListingApiKeyValidator
from app.infrastructure.openai_available_models_provider import OpenAIAvailableModelsProvider
from app.infrastructure.rate_limiting import AsyncRateLimiter
from app.infrastructure.scoring_strategies import SkillBasedScorer
from app.infrastructure.translation_agents import build_polish_to_english_agent
from app.presentation.api.auth import get_current_user


@dataclass(frozen=True)
class AiComponents:
    scoring_context: AiScoringContext
    list_available_models: ListAvailableModelsUseCase
    list_api_keys: ListApiKeysUseCase
    set_api_key_budget: SetApiKeyBudgetUseCase
    add_api_key: AddApiKeyUseCase
    delete_api_key: DeleteApiKeyUseCase
    ai_use_case_for_request: Callable[..., MatchOffersWithAiUseCase]


def _disable_tracing(_model: str) -> None:
    # Each use case builds agents with their own per-model client, so model selection no longer
    # mutates the global SDK client. Only tracing needs disabling globally (idempotent) — there
    # is no tracing backend configured.
    set_tracing_disabled(True)


def _provider_for_model(model: str) -> str:
    """The provider id for a model, or raise MissingProviderApiKeyError when the model is from a
    company the user can't key (so it's reported as 'add a key')."""
    provider = provider_for_company(company_from_model(model))
    if provider is None:
        raise MissingProviderApiKeyError(company_from_model(model))
    return provider


def build_ai(foundation: Foundation, usage: UsageComponents) -> AiComponents:
    api_key_repo = foundation.api_key_repository
    key_cipher = foundation.key_cipher

    def models_provider_for_key(provider: str, key: str):
        if provider == "google":
            return GeminiAvailableModelsProvider(key, timeout=LLM_TIMEOUT_SECONDS)
        return OpenAIAvailableModelsProvider(key, timeout=LLM_TIMEOUT_SECONDS)

    # Scoring resolves the calling user's own key on demand (require own key — no env fallback);
    # the model picker is discovered from the user's own keys and cached per user.
    api_key_resolver = UserApiKeyResolver(api_key_repo, key_cipher)
    available_models_provider = CachingUserAvailableModelsProvider(
        KeyedUserAvailableModelsProvider(api_key_repo, key_cipher, models_provider_for_key),
        ttl_seconds=MODELS_CACHE_TTL_SECONDS,
    )
    # One Google limiter per (user, model): Gemini free-tier RPM is capped per project AND per
    # model, and each user brings their own key/project, sized to that model's real RPM and split
    # across WORKERS. OpenAI scoring is never paced — only Google's stricter free tier is.
    google_pace_limiters = GooglePaceLimiterCache(
        foundation.model_limits, GOOGLE_RPM_LIMIT, workers=WORKERS
    )

    def build_ai_use_case(user_id: str, model: str) -> MatchOffersWithAiUseCase:
        rate_limiter: AsyncRateLimiter | None = None
        if model:
            provider = _provider_for_model(model)
            key = api_key_resolver.key_for_provider(user_id, provider)  # require own key
            chat_model = build_chat_model_with_key(model, api_key=key, timeout=LLM_TIMEOUT_SECONDS)
            if company_from_model(model) == "Google":
                # Google's free tier is budgeted by requests/day, not dollars: no USD gate (the
                # daily-request reader gates it), but pace under its free-tier RPM cap.
                budget_gate = None
                rate_limiter = google_pace_limiters.get(user_id, model)
            else:
                budget_gate = usage.build_budget_gate(provider)
        else:
            chat_model = None
            budget_gate = usage.build_budget_gate(None)
        ai_scorer = CachingAiScorer(
            LLMScoringStrategy.create(
                model=model,
                chat_model=chat_model,
                translator_agent=build_polish_to_english_agent(chat_model=chat_model),
                usage_tracker=foundation.usage_tracker,
                rate_limiter=rate_limiter,
            ),
            foundation.ai_score_repository,
            model=model,
        )
        return MatchOffersWithAiUseCase(
            foundation.offer_repository,
            foundation.filter_chain,
            SkillBasedScorer(),
            ai_scorer,
            usage_tracker=foundation.usage_tracker,
            usage_repository=foundation.model_usage_repository,
            budget=budget_gate,
            max_concurrency=AI_MATCH_CONCURRENCY,
            fail_closed=BUDGET_FAIL_CLOSED,
            canonicalizer=foundation.skill_canonicalizer,
            daily_request_reader=usage.daily_request_reader,
            scoring_model=model,
        )

    # Each user selects a model from their own keys; there is no global default.
    set_tracing_disabled(True)
    scoring_context = AiScoringContext(
        repository=foundation.selected_model_repository,
        build_use_case=build_ai_use_case,
        configure_sdk=_disable_tracing,
        default_model="",
    )

    # A key change must invalidate BOTH per-user caches: the model picker (else a freshly added
    # provider stays hidden until the TTL) and the AI scoring context (else a rotated key keeps
    # replaying the deleted credential until restart). The context exists before the use cases
    # that trigger this, so no late binding is needed.
    def on_user_keys_changed(user_id: str) -> None:
        available_models_provider.invalidate(user_id)
        scoring_context.invalidate(user_id)

    def ai_use_case_for_request(
        user: User = Depends(get_current_user),
    ) -> MatchOffersWithAiUseCase:
        """Resolve the AI match use case for the calling user's selected model (per-user)."""
        return scoring_context.use_case_for(user.id)

    return AiComponents(
        scoring_context=scoring_context,
        list_available_models=ListAvailableModelsUseCase(available_models_provider),
        list_api_keys=ListApiKeysUseCase(api_key_repo, usage.provider_spend_provider),
        set_api_key_budget=SetApiKeyBudgetUseCase(api_key_repo, usage.provider_spend_provider),
        add_api_key=AddApiKeyUseCase(
            api_key_repo,
            key_cipher,
            ModelListingApiKeyValidator(provider_factory=models_provider_for_key),
            on_change=on_user_keys_changed,
        ),
        delete_api_key=DeleteApiKeyUseCase(api_key_repo, on_change=on_user_keys_changed),
        ai_use_case_for_request=ai_use_case_for_request,
    )
