"""Survey the offer corpus's skill tokens and report canonical coverage + the unmapped tail.

A dev/admin tool (Phase 2, step 1 of docs/skills-normalization.md): it reads the offers'
`tech_stack` / `tech_stack_nice_to_have` lists, normalizes each token with the shipped alias
map, and prints how much resolves plus the most frequent *unmapped* tokens — the highest-ROI
entries to add to app/infrastructure/data/skill_aliases.json. Read-only; touches no app state.

Usage:
    uv run python -m app.scripts.mine_skill_corpus [--top N]
"""

import argparse
import sys
from collections import Counter

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.application.skill_corpus import render_coverage, summarize_skill_corpus
from app.config import DATABASE_URL
from app.infrastructure.alias_map_skill_normalizer import AliasMapSkillNormalizer
from app.infrastructure.db import build_engine
from app.infrastructure.orm_models import OfferRow


def offer_token_counts(engine: Engine) -> Counter[str]:
    """Frequency of every (non-blank) required/nice-to-have skill token across all offers."""
    counts: Counter[str] = Counter()
    with Session(engine) as session:
        for required, nice in session.execute(
            select(OfferRow.tech_stack, OfferRow.tech_stack_nice_to_have)
        ):
            for token in (*(required or []), *(nice or [])):
                if token and token.strip():
                    counts[token] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Survey offer skill tokens and report coverage."
    )
    parser.add_argument(
        "--top", type=int, default=50, help="how many unmapped tokens to list"
    )
    args = parser.parse_args(argv)

    counts = offer_token_counts(build_engine(DATABASE_URL))
    if not counts:
        print("No offer skill tokens found.", file=sys.stderr)
        return 1
    # on_unknown=None: this tool classifies tokens itself; it must not also log every miss.
    normalizer = AliasMapSkillNormalizer.from_default(on_unknown=None)
    print(render_coverage(summarize_skill_corpus(counts, normalizer), top=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
