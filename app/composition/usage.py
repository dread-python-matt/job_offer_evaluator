"""Composition of usage, budgets, and spend readouts: the per-user token-accounting budget and
its cache, the per-provider spend provider, the org-spend backstop and composite budget gate,
the OpenAI admin-key use cases + resolver, per-model usage totals, and the per-day request
budget. The org spend/usage readouts resolve per request from the caller's own admin key (env
fallback), so this module also exposes them as FastAPI dependency providers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends

from app.application.admin_key_resolver import AdminKeyResolver
from app.application.admin_key_use_cases import (
    DeleteAdminKeyUseCase,
    GetAdminKeyUseCase,
    SetAdminKeyUseCase,
)
from app.application.api_key_use_cases import SetDailyRequestLimitUseCase
from app.application.budget_service import BudgetService
from app.application.use_cases import (
    GetDailyRequestUsageUseCase,
    GetModelUsageSummaryUseCase,
    GetOrgSpendUseCase,
    GetOrgUsageUseCase,
)
from app.composition.foundation import Foundation
from app.config import (
    BUDGET_SPEND_CACHE_TTL_SECONDS,
    GEMINI_API_KEY,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    OPENAI_ADMIN_KEY,
    OPENAI_API_KEY,
    ORG_DAILY_BUDGET_USD,
)
from app.domain.auth import User
from app.infrastructure.api_key_budget_status_reader import ApiKeyBudgetStatusReader
from app.infrastructure.composite_budget_status_reader import CompositeBudgetStatusReader
from app.infrastructure.daily_request_usage_reader import (
    TokenAccountingDailyRequestUsageReader,
)
from app.infrastructure.llm_provider_factory import build_llm_provider_factory
from app.infrastructure.openai_admin_key_validator import OpenAIAdminKeyValidator
from app.infrastructure.org_spend_backstop import OrgSpendBackstop
from app.infrastructure.token_accounting_provider_spend_provider import (
    TokenAccountingProviderSpendProvider,
)
from app.infrastructure.token_accounting_spend_provider import TokenAccountingSpendProvider
from app.presentation.api.auth import get_current_user


@dataclass(frozen=True)
class UsageComponents:
    budget_service: BudgetService
    provider_spend_provider: TokenAccountingProviderSpendProvider
    org_spend_backstop: OrgSpendBackstop
    build_budget_gate: Callable[[str | None], CompositeBudgetStatusReader]
    get_admin_key: GetAdminKeyUseCase
    set_admin_key: SetAdminKeyUseCase
    delete_admin_key: DeleteAdminKeyUseCase
    usage_summary: GetModelUsageSummaryUseCase
    daily_request_reader: TokenAccountingDailyRequestUsageReader
    get_daily_request_usage: GetDailyRequestUsageUseCase
    set_daily_request_limit: SetDailyRequestLimitUseCase
    org_spend_for_request: Callable[..., GetOrgSpendUseCase]
    org_usage_for_request: Callable[..., GetOrgUsageUseCase]


def build_usage(foundation: Foundation) -> UsageComponents:
    model_usage = foundation.model_usage_repository
    api_key_repo = foundation.api_key_repository

    provider_spend_provider = TokenAccountingProviderSpendProvider(model_usage)

    # LLM_PROVIDER selects only the org-level usage/cost wiring; the scoring model is per user.
    llm_factory = build_llm_provider_factory(
        LLM_PROVIDER, OPENAI_API_KEY, OPENAI_ADMIN_KEY, GEMINI_API_KEY
    )
    env_org_spend_provider = llm_factory.build_spend_provider()
    org_spend_backstop = OrgSpendBackstop(env_org_spend_provider, ORG_DAILY_BUDGET_USD)
    env_org_usage_provider = llm_factory.build_external_usage_provider()

    admin_key_resolver = AdminKeyResolver(foundation.admin_key_repository, foundation.key_cipher)
    admin_key_validator = OpenAIAdminKeyValidator(timeout=LLM_TIMEOUT_SECONDS)

    def build_budget_gate(api_provider: str | None) -> CompositeBudgetStatusReader:
        # The user's per-key budget (bound to the scored model's provider) plus the global
        # org-spend backstop that protects the owner's real bill (active only with an admin key).
        readers: list = []
        if api_provider is not None:
            readers.append(
                ApiKeyBudgetStatusReader(api_key_repo, provider_spend_provider, api_provider)
            )
        readers.append(org_spend_backstop)
        return CompositeBudgetStatusReader(readers)

    def spend_provider_for_user(user_id: str):
        # The caller's own admin key if set, else the env key (None → the readout returns null).
        key = admin_key_resolver.key_for_user(user_id)
        if key:
            from app.infrastructure.openai_spend_provider import OpenAISpendProvider

            return OpenAISpendProvider(api_key=key, timeout=LLM_TIMEOUT_SECONDS)
        return env_org_spend_provider

    def usage_provider_for_user(user_id: str):
        key = admin_key_resolver.key_for_user(user_id)
        if key:
            from openai import OpenAI

            from app.infrastructure.openai_usage_provider import OpenAIExternalUsageProvider

            # Admin/organization usage routes authenticate with `admin_api_key`, not `api_key`.
            return OpenAIExternalUsageProvider(
                OpenAI(admin_api_key=key, timeout=LLM_TIMEOUT_SECONDS)
            )
        return env_org_usage_provider

    def org_spend_for_request(user: User = Depends(get_current_user)) -> GetOrgSpendUseCase:
        return GetOrgSpendUseCase(spend_provider_for_user(user.id))

    def org_usage_for_request(user: User = Depends(get_current_user)) -> GetOrgUsageUseCase:
        return GetOrgUsageUseCase(usage_provider_for_user(user.id))

    daily_request_reader = TokenAccountingDailyRequestUsageReader(
        api_key_repo, model_usage, foundation.model_limits
    )

    return UsageComponents(
        budget_service=BudgetService(
            foundation.budget_repository,
            TokenAccountingSpendProvider(model_usage),
            cache_ttl_seconds=BUDGET_SPEND_CACHE_TTL_SECONDS,
        ),
        provider_spend_provider=provider_spend_provider,
        org_spend_backstop=org_spend_backstop,
        build_budget_gate=build_budget_gate,
        get_admin_key=GetAdminKeyUseCase(foundation.admin_key_repository),
        set_admin_key=SetAdminKeyUseCase(
            foundation.admin_key_repository, foundation.key_cipher, admin_key_validator
        ),
        delete_admin_key=DeleteAdminKeyUseCase(foundation.admin_key_repository),
        usage_summary=GetModelUsageSummaryUseCase(model_usage, foundation.model_limits),
        daily_request_reader=daily_request_reader,
        get_daily_request_usage=GetDailyRequestUsageUseCase(
            foundation.selected_model_repository, daily_request_reader
        ),
        set_daily_request_limit=SetDailyRequestLimitUseCase(api_key_repo),
        org_spend_for_request=org_spend_for_request,
        org_usage_for_request=org_usage_for_request,
    )
