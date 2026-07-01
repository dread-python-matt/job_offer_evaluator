# Skills Normalization — Implementation Report & Runbook

Status, what's shipped, what's left, and **how to operate it** (commands). The *design rationale*
lives in [`skills-normalization.md`](skills-normalization.md); this file is the progress report +
operations runbook. Last updated: **2026-07-01**.

---

## 1. Status at a glance

| # | Item | State |
|---|---|---|
| 1 | Operational hardening of the browse index (self-building, staleness-aware, missing-table tolerant) | ✅ Done |
| 2 | Evidence-aware scoring: **un-evidenced self-claim cap** | ✅ Done |
| 3 | **Unknown-token curation table** (persist the unmapped tail) | ✅ Done |
| 6 | **Alias-map expansion + Python/IT research pass** (64 → **223** canonical concepts, **131** aliases; PL variants) | ✅ Done |
| — | First real-corpus curation survey (coverage = **57.3%**) | ✅ Run (findings in §3) |
| — | Second curated map pass (`.net` bug fix + ~20 concepts) | ⏳ Proposed, not applied |
| 4 | `match_confidence` weighting in scoring | ⛔ Deferred (needs a sub-1.0 source → #5) |
| 5 | Tier-2 pgvector semantic runtime fallback | ⛔ Deferred (metrics-gated) |
| — | Live-stream unknown capture (buffered DB writes) | ⛔ Deferred (corpus snapshot covers the bulk) |

---

## 2. What has been done

### #1 — Operational hardening of the `offer_skill` browse index
The browse `tech` filter matches by **canonical concept** via an app-owned `offer_skill` projection
(one row per offer×concept). Hardening added:
- **Self-building on deploy.** The Docker `CMD` runs the indexer after migrations, before serving.
- **Missing-table tolerance.** If the scraper-owned `offers` table doesn't exist yet, the indexer
  logs and no-ops (returns 0) instead of crashing — so it can run unconditionally at boot.
- **Staleness signal.** Each rebuild stamps `offer_skill_index_meta` (migration `0019`) with the
  alias-map `version`, row count, and build time. `--status` reports `fresh` / `STALE` / `NOT BUILT`.
  This is what fixed the original *"failed to load offers"* class of bug (an unbuilt/absent index is
  now observable, not a silent 500 / empty result).

Files: `app/infrastructure/postgres_offer_skill_indexer.py`, `orm_models.py`
(`OfferSkillRow`, `OfferSkillIndexMeta`), `alembic/versions/0018_*`, `0019_*`,
`app/scripts/index_offer_skills.py`, `Dockerfile`.

### #2 — Un-evidenced self-claim cap (scoring)
A matched skill's weight uses two features: self-rating (1–5) and whether it's **evidenced** (used in
a real project/experience). Evidence already doubled the weight and gave evidenced-but-unrated skills
a baseline. Added: **`UNEVIDENCED_SELF_RATING_CAP = 0.6`** — a bare self-claim counts at most like a
3/5, so an un-evidenced 4–5/5 is reined in ("juniors over-claim"). It's the single calibration knob:
raise toward 1.0 to trust self-claims more, `1.0` disables it.

File: `app/infrastructure/skill_utils.py`.

### #3 — Unknown-token curation table
The unmapped (Tier-0 miss) tail is persisted to `unknown_skill_token` (migration `0020`): normalized
token, occurrences, example raw forms. **Snapshot-replace** semantics (counts reflect the current
corpus, never double-counted). Populated by `mine_skill_corpus --persist`; read by
`suggest_skill_aliases --from-db`. The live request path still only logs misses on `app.skills`
(buffering live misses into the table is a possible later add-on).

Files: `app/application/ports.py` (`UnknownSkillToken`, `UnknownSkillTokenRepository`),
`app/application/skill_corpus.py` (`collect_unknown_tokens`),
`app/infrastructure/postgres_unknown_skill_token_repository.py`, `orm_models.py`,
`alembic/versions/0020_*`.

### #6 — Alias-map expansion
`skill_aliases.json` grew **64 → 176 canonical concepts**, **61 aliases**, **16 `never_merge`
guards** (was 8). Added languages, frontend/backend frameworks, databases, big-data/messaging,
cloud/devops/observability, testing, mobile, ML/AI, protocols/methodologies, and **Polish aliases**
(`uczenie głębokie`→deep learning, etc.). Only deterministic, unambiguous entries; ambiguous short
forms (`tf`, `ml`, `rn`, `ai`, `ps`, `elk`) deliberately omitted. New collision guards:
`c≠objectivec`, `sql≠mssql/oracle/mariadb`, `mysql≠mariadb`, `javascript≠typescript`,
`nextjs≠nestjs`, `machinelearning≠deeplearning`. The `version` bump (`2026-07-01` → `2026-07-02`)
correctly marked the index stale until rebuilt.

File: `app/infrastructure/data/skill_aliases.json`.

---

## 3. What can be done next

### 3a. Second curated map pass (highest ROI — concrete, from real data)
> **Update (2026-07-01):** largely applied via a **Python/IT-stack alias research pass**. The map
> grew to **223 canonical concepts / 131 aliases** (from 180 / 66); `version` → `2026-07-04`.
> Added the earlier slice (Pydantic, Alembic, Clean Code, LLM, and the `.net`→`dotnet` fix), then
> **+43 canonicals**: Python ecosystem (SQLAlchemy, Celery, Poetry, Conda, Jinja, Gunicorn,
> Uvicorn, asyncio, BeautifulSoup, Scrapy, Seaborn, Plotly, Streamlit, mypy, Ruff, Black, flake8,
> Pylint), tools (GitHub, GitLab, Jira, Confluence, Azure DevOps, Power BI), data/ML (ETL, MLOps,
> MLflow, NoSQL, Data Science, Data Engineering, Big Data, RAG, GenAI), formats (JSON, YAML, XML),
> OS/infra (IaC, Windows, Unix), Bootstrap, methodology (Integration Testing, BDD, Functional
> Programming) — plus **~68 aliases** (abbreviations, alt-spellings, vendor/full names, Polish
> variants) and **+13 `never_merge` guards**. Three pre-existing redundant aliases were removed and
> a **structural-invariant test** now rejects redundant / canonical-shadowing aliases.
> **Deliberately skipped** (weak standalone matching signal — see the "Generic" bullet below):
> `ai`, `cloud`, `api`, `security`, `testing`, `networking`; and LangGraph (niche). Rebuild the
> browse index to pick the new concepts up.

The 2026-06-30 corpus survey (`mine_skill_corpus --top 40`) reported **57.3% coverage**
(9,779 / 17,068 occurrences; 1,811 distinct unmapped). Key findings:

- **✅ FIXED (2026-07-01):** **`.net` (49 occ) now resolves to `dotnet`.** It's in `protected`
  (keeps its dot) but had no `".net" → dotnet` alias, so it passed through (`asp.net` / `.net core`
  mapped; bare `.net` didn't). Added alias `".net": "dotnet"`.
- **Alias quick wins:** `microsoft azure` (88) → `azure`; `pyspark` (60) → `spark`.
- **New canonicals worth adding (~20):** Jira (100), Confluence (56), GitHub (68), GitLab (50),
  Azure DevOps (75), Power BI (56), ETL (91), LLM (90), MLOps (59), NoSQL (58),
  IaC (35 + `infrastructureascode` 33 = 68 combined), JSON (30), MLflow (27), LangGraph (30),
  RAG (40), GenAI (39), Data Science (42), Data Engineering (42), Big Data (46), Windows (30),
  Unix (28).
- **Correctly unmapped (NOT tech skills — leave):** `english` (175), `polish` (90),
  `communicationskills` (92), `analyticalskills` (37), `degree` (56). These ~450 occurrences depress
  the headline %; real *tech-token* coverage is meaningfully higher than 57%.
- **Generic — product judgment call:** `ai` (278), `cloud` (167), `api` (114), `security` (78),
  `testing` (62), `networking` (36). High counts but weak matching signals as standalone concepts.

Each batch must keep the safety discipline: unambiguous only, add `never_merge` guards for new
collisions, add merge/non-merge tests, **bump the map `version`**, then rebuild the index.

### 3b. Deferred (gated)
- **#4 `match_confidence` weighting** — `CanonicalSkill.confidence` is plumbed but always 1.0; it
  only becomes useful once a sub-1.0 source exists (#5). Building it now would be dead plumbing.
- **#5 Tier-2 pgvector runtime fallback** — semantic match for the still-unmapped tail at reduced
  confidence. Only worth it if, after curation, the unknown-token table shows a meaningful tail.
- **Live-stream unknown capture** — buffer per-process misses and flush to `unknown_skill_token`
  (cross-worker accumulation). The corpus snapshot already covers the dominant source (offers).

### 3c. Minor correctness notes (not urgent)
- `SkillCanonicalizer._canon_all` maps tokens in place **without dedup**, so an offer listing both
  `JS` and `JavaScript` double-counts the concept in the weighted-ratio denominator (documented;
  mostly harmless).
- `go`, `c`, `r`, `sql` are canonical ids; safe only because tech-stack fields are curated lists,
  not free text.
- Human-language proficiency (`english`, `polish`) and soft skills (`communication skills`) are
  intentionally **not** tech skills; a separate taxonomy for them is out of scope here.

---

## 4. How it works — COMMANDS (runbook)

> All commands are run from the repo root. They read `DATABASE_URL` from `.env`. Run **one command
> per invocation** (project convention — no `&&`/`|` chaining; the Docker `CMD` is the one place
> chaining is used, and that's the container's shell, not your dev shell).

### 4.1 Command reference

| Command | Reads | Writes | What it does |
|---|---|---|---|
| `uv run alembic upgrade head` | migrations | app-owned tables | Creates/updates schema. The skills tables are `offer_skill` (`0018`), `offer_skill_index_meta` (`0019`), `unknown_skill_token` (`0020`). Idempotent. |
| `uv run python -m app.scripts.index_offer_skills` | `offers` | `offer_skill`, `offer_skill_index_meta` | **Rebuilds** the browse concept index (delete-all + reinsert in one transaction) and stamps the meta row. No-ops if `offers` doesn't exist yet. |
| `uv run python -m app.scripts.index_offer_skills --status` | meta table | — | Prints `fresh` / `STALE` / `NOT BUILT` (compares the index's built-from map version to the current one). No rebuild. |
| `uv run python -m app.scripts.mine_skill_corpus [--top N] [--persist]` | `offers` | `unknown_skill_token` (only with `--persist`) | Surveys offer skill tokens; prints coverage % + the top-N unmapped tokens. `--persist` snapshots the whole unmapped tail into the table for curation. |
| `uv run python -m app.scripts.suggest_skill_aliases [--threshold T] [--min-occurrences N] [--embeddings] [--from-db] [--out FILE]` | `offers` or `unknown_skill_token` (`--from-db`) | nothing (advisory) / `FILE` | Ranks the unmapped tail against canonical concepts and prints `alias → canonical` suggestions ≥ threshold. **Never edits the map.** |

Flag notes:
- `mine_skill_corpus --top N` — how many unmapped tokens to print (default 50). `--persist` is the
  only side-effecting flag.
- `suggest_skill_aliases` — `--threshold` (default `0.84`) minimum similarity; `--min-occurrences`
  (default `2`) ignores rarer tokens; `--embeddings` adds OpenAI embedding-cosine matches (needs
  `OPENAI_API_KEY`, costs a tiny one-off); `--from-db` reads the persisted tail instead of surveying
  live; `--out FILE` also writes suggestions as JSON for diffing.

### 4.2 First-time / fresh-DB setup
```
uv run alembic upgrade head                         # create offer_skill, *_meta, unknown_skill_token
uv run python -m app.scripts.index_offer_skills     # build the browse index from offers
uv run python -m app.scripts.index_offer_skills --status   # expect: fresh
```
If `offers` isn't seeded/scraped yet, the indexer prints `NOT BUILT` and no-ops — that's fine; run it
again after offers exist.

### 4.3 The curation loop (growing the alias map from real data)
```
# 1. Survey coverage + snapshot the unmapped tail
uv run python -m app.scripts.mine_skill_corpus --persist

# 2. Get ranked alias suggestions from the persisted tail (add --embeddings for semantic matches)
uv run python -m app.scripts.suggest_skill_aliases --from-db --min-occurrences 5

# 3. HUMAN STEP: review suggestions; add approved rows to
#    app/infrastructure/data/skill_aliases.json  (canonical concepts + aliases),
#    add never_merge guards for any new collision risk, and BUMP the "version" field.

# 4. Rebuild the browse index so it reflects the new concepts
uv run python -m app.scripts.index_offer_skills

# 5. Confirm
uv run python -m app.scripts.index_offer_skills --status   # expect: fresh
```
Notes:
- Step 3 is deliberately manual — the tooling **never auto-edits the map** (the guard against
  over-merging). Suggestions are advisory.
- **Matching** picks up map changes immediately (it normalizes on read). Only the **browse** index
  needs the rebuild in step 4.
- Skip `--persist` / `--from-db` to run the loop purely in-memory (survey live, suggest live) without
  touching `unknown_skill_token`.

### 4.4 When is the index stale, and how is it detected?
The alias map's `version` is stamped into `offer_skill_index_meta` at each rebuild. Editing the map
(and bumping `version`) without rebuilding makes `--status` report **STALE**. The Docker image
rebuilds on every deploy, so a map change shipped in a deploy is reflected automatically; for local
dev you rerun `index_offer_skills` yourself (step 4 above).

### 4.5 Deploy (Docker) behavior
```
CMD: sh -c "uv run alembic upgrade head \
            && (uv run python -m app.scripts.index_offer_skills || true) \
            && uv run python main.py"
```
- Migrations **must** succeed (`&&`).
- The index build is **best-effort** (`|| true`): a failed/empty build degrades only the browse tech
  filter, so it never blocks the API from serving; it no-ops before the first scrape.
- Then the API starts.

---

## 5. How it works — mechanics (brief)

- **Tier-0 normalizer** (`AliasMapSkillNormalizer`): per token → casefold → fold diacritics
  (incl. Polish `ł`) → collapse separators (except `protected` like `.net`; `+`/`#` are not
  separators so `c++`/`c#` survive) → alias lookup → canonical check → passthrough. O(1) dict
  lookups, request-path safe. Unknown tokens are logged once per process on `app.skills`.
- **Canonicalization boundary** (`SkillCanonicalizer`): rewrites the candidate + offers onto
  canonical ids on **scoring-only copies** at match time — display strings and stored data are
  untouched. No-op without a normalizer (so literal-match tests still pass).
- **Scoring** (`skill_utils.weighted_skill_ratio`): per matched skill, evidenced → `rating/5 × 2`
  (or `EVIDENCED_BASELINE × 2` if unrated); un-evidenced → `min(rating/5, UNEVIDENCED_SELF_RATING_CAP)`;
  neither → 0.
- **Browse index** (`offer_skill`): SQL `EXISTS` against canonical ids; built by
  `PostgresOfferSkillIndexer.rebuild()`; freshness in `offer_skill_index_meta`.
- **Curation store** (`unknown_skill_token`): snapshot of the unmapped tail by frequency, the
  highest-ROI map-growth candidates.

### Safety invariants
- Nothing auto-merges; the map is hand-edited and version-controlled; suggestions are advisory.
- `never_merge` pairs are asserted by tests (`test_default_map_honors_its_never_merge_pairs` walks
  every pair) — a regression that merges them fails CI.
- Human languages and soft skills are intentionally not normalized as tech skills.

---

## 6. File map

| Concern | File(s) |
|---|---|
| Canonical concept + ports | `app/domain/skills.py` (`CanonicalSkill`, `SkillNormalizer`, `SkillEmbedder`) |
| Deterministic normalizer | `app/infrastructure/alias_map_skill_normalizer.py` |
| Alias map data | `app/infrastructure/data/skill_aliases.json` |
| Canonicalization boundary | `app/application/skill_canonicalization.py` |
| Scoring weights | `app/infrastructure/skill_utils.py` |
| Browse index | `app/infrastructure/postgres_offer_skill_indexer.py`, `orm_models.py` |
| Curation store + survey | `app/application/skill_corpus.py`, `app/application/ports.py`, `app/infrastructure/postgres_unknown_skill_token_repository.py` |
| Suggester | `app/application/skill_suggestions.py`, `app/infrastructure/openai_skill_embedder.py` |
| Scripts (ops) | `app/scripts/{index_offer_skills,mine_skill_corpus,suggest_skill_aliases}.py` |
| Migrations | `alembic/versions/0018_*`, `0019_*`, `0020_*` |
