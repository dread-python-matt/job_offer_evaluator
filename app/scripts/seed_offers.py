"""Seed the database with a diverse set of demo job offers so the app is usable out of the box.

The `offers` / `salaries` / `normalized_salary` tables are owned by a separate, **external**
offers source and are read-only here (no Alembic migration creates them). On a fresh database a
recruiter therefore has nothing to browse or match against. This script fills that gap with a
curated, realistic fixture — ~50+ recent offers spanning many tech stacks, portals, seniority
levels and contract types — so browsing, filtering, the deterministic match and the salary
calculator all work immediately (no provider API key required).

It is split in two so the data is testable without a database:

* `build_sample_offers()` — a **pure** function returning framework-free value objects.
* `seed_database(engine, offers)` — creates the three external tables if absent and inserts the
  data, computing each offer's normalized NET salary with the app's own `SalaryCalculator`
  (so the demo figures are consistent with the rest of the app).

It is **idempotent**: every seeded row carries a `seed-*` id and is removed before re-inserting,
so running it twice doesn't duplicate data. Each offer's `link` (the `offers` primary key) is its
real portal homepage plus a unique `?ref=seed-*` marker — a working, clickable URL that stays
distinct per row and never collides with a real external offer's link.

Usage:
    uv run python -m app.scripts.seed_offers            # seed the database
    uv run python -m app.scripts.seed_offers --dry-run  # print what would be inserted, no writes
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.domain.salary_calculator import SalaryCalculator, contract_type_from_label
from app.infrastructure.orm_models import (
    Base,
    NormalizedSalaryRow,
    OfferRow,
    SalaryRow,
)

# --- value objects (pure; no ORM / framework types) -------------------------------------


@dataclass(frozen=True)
class SeedSalary:
    """One advertised salary band for a demo offer. `contract_type` is a source-style label
    (`b2b` / `permanent` / `zlecenie`) the net calculator understands; amounts are gross
    monthly PLN."""

    contract_type: str
    min_amount: float
    max_amount: float


@dataclass(frozen=True)
class SeedOffer:
    """A demo job offer, mirroring the fields the app reads from a real offer."""

    title: str
    company: str
    portal: str
    locations: list[str]
    tech_stack: list[str]
    tech_stack_nice_to_have: list[str]
    levels: list[str]
    description: str
    requirements: str
    benefits: str
    responsibilities: str
    salaries: list[SeedSalary]
    published_days_ago: int
    expired: bool = False


# --- the fixture ------------------------------------------------------------------------


@dataclass(frozen=True)
class _Archetype:
    """A role family the variants are generated from. `mid_min`/`mid_max` are the gross
    monthly PLN band for a *Mid* hire; other levels scale it (see `_LEVEL_MULTIPLIER`)."""

    role: str
    company: str
    portal: str
    locations: list[str]
    tech_stack: list[str]
    nice_to_have: list[str]
    mid_min: float
    mid_max: float


# Ordered low → high so a slice of three covers a spread of seniorities (see `build_sample_offers`).
_LEVEL_ORDER = ["Intern", "Junior", "Mid", "Senior", "Lead", "Expert"]
_LEVEL_MULTIPLIER = {
    "Intern": 0.45,
    "Junior": 0.62,
    "Mid": 1.0,
    "Senior": 1.55,
    "Lead": 2.0,
    "Expert": 2.35,
}
_CONTRACTS = ["b2b", "permanent", "zlecenie"]
_SENIOR_LEVELS = {"Senior", "Lead", "Expert"}

# 18 role families across 7 Polish IT job portals; expanded to 54 offers (3 seniorities each).
_ARCHETYPES: list[_Archetype] = [
    _Archetype("Python Backend Engineer", "Nimbus Software", "justjoin.it",
               ["Warszawa", "Remote"], ["Python", "FastAPI", "PostgreSQL", "Docker"],
               ["Kubernetes", "AWS"], 16000, 23000),
    _Archetype("Java Backend Engineer", "Vistula Systems", "nofluffjobs.com",
               ["Kraków"], ["Java", "Spring Boot", "Hibernate", "PostgreSQL"],
               ["Kafka", "Kubernetes"], 16000, 24000),
    _Archetype("React Frontend Developer", "Pixel Forge", "bulldogjob.pl",
               ["Wrocław", "Remote"], ["TypeScript", "React", "Redux", "CSS"],
               ["Next.js", "GraphQL"], 14000, 20000),
    _Archetype("Angular Frontend Developer", "Baltic Apps", "pracuj.pl",
               ["Gdańsk"], ["TypeScript", "Angular", "RxJS", "SCSS"],
               ["NgRx", "Cypress"], 14000, 20000),
    _Archetype("Fullstack Node Developer", "Odra Digital", "rocketjobs.pl",
               ["Poznań", "Remote"], ["JavaScript", "Node.js", "Express", "MongoDB"],
               ["TypeScript", "AWS"], 15000, 22000),
    _Archetype("DevOps Engineer", "Tatra Cloud", "theprotocol.it",
               ["Warszawa"], ["Kubernetes", "Terraform", "AWS", "Linux"],
               ["Ansible", "Prometheus"], 18000, 26000),
    _Archetype("Data Engineer", "Wawel Data", "justjoin.it",
               ["Remote"], ["Python", "SQL", "Spark", "Airflow"],
               ["dbt", "Snowflake"], 16000, 24000),
    _Archetype("Machine Learning Engineer", "Copernicus AI", "nofluffjobs.com",
               ["Kraków", "Remote"], ["Python", "PyTorch", "TensorFlow", "scikit-learn"],
               ["MLflow", "CUDA"], 18000, 27000),
    _Archetype("Go Backend Engineer", "Sudety Labs", "bulldogjob.pl",
               ["Wrocław"], ["Go", "gRPC", "PostgreSQL", "Docker"],
               ["Kubernetes", "Kafka"], 17000, 25000),
    _Archetype("Rust Systems Engineer", "Granit Systems", "solid.jobs",
               ["Remote"], ["Rust", "Tokio", "WebAssembly", "Linux"],
               ["C++"], 18000, 27000),
    _Archetype(".NET Backend Engineer", "Mazovia Soft", "pracuj.pl",
               ["Katowice"], ["C#", ".NET", "ASP.NET Core", "SQL Server"],
               ["Azure"], 15000, 23000),
    _Archetype("Android Developer", "Bug River Mobile", "theprotocol.it",
               ["Łódź"], ["Kotlin", "Jetpack Compose", "Coroutines"],
               ["Java"], 15000, 22000),
    _Archetype("iOS Developer", "Amber Mobile", "rocketjobs.pl",
               ["Remote"], ["Swift", "SwiftUI", "Combine"],
               ["Objective-C"], 15000, 22000),
    _Archetype("PHP Backend Developer", "Lech Commerce", "justjoin.it",
               ["Gdańsk"], ["PHP", "Laravel", "MySQL", "Redis"],
               ["Vue.js"], 13000, 19000),
    _Archetype("QA Automation Engineer", "Quality Bridge", "nofluffjobs.com",
               ["Warszawa", "Remote"], ["Selenium", "Python", "Playwright"],
               ["Cypress"], 12000, 18000),
    _Archetype("Security Engineer", "Cerber Security", "bulldogjob.pl",
               ["Remote"], ["Python", "Linux", "Burp Suite", "Networking"],
               ["Go"], 18000, 27000),
    _Archetype("Data Scientist", "Piast Analytics", "solid.jobs",
               ["Kraków"], ["Python", "Pandas", "SQL", "scikit-learn"],
               ["R", "Tableau"], 16000, 24000),
    _Archetype("Embedded Systems Engineer", "Orla Electronics", "theprotocol.it",
               ["Wrocław"], ["C", "C++", "RTOS", "Embedded Linux"],
               ["Rust"], 16000, 23000),
]


def _round_to_100(amount: float) -> float:
    return float(round(amount / 100.0) * 100)


def _salary_band(archetype: _Archetype, level: str) -> tuple[float, float]:
    multiplier = _LEVEL_MULTIPLIER[level]
    return (
        _round_to_100(archetype.mid_min * multiplier),
        _round_to_100(archetype.mid_max * multiplier),
    )


def _salaries_for(archetype: _Archetype, level: str, index: int) -> list[SeedSalary]:
    """One salary band for the offer; senior+ roles also advertise a second contract type
    (with a slightly higher B2B-style band), so the fixture shows multi-contract offers."""
    low, high = _salary_band(archetype, level)
    primary = _CONTRACTS[(index - 1) % len(_CONTRACTS)]
    salaries = [SeedSalary(primary, low, high)]
    if level in _SENIOR_LEVELS:
        secondary = _CONTRACTS[index % len(_CONTRACTS)]
        salaries.append(
            SeedSalary(secondary, _round_to_100(low * 1.1), _round_to_100(high * 1.15))
        )
    return salaries


def _build_offer(archetype: _Archetype, level: str, index: int) -> SeedOffer:
    expired = index % 18 == 5  # ~3 of 54: shows the include_expired filter
    published_days_ago = (40 + index % 12) if expired else (index * 13) % 30
    lead_tech = ", ".join(archetype.tech_stack[:3])
    return SeedOffer(
        title=f"{level} {archetype.role}",
        company=archetype.company,
        portal=archetype.portal,
        locations=list(archetype.locations),
        tech_stack=list(archetype.tech_stack),
        tech_stack_nice_to_have=list(archetype.nice_to_have),
        levels=[level],
        description=(
            f"{archetype.company} is hiring a {level} {archetype.role} to build and ship "
            f"production software using {lead_tech}. You'll join a cross-functional team, own "
            f"features end to end, and help shape our engineering culture."
        ),
        requirements=(
            f"Hands-on experience with {lead_tech}. "
            f"{'First commercial experience' if level in {'Intern', 'Junior'} else 'Solid commercial experience'} "
            f"delivering and maintaining software. Good English and teamwork."
        ),
        benefits="Private healthcare, Multisport card, flexible hours, and a training budget.",
        responsibilities=(
            f"Design, implement and maintain {archetype.role.lower()} solutions; review code; "
            "collaborate with product and other engineers."
        ),
        salaries=_salaries_for(archetype, level, index),
        published_days_ago=published_days_ago,
        expired=expired,
    )


def build_sample_offers() -> list[SeedOffer]:
    """Build the demo offer fixture: 54 offers (3 seniorities per role family), diverse across
    tech stack, portal, seniority and contract type, mostly recent with a few expired. Pure and
    deterministic — no database, no randomness — so it can be asserted on in tests."""
    offers: list[SeedOffer] = []
    index = 0
    for archetype_index, archetype in enumerate(_ARCHETYPES):
        # Three seniorities spread across the ladder; offset per archetype so that, across the
        # whole list, every one of the six levels is represented.
        levels = [_LEVEL_ORDER[(archetype_index + 2 * step) % len(_LEVEL_ORDER)] for step in range(3)]
        for level in levels:
            index += 1
            offers.append(_build_offer(archetype, level, index))
    return offers


# --- net salary (reuses the app's own calculator) ---------------------------------------

_CALCULATOR = SalaryCalculator()


def normalized_net(salary: SeedSalary) -> tuple[float, float, float] | None:
    """The standardized NET monthly PLN triple `(net_of_min, net_of_max, midpoint)` for a
    salary band, computed with the app's own `SalaryCalculator` so demo figures match the rest
    of the app. Returns None for a contract label the calculator doesn't recognize."""
    contract_type = contract_type_from_label(salary.contract_type)
    if contract_type is None:
        return None
    net_min = _CALCULATOR.calculate(contract_type, salary.min_amount).take_home
    net_max = _CALCULATOR.calculate(contract_type, salary.max_amount).take_home
    midpoint = (net_min + net_max) / 2
    return round(net_min, 2), round(net_max, 2), round(midpoint, 2)


