from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.entities import Offer, Salary


class Base(DeclarativeBase):
    pass


class SalaryRow(Base):
    """Maps the `salaries` table owned and migrated by the scraper project. One row
    per contract type offered (e.g. B2B vs permanent)."""

    __tablename__ = "salaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    contract_type: Mapped[str]
    min: Mapped[Decimal | None] = mapped_column(Numeric)
    max: Mapped[Decimal | None] = mapped_column(Numeric)
    currency: Mapped[str]
    period: Mapped[str]

    normalized: Mapped["NormalizedSalaryRow | None"] = relationship(
        "NormalizedSalaryRow", uselist=False, viewonly=True, lazy="selectin"
    )

    def to_salary(self) -> Salary:
        n = self.normalized
        return Salary(
            contract_type=self.contract_type,
            min_amount=float(self.min) if self.min is not None else None,
            max_amount=float(self.max) if self.max is not None else None,
            currency=self.currency,
            period=self.period,
            net_min=float(n.net_of_min) if n is not None else None,
            net_mid=float(n.midpoint) if n is not None else None,
            net_max=float(n.net_of_max) if n is not None else None,
        )


class NormalizedSalaryRow(Base):
    """Maps the scraper-owned `normalized_salary` table (read-only): one row per
    `salaries` row, holding precomputed NET monthly PLN figures. Lets the app filter
    and sort offers by salary in SQL instead of materializing and computing in Python."""

    __tablename__ = "normalized_salary"

    salary_id: Mapped[int] = mapped_column(
        ForeignKey("salaries.id", ondelete="CASCADE"), primary_key=True
    )
    net_of_min: Mapped[Decimal] = mapped_column(Numeric)
    net_of_max: Mapped[Decimal] = mapped_column(Numeric)
    midpoint: Mapped[Decimal] = mapped_column(Numeric)
    model_version: Mapped[str]
    computed_at: Mapped[datetime] = mapped_column(DateTime)


class OfferRow(Base):
    """Maps the `offers` table owned and migrated by the scraper project."""

    __tablename__ = "offers"

    link: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[str] = mapped_column(unique=True)
    title: Mapped[str]
    company: Mapped[str]
    tech_stack: Mapped[list] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str] = mapped_column(Text)
    benefits: Mapped[str] = mapped_column(Text)
    locations: Mapped[list] = mapped_column(JSON)
    published_date: Mapped[str]
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    portal: Mapped[str]
    tech_stack_nice_to_have: Mapped[list] = mapped_column(JSON)
    requirements_nice_to_have: Mapped[str] = mapped_column(Text)
    responsibilities: Mapped[str] = mapped_column(Text)
    expires: Mapped[str]
    levels: Mapped[list] = mapped_column(JSON)
    expired: Mapped[bool] = mapped_column(Boolean)

    salaries: Mapped[list[SalaryRow]] = relationship(
        primaryjoin="OfferRow.id == foreign(SalaryRow.offer_id)",
        viewonly=True,
        lazy="selectin",
    )

    def to_offer(self) -> Offer:
        return Offer(
            link=self.link,
            title=self.title,
            company=self.company,
            tech_stack=self.tech_stack or [],
            tech_stack_nice_to_have=self.tech_stack_nice_to_have or [],
            description=self.description or "",
            locations=self.locations or [],
            salaries=[row.to_salary() for row in self.salaries],
            expired=self.expired,
            expires=self.expires or None,
            levels=self.levels or [],
            published=self.published_date or None,
        )


