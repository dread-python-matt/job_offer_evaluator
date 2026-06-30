# Skills Normalization — Design & Implementation Plan

How to stop comparing skill strings literally and instead collapse synonyms, abbreviations,
casing, diacritics, and PL/EN variants to **one canonical concept** before anything is compared.
Every downstream number (skill ratio, cheap pre-filter, AI pre-ranking, browse filter) currently
inherits string-match errors; canonicalizing once at the boundary fixes all of them at the root.

> Scope: backend matching pipeline (`app/domain`, `app/application`, `app/infrastructure`). The
> `offers` table is **scraper-owned and read-only** here, which shapes *where* normalization can
> run — see §4. This is a plan, not yet implemented.

---

## 1. Current state (the problem)

All skill comparison today is **literal string matching after `.lower()` / `.casefold()`**:

| Where | Code | What it does |
|---|---|---|
| Core scorer & cheap pre-filter | `skill_utils.weighted_skill_ratio` | `ratings.get(skill.lower())` — **exact** dict hit; evidence bonus `×2` via **exact** set membership in `practiced_skills` |
| Deterministic scoring | `scoring_strategies.SkillBasedScorer` | sums `weighted_skill_ratio` over `tech_stack` + `tech_stack_nice_to_have` |
| AI pre-filter | `offer_filters.SkillFilter` | same ratio ≥ `min_score` to skip LLM calls |
| Sets | `UserProfile.skill_names()`, `Offer.skill_set()` | `{x.lower()}` |
| Browse tech filter | `postgres_offer_repository._apply_sql_filters` | SQL `LIKE %tech%` over `tech_stack` JSON cast to text |

Consequences: `JS` ≠ `JavaScript`, `node` ≠ `Node.js` ≠ `nodejs`, `postgres` ≠ `PostgreSQL`,
`k8s` ≠ `Kubernetes`, `React.js` ≠ `ReactJS`, `angularjs` ≠ `Angular`, and PL ≠ EN
(`baza danych` ≠ `database`, `testy jednostkowe` ≠ `unit testing`). A candidate who wrote "JS"
scores **0** against an offer requiring "JavaScript". Worse, a skill **evidenced in a project but
not in the self-rated `skills` list** contributes `0` today (`ratings.get` misses it) — the
opposite of "evidence should count most".

---

## 2. Goal & principles

1. **Canonicalize before comparing.** Map every raw skill token → a stable canonical concept; do
   it once at the boundary; let all existing comparison logic operate on canonical tokens.
2. **Deterministic core, ML only as a curation aid.** A static alias map does the cheap ~90% with
   **zero ML in the hot path** (O(1) dict lookups). Embedding/fuzzy similarity is used **offline**
   to *grow the map* (and optionally as a confidence-weighted runtime fallback later) — never as a
   silent per-request black box.
