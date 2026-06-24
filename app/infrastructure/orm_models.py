from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Text, Integer
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


class ModelUsageRow(Base):
    __tablename__ = "model_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nullable: rows written before multi-tenancy are unattributed and excluded from
    # any user's per-user summary.
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    company: Mapped[str]
    model: Mapped[str]
    label: Mapped[str]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BudgetRow(Base):
    """Single-row table holding the spend budget. The usage anchor (`tracking_since`)
    only moves on an explicit reset, so accrued usage never resets automatically."""

    __tablename__ = "budget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    limit_usd: Mapped[Decimal] = mapped_column(Numeric)
    tracking_since: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
    lowercased). `token_version` is bumped to invalidate all of a user's sessions."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
