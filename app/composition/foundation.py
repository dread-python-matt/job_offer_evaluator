"""Shared infrastructure primitives for the composition root: the database engine, the
repositories built on it, and the stateless helpers (skill normalization, filtering, request-
scoped usage tracking, model limits, key cipher) that several concern builders depend on.

This is composition-root code — it deliberately imports concrete adapters. Building a repository
does not open a connection (Alembic owns the schema; `create_all` was removed), so
`build_foundation()` succeeds even when the database is unreachable.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from app.application.skill_canonicalization import SkillCanonicalizer
from app.config import (
    API_KEY_ENCRYPTION_KEY,
    DATABASE_URL,
    DB_MAX_OVERFLOW,
    DB_POOL_SIZE,
    DEFAULT_BUDGET_USD,
)
from app.domain.filters import FilterChain
from app.infrastructure.alias_map_skill_normalizer import AliasMapSkillNormalizer
from app.infrastructure.db import build_engine
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry
from app.infrastructure.model_pricing_registry import HardcodedModelPricingRegistry
from app.infrastructure.offer_filters import (
    ExpiredFilter,
    LevelFilter,
    LocationFilter,
    SalaryFilter,
    SkillFilter,
)
from app.infrastructure.postgres_admin_key_repository import PostgresAdminKeyRepository
from app.infrastructure.postgres_ai_score_repository import PostgresAiScoreRepository
from app.infrastructure.postgres_api_key_repository import PostgresApiKeyRepository
from app.infrastructure.postgres_budget_repository import PostgresBudgetRepository
from app.infrastructure.postgres_model_usage_repository import PostgresModelUsageRepository
from app.infrastructure.postgres_offer_repository import PostgresOfferRepository
from app.infrastructure.postgres_refresh_token_repository import PostgresRefreshTokenRepository
from app.infrastructure.postgres_selected_model_repository import (
    PostgresSelectedModelRepository,
)
from app.infrastructure.postgres_user_profile_repository import PostgresUserProfileRepository
from app.infrastructure.postgres_user_repository import PostgresUserRepository
from app.infrastructure.pricing_model_usage_repository import PricingModelUsageRepository
from app.infrastructure.request_scoped_usage_tracker import RequestScopedModelUsageTracker


@dataclass(frozen=True)
class Foundation:
    """The shared, long-lived infrastructure objects every request is served from."""

    engine: Engine
    key_cipher: FernetKeyCipher
    skill_normalizer: AliasMapSkillNormalizer
    filter_chain: FilterChain
    skill_canonicalizer: SkillCanonicalizer
    usage_tracker: RequestScopedModelUsageTracker
    model_limits: HardcodedModelLimitsRegistry
    profile_repository: PostgresUserProfileRepository
    offer_repository: PostgresOfferRepository
    model_usage_repository: PricingModelUsageRepository
    ai_score_repository: PostgresAiScoreRepository
    selected_model_repository: PostgresSelectedModelRepository
    budget_repository: PostgresBudgetRepository
    api_key_repository: PostgresApiKeyRepository
    admin_key_repository: PostgresAdminKeyRepository
    user_repository: PostgresUserRepository
    refresh_token_repository: PostgresRefreshTokenRepository


def _build_model_usage_repository(engine: Engine) -> PricingModelUsageRepository:
    """Price each usage row at write time and freeze its `cost_usd`, so a later price change
    never rewrites historical spend and spend reads just sum the stored column."""
    return PricingModelUsageRepository(
        PostgresModelUsageRepository(engine), HardcodedModelPricingRegistry()
    )


def _build_filter_chain() -> FilterChain:
    return FilterChain(
        [SkillFilter(), LocationFilter(), SalaryFilter(), ExpiredFilter(), LevelFilter()]
    )


def build_foundation() -> Foundation:
    """Build the engine (tunable pool) and every repository/shared primitive on top of it.

    Skills are collapsed to canonical concepts (alias map + folding) before any comparison, so
    the normalizer is shared by matching (via the canonicalizer) and browsing's tech filter (via
    the offer repository's `offer_skill` index)."""
    engine = build_engine(DATABASE_URL, pool_size=DB_POOL_SIZE, max_overflow=DB_MAX_OVERFLOW)
    skill_normalizer = AliasMapSkillNormalizer.from_default()
    return Foundation(
        engine=engine,
        key_cipher=FernetKeyCipher(API_KEY_ENCRYPTION_KEY),
        skill_normalizer=skill_normalizer,
        filter_chain=_build_filter_chain(),
        skill_canonicalizer=SkillCanonicalizer(skill_normalizer),
        usage_tracker=RequestScopedModelUsageTracker(),
        model_limits=HardcodedModelLimitsRegistry(),
        profile_repository=PostgresUserProfileRepository(engine),
        offer_repository=PostgresOfferRepository(engine, normalizer=skill_normalizer),
        model_usage_repository=_build_model_usage_repository(engine),
        ai_score_repository=PostgresAiScoreRepository(engine),
        selected_model_repository=PostgresSelectedModelRepository(engine),
        budget_repository=PostgresBudgetRepository(engine, default_limit_usd=DEFAULT_BUDGET_USD),
        api_key_repository=PostgresApiKeyRepository(engine),
        admin_key_repository=PostgresAdminKeyRepository(engine),
        user_repository=PostgresUserRepository(engine),
        refresh_token_repository=PostgresRefreshTokenRepository(engine),
    )