3. **Keep the structured signal alive.** Ratings (1–5) and evidence ("practiced in a real
   project") become **explicit, tunable features**, and **evidenced skills outweigh self-claimed
   ones** (juniors over-claim).
4. **Safety over recall.** Never auto-merge below a high confidence threshold; protect
   punctuation-significant names; ship with regression tests for **known non-merges**
   (`Java` ≠ `JavaScript`, `C` ≠ `C#` ≠ `C++`, `Go` ≠ "go" the word).
5. **Fit the architecture.** Normalization is an **application concern** using a **port**; the
   alias-map and any embeddings/pgvector live in **infrastructure**; the **domain stays pure**.
6. **Minimal runtime dependencies.** Prefer stdlib; the alias map is a JSON resource; heavy ML
   (sentence-transformers / pgvector) is confined to an **optional dev/tooling dependency group**.

---

## 3. Design overview — three tiers

```
raw token ("Node.JS", "k8s", "baza danych", "ReactJS")
   │
   ▼  Tier 0 — DETERMINISTIC (runtime, hot path, no ML)
   fold case  →  fold diacritics  →  normalize separators/punctuation
   →  expand abbreviations  →  alias → canonical lookup
   │
   ├── hit  → CanonicalSkill(id="nodejs", confidence=1.0)
   └── miss → pass through normalized surface form, confidence=1.0-for-self,
              and RECORD to the unknown-token log  ──────────────┐
   │                                                             │
   ▼  Tier 1 — CURATION (offline tooling, grows the map)         │
   embed unknown tokens + canonical taxonomy labels; fuzzy +     │
   cosine nearest-canonical above threshold → human review →     │
   approved entries baked into the static alias map  ◄───────────┘
   │
   ▼  Tier 2 — SEMANTIC FALLBACK (optional, runtime, later)
   only the still-unmapped tail: pgvector ANN against canonical
   embeddings, contributes at REDUCED confidence (= cosine sim)
```

Tier 0 ships first and delivers most of the value. Tiers 1–2 are additive.

---

## 4. Where normalization runs (the read-only-offers constraint)

The idea says "normalize once at write time (profile save, offer index)." That is fully realizable
for the **profile** (app-owned, writable) but **not for offers** — the `offers` table belongs to
the scraper and we only read it. So:

- **Recommended baseline:** canonicalization is a **pure function applied at the matching
  boundary (read time)**, in the application layer, on both the candidate profile and the fetched
  offers, *before* filtering/scoring. Deterministic Tier 0 is microseconds over ~10–30 tokens per
  offer, so on-read normalization is cheap and **stateless** (no staleness, no cache to invalidate
  when the map grows). Stored strings remain the source of truth and display value.
- **Optimization (later, optional):** persisted **write-time projections** to realize the
  "normalize once" ideal at scale, each tagged with a **`map_version`** so a map update
  invalidates them:
  - profile: store a `canonical_skills` projection in the `user_profile` JSON doc at save;
  - offers: an **app-owned** `offer_skill_index(offer_id, map_version, required[], nice_to_have[])`
    table, rebuilt by a batch job over `offers` and filled lazily on cache-miss at read. Required
    only if profiling shows on-read normalization is a bottleneck **or** to push a canonical tech
    filter into SQL for browse (see below).

**Browse vs. match path.** The match path (`candidate_offers`) does **not** filter tech in SQL
(skills are *scored* in Python), so on-read canonicalization is a perfect fit. The browse tech
filter *is* pushed into SQL (`LIKE %tech%`); to make that canonical we either (a) normalize the
query term and keep the substring match as a coarse prefilter (Phase 1, good enough), or (b) add
the `offer_skill_index` table and filter on it in SQL (the proper fix, Phase 3).

---

## 5. Tier 0 — the deterministic normalizer

Pure pipeline, applied per token:

```
def normalize(raw: str) -> CanonicalSkill:
    s = raw.strip().casefold()
    s = fold_diacritics(s)              # ł→l, ą→a, ś→s, … (see note)
    s = normalize_separators(s)         # collapse "  ", "node.js"/"node js"→"nodejs"
                                        # BUT keep protected tokens intact (c#, c++, .net, f#)
    s = ABBREVIATIONS.get(s, s)         # k8s→kubernetes, js→javascript, ts→typescript, …
    canonical = ALIAS_TO_CANONICAL.get(s)
    if canonical is not None:
        return CanonicalSkill(id=canonical, confidence=1.0, source="alias")
    record_unknown(raw, s)              # feeds Tier 1 curation
    return CanonicalSkill(id=s, confidence=1.0, source="passthrough")
```

- **Diacritics.** Python's `unicodedata.NFKD` + strip combining marks does **not** fold Polish `ł`
  (it has no canonical decomposition). Use a **small hand-rolled PL fold table**
  (`ł→l, ą→a, ć→c, ę→e, ń→n, ó→o, ś→s, ź/ż→z`) — zero dependency, fully controlled — or the
  `unidecode` library if broader transliteration is wanted. Recommend the hand-rolled table first.
- **Protected tokens.** A set of names where punctuation is meaningful (`c#`, `c++`, `f#`, `.net`,
  `node.js` kept distinct from a hypothetical "node") bypass `normalize_separators` so we don't
  destroy `c++ → c`.
- **Alias map format** (`app/infrastructure/data/skill_aliases.json`), human-editable and
  version-controlled:

```json
{
  "version": "2026-07-01",
  "canonical": {
    "javascript": { "label": "JavaScript", "esco": "http://data.europa.eu/esco/skill/…", "tags": ["lang"] },
    "kubernetes": { "label": "Kubernetes", "tags": ["devops"] }
  },
  "aliases": {
    "js": "javascript", "ecmascript": "javascript", "node": "nodejs", "node.js": "nodejs",
    "k8s": "kubernetes", "postgres": "postgresql", "baza danych": "database"
  },
  "protected": ["c#", "c++", "f#", ".net"],
  "never_merge": [["java", "javascript"], ["go", "golang-is-ok-but-go-word-no"]]
}
```

`never_merge` pairs are asserted by tests, not used at runtime — they encode the non-merges we
must never regress.

---

## 6. Unknown-token capture (closing the loop)

Every Tier-0 miss is recorded so the map can be grown from *our* corpus:

- **Structured log** (reuse the new logging stack): `logging.getLogger("app.skills").info("unknown
  skill token", extra={"event": "unknown_skill_token", "token": raw, "normalized": s})` — queryable
  in the aggregator.
- **Aggregation table** `unknown_skill_token(normalized PK, raw_samples[], count, first_seen,
  last_seen)` (app-owned, Alembic migration) so curation can sort the tail by frequency.

A skill that recurs a lot but stays unknown is the highest-ROI map entry to add.

---

## 7. Tier 1 — embedding-assisted curation (offline)

A dev/admin script (`app/scripts/suggest_skill_aliases.py`) proposes `alias → canonical` for the
unknown-token log:

1. Build the canonical concept set + their labels/synonyms from the **seed sources** (§9).
2. **Embed** canonical labels and unknown tokens into one vector space (multilingual model so PL
   and EN land together — e.g. `paraphrase-multilingual-MiniLM-L12-v2`, or a provider embeddings
   API; see §9).
3. For each unknown token, take the **nearest canonical** by cosine + a `rapidfuzz` lexical score;
   above a **high threshold** emit a suggestion, below it leave it for manual handling.
4. A human reviews suggestions (CSV/JSON diff); approved rows are appended to `skill_aliases.json`
   and the `version` is bumped.

Embeddings here run **offline over a small token list**, so this can use a provider embeddings API
(no heavy local dependency) or `sentence-transformers` (offline/private) — either way it never
touches the request path. Persisted canonical embeddings (pgvector) are optional and only needed
for Tier 2.

---

## 8. Tier 2 — optional runtime semantic fallback

Only if Tier 0 + grown map leave a meaningful tail. For still-unmapped tokens, look up the nearest
canonical concept via **pgvector** ANN against a `canonical_skill_embedding` table and accept it
**only above a strict threshold**, contributing at **reduced confidence = cosine similarity**
(see §9 for storage). This keeps fuzzy matches from ever counting as much as a deterministic hit
and is fully auditable (we log what mapped to what, with the score).

---

## 9. Structured features & scoring (ratings + evidence)

Make the structured signal explicit. Replace the implicit `rating/5 × (2 if practiced)` with named,
tunable features per matched (canonical) skill:

| Feature | Meaning | Notes |
|---|---|---|
| `required` vs `nice_to_have` | which offer list it came from | already separated |
| `self_rating` | candidate's 1–5 → 0.2–1.0 | self-claimed signal |
| `evidenced` | appears in a project/experience `tech_stack` | the trustworthy signal |
| `match_confidence` | 1.0 for deterministic alias, `<1.0` for fuzzy/embedding | gates safety |

Scoring changes (all in the **pure domain**, behind the same `OfferScorer` interface):

- **Evidenced skills outweigh self-claimed.** Tunable weights, e.g. `contribution = base ×
  evidence_factor × match_confidence`, where `evidence_factor` is high when evidenced and an
  un-evidenced high self-rating is **capped** (juniors over-claim). Weights live in config/constants
  so they can be calibrated.
- **Fix the evidenced-but-unrated gap.** A canonical skill practiced in a project but absent from
  the self-rated `skills` list should get a **baseline weight** (today it scores 0). This alone is
  a meaningful accuracy win.
- Determinism preserved: with all-deterministic matches and current weights, behavior reduces to
  today's, so changes are isolated and testable.

---

## 10. Data sources & libraries

### Taxonomies / seed data

| Source | Use | Fit / licensing |
|---|---|---|
| **ESCO** (EU Skills/Competences/Occupations) | **Primary** canonical concepts + synonyms. Free download (CSV/JSON-LD) in 27 languages **incl. Polish & English**, with `preferredLabel` + `altLabels` per language and a skills hierarchy (incl. ICT/technology). Also the taxonomy to back Tiers 1–2. | Free, multilingual — **best fit for a PL/EN app**. Verify exact CSV columns on download. |
| **Stack Overflow tag synonyms** | Cheap, tech-specific `alias→canonical` seed (`js→javascript`, `reactjs→react`). Community-curated; via the StackExchange API `/tags/synonyms` or the data dump. | Tech-centric, high quality for software. CC BY-SA — attribute. |
| **GitHub Linguist `languages.yml`** | Programming-language names + aliases. | MIT. Great for the `lang` slice. |
| **Lightcast Open Skills** | 34k+ skills incl. *software skills*, machine IDs. | **API/contract-based**, English-centric — use as optional reference, not the PL/EN backbone. |
| **Our own corpus** | Seed/validate the map from *actual* tokens: candidate `skills` + project/experience `tech_stack`, and offer `tech_stack` / `tech_stack_nice_to_have` / requirements text. | Highest signal — the map must fit our data. |

### Python libraries

| Need | Recommendation | Dependency tier |
|---|---|---|
| Diacritics fold | hand-rolled PL table (0 dep) or `unidecode` | runtime (prefer 0-dep) |
| Fuzzy near-miss / typos | **`rapidfuzz`** (MIT, fast C++) | runtime (small) or tooling |
| Alias map storage | JSON (stdlib) | runtime |
| Embeddings (curation/Tier 2) | provider API (OpenAI `text-embedding-3-small` / Gemini — wiring already exists) **or** `sentence-transformers` w/ `paraphrase-multilingual-MiniLM-L12-v2` | **optional `dev`/`embeddings` extra** (keeps `torch` out of runtime) |
| Vector store / ANN | **pgvector** in the existing Postgres (HNSW/IVFFlat) | optional extra + DB extension |
| Skill extraction from free text (stretch) | Nesta **`ojd_daps_skills`** (ESCO/Lightcast, maintained) — over `skillNer` (stale since 2021) | tooling only |

---

## 11. Architecture mapping

Dependencies still point inward; the domain gains no framework/IO knowledge.

- **Domain** (`app/domain/`)
  - `skills.py` (new): `CanonicalSkill` value object (`id`, `label`, `confidence`, `source`); pure
    feature/scoring helpers. `SkillNormalizer` **port** may live here or in application.
  - `scoring.py` / scorer: unchanged interface; scoring math updated to use canonical tokens +
    explicit features (§9).
- **Application** (`app/application/`)
  - `SkillNormalizer` port (`normalize`, `normalize_many`) in `ports.py`.
  - A `canonicalize_profile` / `canonicalize_offer` step (application service) applied in
    `MatchOffersUseCase` / `MatchOffersWithAiUseCase` **before** the `FilterChain`/scorer, so the
    domain receives canonical `UserProfile` / `Offer` views. `SaveUserProfileUseCase` may also
    persist the canonical projection (optimization).
- **Infrastructure** (`app/infrastructure/`)
  - `alias_map_skill_normalizer.py`: deterministic Tier-0 adapter; loads
    `data/skill_aliases.json`; records unknowns.
  - `unknown_skill_token_repository.py` (+ ORM row + Alembic migration).
  - (Tier 2, optional) `pgvector_skill_normalizer.py` + `canonical_skill_embedding` table.
- **Composition root** (`main.py`): build the normalizer once, inject into the use cases (DI by
  override, like every other port).
- **Scripts** (`app/scripts/`): `mine_skill_corpus.py` (seed/survey), `suggest_skill_aliases.py`
  (Tier 1 curation).
- **Migrations**: `unknown_skill_token`; later `offer_skill_index`, `canonical_skill_embedding`
  (the last needs the `vector` extension).

---

## 12. Phased rollout

**Phase 1 — deterministic MVP (no heavy deps, biggest win).**
Normalizer port + `AliasMapSkillNormalizer` + seeded `skill_aliases.json` (ESCO ICT slice + SO tag
synonyms + Linguist + corpus survey) → canonicalize candidate & offers at the matching boundary →
update scoring to canonical + explicit features (incl. the evidenced-but-unrated fix) →
unknown-token table + structured log → tests for known **merges and non-merges**. Ship.

**Phase 2 — curation tooling.** `mine_skill_corpus.py` + `suggest_skill_aliases.py` (embeddings +
rapidfuzz) + review workflow; iterate the map from the unknown-token log. Optionally persist
profile/offer canonical projections (write-time, `map_version`-tagged).

**Phase 3 — semantic fallback / scale.** pgvector `canonical_skill_embedding`, confidence-weighted
Tier-2 runtime fallback, and the `offer_skill_index` table to push canonical tech filtering into
SQL for browse. Only if metrics justify it.

---

## 13. Testing strategy (TDD)

- **Normalizer units**: case, diacritics (incl. `ł`), separators (`Node.js`/`node js`/`nodejs`),
  abbreviations (`k8s`, `js`, `ts`), alias→canonical, unknown pass-through **and** logging.
- **Known-merge table**: `JS|ECMAScript→javascript`, `k8s→kubernetes`, `postgres→postgresql`,
  `reactjs→react`, PL/EN pairs.
- **Known-non-merge table** (regression guard): `java`≠`javascript`, `c`≠`c#`≠`c++`,
  `react`≠`react native`, `sql`≠`mysql`/`postgresql`; language requirements (`język angielski`,
  `English`) are **not** treated as tech skills.
- **Scoring**: evidenced > self-claimed; evidenced-but-unrated > 0; confidence-weighted fuzzy < a
  deterministic hit; determinism reduces to today's numbers with all-deterministic input.
- **Golden corpus test**: a fixture sampled from real tokens asserts canonical coverage ≥ a target
  and flags new unknowns in CI.
- **Repository/migration** tests for `unknown_skill_token` (integration, self-skipping like the
  others).

---

## 14. Risks & mitigations

| Risk (from the idea, expanded) | Mitigation |
|---|---|
| **Over-merging distinct skills** (`Java`/`JavaScript`, `Go`, `C#`) | `protected` tokens; `never_merge` regression tests; high similarity threshold; deterministic-only by default (semantic fallback opt-in, confidence-weighted) |
| **Language on non-tech words** (role titles, levels, "English") | Normalize **only** the skill/tech fields, never titles/levels/free text; treat human-language proficiency as its own concept, curated separately |
| **Map staleness** (grows over time) | On-read normalization (no stored staleness) by default; persisted projections carry `map_version` for invalidation |
| **Silent bad fuzzy matches** | Nothing auto-merges below threshold; every fuzzy/semantic map is logged with its score and is human-reviewed before baking |
| **Dependency bloat** | Runtime is stdlib + tiny map (+ optional rapidfuzz); embeddings/pgvector are an optional tooling extra |
| **PL/EN drift** | ESCO multilingual labels anchor PL↔EN to the same concept URI |

**Success metrics:** unknown-token rate (↓ over time), canonical coverage of the corpus (↑),
match-score deltas on a labelled sample, and a manual precision check on a sample of auto-merges
(target high precision; recall grows via curation).

---

## 15. Open decisions (need a call before Phase 1)

1. **Canonical id form** — human-readable slug (`javascript`) vs. ESCO URI. Recommend slug +
   optional ESCO URI in the map (readable diffs, taxonomy-anchored).
2. **Persist canonical at write time vs. normalize on read** — recommend **on-read** for the MVP
   (simplest, no staleness), add persisted projections only when needed.
3. **Embeddings provider for curation** — provider API (no heavy dep, tiny one-off cost) vs. local
   `sentence-transformers` (offline/private). Recommend provider API to start.
4. **Scoring re-calibration appetite** — how aggressively to down-weight un-evidenced self-claims
   (changes scores for existing users).

---

## Sources

- ESCO — download & multilingual classification: <https://esco.ec.europa.eu/en/use-esco/download>,
  dataset structure: <https://esco.ec.europa.eu/en/structure-esco-downloadable-datasets>
- Lightcast Open Skills: <https://lightcast.io/open-skills>, API: <https://docs.lightcast.dev/apis/skills>
- Stack Overflow tag synonyms: <https://stackoverflow.blog/2010/08/01/tag-folksonomy-and-tag-synonyms/>
- Skill/job entity linking with sentence-transformers + taxonomies (survey of approaches):
  <https://arxiv.org/pdf/2512.03195>, <https://arxiv.org/pdf/2509.04942>
- pgvector (vector similarity search for Postgres): <https://github.com/pgvector/pgvector>
- Sentence Transformers (multilingual models): <https://www.sbert.net/>
- SkillNER (note: stale since 2021): <https://github.com/AnasAito/SkillNER>; maintained alternative
  Nesta `ojd_daps_skills`: <https://github.com/nestauk/ojd_daps_skills>
- rapidfuzz: <https://github.com/rapidfuzz/RapidFuzz>