# --- database insertion (thin I/O over the data above) ----------------------------------

_EXTERNAL_TABLES = [OfferRow.__table__, SalaryRow.__table__, NormalizedSalaryRow.__table__]


def _ensure_tables(engine: Engine) -> None:
    """Create the externally-owned tables if they don't exist yet (no-op when the real external
    schema is already present). These are intentionally not in Alembic — see module docstring."""
    Base.metadata.create_all(engine, tables=_EXTERNAL_TABLES)  # type: ignore[arg-type]  # __table__ typed FromClause, is Table at runtime


def _clear_previous_seed(session: Session) -> None:
    """Remove any rows from a previous run so re-seeding is idempotent. Only `seed-*` offers
    (and their salaries / normalized rows) are touched — real external data is never deleted."""
    seed_salary_ids = select(SalaryRow.id).where(SalaryRow.offer_id.like("seed-%"))
    session.execute(
        delete(NormalizedSalaryRow).where(NormalizedSalaryRow.salary_id.in_(seed_salary_ids))
    )
    session.execute(delete(SalaryRow).where(SalaryRow.offer_id.like("seed-%")))
    session.execute(delete(OfferRow).where(OfferRow.id.like("seed-%")))


def demo_offer_link(portal: str, offer_id: str) -> str:
    """A working, per-offer-unique link for a demo offer: the offer's real portal homepage plus
    a unique `?ref=<offer_id>` marker. Using the real portal host means the UI's "Open offer"
    button lands on a live site instead of a dead placeholder domain, while the marker keeps
    `link` (the `offers` primary key) distinct per row and namespaced so it never collides with a
    real external offer's link."""
    return f"https://{portal}/?ref={offer_id}"


