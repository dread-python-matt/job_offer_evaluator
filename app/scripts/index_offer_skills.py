"""Rebuild the offer-skill index (Phase 3 of docs/skills-normalization.md).

Projects every offer's skills onto canonical concepts and replaces the `offer_skill` table, so the
browse "tech" filter matches by concept ("k8s" finds "Kubernetes"). Run after a scrape, or when the
alias map changes (so newly mapped concepts take effect).

Usage:
    uv run python -m app.scripts.index_offer_skills
"""

import argparse
import sys

from app.config import DATABASE_URL
from app.infrastructure.alias_map_skill_normalizer import AliasMapSkillNormalizer
from app.infrastructure.db import build_engine
from app.infrastructure.postgres_offer_skill_indexer import PostgresOfferSkillIndexer


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="Rebuild the offer_skill concept index from the offers table."
    ).parse_args(argv)
    normalizer = AliasMapSkillNormalizer.from_default(on_unknown=None)
    indexer = PostgresOfferSkillIndexer(build_engine(DATABASE_URL), normalizer)
    written = indexer.rebuild()
    print(
        f"Rebuilt offer_skill index: {written} (offer, concept) rows.", file=sys.stderr
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
