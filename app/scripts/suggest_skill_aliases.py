"""Propose `unmapped-token -> canonical` aliases for human review (Phase 2, step 2).

Surveys the offer corpus (like mine_skill_corpus), then ranks the unmapped tail against the
canonical concepts and prints the high-confidence suggestions. Lexical (difflib) by default;
pass --embeddings to also use OpenAI embeddings for semantic matches (needs OPENAI_API_KEY).
Read-only and advisory: it NEVER edits skill_aliases.json — a human approves rows. With --out it
also writes the suggestions as JSON for convenient review/diffing.

Usage:
    uv run python -m app.scripts.suggest_skill_aliases [--threshold 0.84] [--min-occurrences 2]
    uv run python -m app.scripts.suggest_skill_aliases --embeddings --out suggestions.json
"""

import argparse
import json
import sys

from app.application.skill_corpus import summarize_skill_corpus
from app.application.skill_suggestions import render_suggestions, suggest_aliases
from app.config import DATABASE_URL, OPENAI_API_KEY
from app.infrastructure.alias_map_skill_normalizer import AliasMapSkillNormalizer
from app.infrastructure.db import build_engine
from app.scripts.mine_skill_corpus import offer_token_counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Suggest skill-alias mappings (lexical; optionally embedding-assisted) for review."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.84,
        help="minimum similarity to suggest (0-1)",
    )
    parser.add_argument(
        "--min-occurrences", type=int, default=2, help="ignore tokens rarer than this"
    )
    parser.add_argument(
        "--embeddings",
        action="store_true",
        help="also use OpenAI embeddings for semantic matches (needs OPENAI_API_KEY)",
    )
    parser.add_argument("--out", help="optional path to also write suggestions as JSON")
    args = parser.parse_args(argv)

    embedder = None
    if args.embeddings:
        if not OPENAI_API_KEY:
            print("--embeddings requires OPENAI_API_KEY to be set.", file=sys.stderr)
            return 2
        from app.infrastructure.openai_skill_embedder import OpenAISkillEmbedder

        embedder = OpenAISkillEmbedder.create(OPENAI_API_KEY)

    counts = offer_token_counts(build_engine(DATABASE_URL))
    if not counts:
        print("No offer skill tokens found.", file=sys.stderr)
        return 1
    # on_unknown=None: this tool classifies tokens itself; it must not also log every miss.
    normalizer = AliasMapSkillNormalizer.from_default(on_unknown=None)
    report = summarize_skill_corpus(counts, normalizer)
    suggestions = suggest_aliases(
        report.unknown_by_frequency,
        normalizer.canonical_labels,
        threshold=args.threshold,
        embedder=embedder,
        min_occurrences=args.min_occurrences,
    )
    print(render_suggestions(suggestions))

    if args.out:
        payload = [
            {
                "alias": s.token,
                "canonical": s.canonical_id,
                "score": round(s.score, 4),
                "method": s.method,
                "occurrences": s.occurrences,
            }
            for s in suggestions
        ]
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(payload)} suggestions to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
