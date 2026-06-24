from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, Text, Integer
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

    def to_salary(self) -> Salary:
        return Salary(
            contract_type=self.contract_type,
            min_amount=float(self.min) if self.min is not None else None,
            max_amount=float(self.max) if self.max is not None else None,
            currency=self.currency,
            period=self.period,
        )


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
