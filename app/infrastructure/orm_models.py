from datetime import datetime

from sqlalchemy import JSON, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.entities import Offer


class Base(DeclarativeBase):
    pass


class OfferRow(Base):
    """Maps the `offers` table owned and migrated by the scraper project."""

    __tablename__ = "offers"

    link: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    company: Mapped[str]
    tech_stack: Mapped[list] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str] = mapped_column(Text)
    benefits: Mapped[str] = mapped_column(Text)
    locations: Mapped[list] = mapped_column(JSON)
    published_date: Mapped[str]
    salary_range: Mapped[str | None]
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    portal: Mapped[str]
    tech_stack_nice_to_have: Mapped[list] = mapped_column(JSON)
    requirements_nice_to_have: Mapped[str] = mapped_column(Text)
    responsibilities: Mapped[str] = mapped_column(Text)

    def to_offer(self) -> Offer:
        return Offer(
            link=self.link,
            title=self.title,
            company=self.company,
            tech_stack=self.tech_stack or [],
            tech_stack_nice_to_have=self.tech_stack_nice_to_have or [],
            description=self.description or "",
        )