@dataclass
class SeedResult:
    offers: int
    salaries: int
    normalized: int


def seed_database(
    engine: Engine, offers: list[SeedOffer], *, now: datetime | None = None
) -> SeedResult:
    """Insert the demo offers (creating the external tables if needed), replacing any rows from
    a previous run. Returns how many offer / salary / normalized-salary rows were written."""
    now = now or datetime.now(timezone.utc)
    _ensure_tables(engine)
    salaries_written = 0
    normalized_written = 0
    with Session(engine) as session:
        _clear_previous_seed(session)
        for index, offer in enumerate(offers, start=1):
            offer_id = f"seed-{index:04d}"
            published = (now - timedelta(days=offer.published_days_ago)).date().isoformat()
            expires = (
                (now - timedelta(days=3)) if offer.expired else (now + timedelta(days=30))
            ).date().isoformat()
            session.add(
                OfferRow(
                    link=demo_offer_link(offer.portal, offer_id),
                    id=offer_id,
                    title=offer.title,
                    company=offer.company,
                    tech_stack=offer.tech_stack,
                    description=offer.description,
                    requirements=offer.requirements,
                    benefits=offer.benefits,
                    locations=offer.locations,
                    published_date=published,
                    scraped_at=now,
                    portal=offer.portal,
                    tech_stack_nice_to_have=offer.tech_stack_nice_to_have,
                    requirements_nice_to_have="",
                    responsibilities=offer.responsibilities,
                    expires=expires,
                    levels=offer.levels,
                    expired=offer.expired,
                )
            )
            for salary in offer.salaries:
                salary_row = SalaryRow(
                    offer_id=offer_id,
                    contract_type=salary.contract_type,
                    min=salary.min_amount,
                    max=salary.max_amount,
                    currency="PLN",
                    period="month",
                )
                session.add(salary_row)
                session.flush()  # assign salary_row.id for the normalized FK
                salaries_written += 1
                net = normalized_net(salary)
                if net is not None:
                    net_min, net_max, midpoint = net
                    session.add(
                        NormalizedSalaryRow(
                            salary_id=salary_row.id,
                            net_of_min=net_min,
                            net_of_max=net_max,
                            midpoint=midpoint,
                            model_version="seed-v1",
                            computed_at=now,
                        )
                    )
                    normalized_written += 1
        session.commit()
    return SeedResult(
        offers=len(offers), salaries=salaries_written, normalized=normalized_written
    )