class OfferSkillRow(Base):
    """App-owned projection of each offer's skills onto canonical concepts, so the browse `tech`
    filter can match by concept in SQL (the scraper-owned `offers.tech_stack` holds raw strings).
    One row per (offer, canonical concept); rebuilt by `PostgresOfferSkillIndexer`. No FK to
    `offers` on purpose — that table is scraper-owned/migrated and this is a derived cache, so we
    avoid coupling our migration to it; orphan rows are harmless and pruned on the next rebuild."""

    __tablename__ = "offer_skill"

    offer_id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_id: Mapped[str] = mapped_column(String, primary_key=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (Index("ix_offer_skill_canonical_id", "canonical_id"),)


class OfferSkillIndexMeta(Base):
    """Single-row bookkeeping for the `offer_skill` index: the alias-map version it was built
    from, when, and how many rows. Lets a stale index (the alias map changed but the indexer was
    never re-run) be detected and surfaced instead of silently serving outdated concept filters.
    Written in the same transaction as a rebuild, so it never disagrees with the index. `id` is a
    fixed sentinel (always 1) enforcing the single-row invariant."""

    __tablename__ = "offer_skill_index_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    map_version: Mapped[str] = mapped_column(String, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UnknownSkillTokenRow(Base):
    """App-owned record of the unmapped skill-token tail (Tier-0 normalizer misses): normalized
    tokens the alias map doesn't recognize, with how often they occur in the corpus and a few
    example raw forms. Snapshot-replaced by `mine_skill_corpus --persist` and read (ranked by
    `occurrences`) by the alias suggester / curation — the highest-ROI map entries to add next."""

    __tablename__ = "unknown_skill_token"

    normalized: Mapped[str] = mapped_column(String, primary_key=True)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_samples: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_unknown_skill_token_occurrences", "occurrences"),)


class ModelUsageRow(Base):
    __tablename__ = "model_usage"
    # Spend is derived by summing a user's usage since an anchor timestamp
    # (TokenAccountingSpendProvider.spend_since), so the hot query filters on user_id AND
    # created_at. A composite index serves that and the user-only summary (leftmost prefix),
    # which is why user_id no longer carries a standalone index.
    __table_args__ = (Index("ix_model_usage_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nullable: rows written before multi-tenancy are unattributed and excluded from
    # any user's per-user summary.
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    company: Mapped[str]
    model: Mapped[str]
    label: Mapped[str]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    # True when the counts were estimated (provider reported no usage), so estimated and
    # measured usage stay distinguishable in the data.
    estimated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # USD cost of this row's tokens, priced once at write time (PricingModelUsageRepository)
    # and frozen here, so spend reads sum this column and a later price change never rewrites
    # historical spend.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BudgetRow(Base):
    """Each user's spend budget. `user_id` is a unique FK to users. The usage anchor
    (`tracking_since`) only moves on an explicit reset, so accrued usage never resets
    automatically."""

    __tablename__ = "budget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    limit_usd: Mapped[Decimal] = mapped_column(Numeric)
    tracking_since: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserApiKeyRow(Base):
    """A user's own provider API key, with its own spend budget. One row per
    (user, api_provider) — `UNIQUE(user_id, api_provider)` enforces a single key per
    provider per user. The key is stored only as ciphertext (encrypted by a server-held
    secret, never one-way hashed — it must be replayed to the provider); `key_hint` is a
    non-secret masked display string. Usage is not stored: it is derived from recorded
    model usage for this provider since `tracking_since`."""

    __tablename__ = "user_api_key"
    __table_args__ = (UniqueConstraint("user_id", "api_provider", name="uq_user_api_key_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    api_provider: Mapped[str] = mapped_column(String(32))
    key_ciphertext: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(64))
    limit_usd: Mapped[Decimal] = mapped_column(Numeric)
    tracking_since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Optional per-day request cap (free-tier-friendly budget). NULL = use the model's
    # free-tier requests-per-day default; a value is the user's own override.
    daily_request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OpenAiAdminKeyRow(Base):
    """A user's OpenAI organization admin key, used to read org-wide spend/usage. At most
    one per user — `UNIQUE(user_id)` enforces it. Unlike a provider key it has no provider
    or budget. The key is stored only as ciphertext (encrypted by a server-held secret,
    never one-way hashed — it must be replayed to the provider); `key_hint` is a non-secret
    masked display string."""

    __tablename__ = "openai_admin_key"
    __table_args__ = (UniqueConstraint("user_id", name="uq_openai_admin_key_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    key_ciphertext: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserProfileRow(Base):
    """One profile per user, stored as a JSON document (atomic writes, no parser).
    `user_id` is a unique FK to users — each account has at most one profile."""

    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SelectedModelRow(Base):
    """Each user's active scoring model, so all workers agree on it per user.
    `user_id` is a unique FK to users."""

    __tablename__ = "selected_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    model: Mapped[str] = mapped_column(Text)


class AiScoreRow(Base):
    """Content-addressed cache of AI scores: `key` is a hash of (model, candidate,
    offer inputs); `data` is the serialized MatchScore (components + AI insight)."""

    __tablename__ = "ai_score"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserRow(Base):
    """An authenticated account. `id` is a UUID string; `email` is unique (stored
    lowercased). `token_version` is bumped to invalidate all of a user's sessions.
    `email_verified` gates login until the emailed confirmation link is followed."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class RefreshTokenRow(Base):
    """A persisted refresh token (one link in a rotation chain). Only the SHA-256
    `token_hash` is stored, never the raw token. `family_id` groups a rotation chain so a
    detected reuse can revoke the whole family. `consumed_at` marks a token as already
    rotated (replaying it is the theft signal)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