def _print_summary(offers: list[SeedOffer], *, header: str) -> None:
    active = sum(1 for o in offers if not o.expired)
    portals = sorted({o.portal for o in offers})
    levels = sorted({lvl for o in offers for lvl in o.levels}, key=_LEVEL_ORDER.index)
    contracts = sorted({s.contract_type for o in offers for s in o.salaries})
    techs = {t.lower() for o in offers for t in (*o.tech_stack, *o.tech_stack_nice_to_have)}
    print(header)
    print(f"  offers:    {len(offers)} ({active} active, {len(offers) - active} expired)")
    print(f"  portals:   {', '.join(portals)}")
    print(f"  levels:    {', '.join(levels)}")
    print(f"  contracts: {', '.join(contracts)}")
    print(f"  technologies: {len(techs)} distinct")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the database with demo job offers.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without touching the database.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    offers = build_sample_offers()
    if args.dry_run:
        _print_summary(offers, header="Would seed (dry run, no database writes):")
        return 0

    # Imported here (not at module top) so the pure builder can be used without DATABASE_URL.
    from app.config import DATABASE_URL
    from app.infrastructure.db import build_engine

    result = seed_database(build_engine(DATABASE_URL), offers)
    _print_summary(offers, header="Seeded the database:")
    print(
        f"  wrote {result.offers} offers, {result.salaries} salaries, "
        f"{result.normalized} normalized-salary rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
