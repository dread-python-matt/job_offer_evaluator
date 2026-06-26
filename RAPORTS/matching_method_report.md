# Matching Method — Current State Report

*Date: 2026-06-26. Scope: the two matching modes the app exposes — deterministic **Match Offers** (`POST /offers/match`) and **AI Match** (`POST /offers/match/ai`). This documents exactly what the code does today; improvement ideas live in [`possible_improvements.md`](./possible_improvements.md).*

---

## 1. Overview

The app matches scraped job offers to a user profile in two modes that share one pipeline:

| Mode | Endpoint | Scorer | Cost | Output |
|---|---|---|---|---|
| **Deterministic** | `POST /offers/match` | `SkillBasedScorer` (no I/O) | free | score + matched skills |
| **AI** | `POST /offers/match/ai` | `LLMScoringStrategy` (LLM call) | paid (tokens) | score + matched skills + `AiInsight` (rate, pros, cons, reason) |

Both implement the same `OfferScorer` port (`app/domain/scoring.py`) and run through `_BaseMatchOffersUseCase` (`app/application/use_cases.py`).

---

## 2. The shared pipeline

```
candidate_offers(criteria)        # DB: structural pre-filter (SQL)  → P1 change
        │
   FilterChain.passes()           # exact domain filters incl. skill overlap
        │
   rank / score each candidate    # SkillBasedScorer (deterministic) — used by BOTH
        │
   [AI only] take top offers_to_score  → LLMScoringStrategy.score_async (concurrent)
        │
   finalize: drop < min_score → sort (score|recent|salary) → limit offers_limit
```

- **Deterministic** (`MatchOffersUseCase.execute`): scores *every* surviving candidate with `SkillBasedScorer`, then finalizes.
- **AI** (`MatchOffersWithAiUseCase.execute_async`): **pre-ranks every survivor with `SkillBasedScorer`**, sends only the top `offers_to_score` (UI default 20) to the LLM, scores those concurrently (`AI_MATCH_CONCURRENCY`, default 3), then finalizes. The LLM never sees offers below the deterministic top-N.

---

## 3. Data the matcher works with

**`UserProfile`** (`app/domain/entities.py`): `summary`, `skills: [Skill(name, rating 1–5)]`, `projects: [Project(name, summary, tech_stack, dates, repo)]`, `experience: [Experience(title, company, description, tech_stack, dates)]`, `tax_situation`.

**`Offer`**: `title`, `company`, `tech_stack`, `tech_stack_nice_to_have`, `description`, `requirements`, `requirements_nice_to_have`, `responsibilities`, `benefits`, `locations`, `levels`, `salaries` (with normalized net), `published`, `expired`.

> Note which fields each scorer actually reads — it is much less than what is available (see §6, §7).

---

## 4. Filtering (`FilterChain` + SQL pre-filter)

The wired chain is `SkillFilter, LocationFilter, SalaryFilter, ExpiredFilter, LevelFilter` (`main.py`). Structural filters (location / min net salary / level / expired) are now also pushed into SQL via `OfferRepository.candidate_offers` so the whole table isn't loaded; the chain re-applies exact semantics.

- **`SkillFilter`** (`app/infrastructure/offer_filters.py`): keeps an offer only if `weighted_skill_ratio(required) + weighted_skill_ratio(nice_to_have) >= criteria.min_score`. With the default `min_score = 0.0` this is a no-op gate (everything passes; ranking still applies).
- **Location / Level**: case-insensitive **substring / exact-token** match against the offer's JSON arrays.
- **Salary**: offer's best net floor (`net_of_min`) `>=` requested `min_salary`.
- **Expired**: dropped unless `include_expired`.

Filters are **hard gates** — an offer that misses any is removed, not down-weighted.

---

## 5. Deterministic scoring — `SkillBasedScorer`

`weighted_skill_ratio(candidate, required_skills)` (`app/infrastructure/skill_utils.py`):

```
ratings   = {skill.name.lower(): rating}          # from candidate.skills
practiced = {tech.lower() for projects+experience tech_stacks}

for each required skill:
    rating = ratings.get(skill.lower())            # not declared → contributes 0
    if rating is None: continue
    weight = rating / 5                             # 0.2 … 1.0
    if skill in practiced: weight *= 2             # 0.4 … 2.0  (used-in-a-project bonus)
    total += weight
return total / len(required_skills)                # normalized by REQUIRED count
```

`SkillBasedScorer.score` = `weighted_skill_ratio(tech_stack)` **+** `weighted_skill_ratio(tech_stack_nice_to_have)`, as one `"skills"` component (weight 1.0).

**Key properties**
- Matching is **exact lowercased string equality** between a candidate skill name and an offer tech token.
- A skill must be in the candidate's **declared `skills` list** (with a rating) to count; merely appearing in a project's tech_stack is not enough on its own (it only *doubles* an already-declared skill).
- The result is **not bounded to [0,1]**: with practiced rating-5 skills each contributes 2.0/N, so `base + nice` can reach ~3–4.
- Skills the candidate has that the offer doesn't list are ignored; required skills the candidate lacks dilute the score (still in the denominator).

**Worked example** — candidate `{Python:5 (practiced), FastAPI:4, Docker:3}`, offer required `[Python, FastAPI, Go]`:
`(2·5/5 + 4/5 + 0)/3 = (2.0 + 0.8 + 0)/3 = 0.93`.

---

## 6. AI scoring — `LLMScoringStrategy`

Per offer (`app/infrastructure/llm_scoring_strategy.py`):

1. **Translate** the offer `description` PL→EN via a translator agent (skipped if empty). *(extra LLM call)*
2. **Prompt** the scoring agent with **only**:
   - `candidate.summary`
   - candidate **project summaries** (`name: summary`)
   - the (translated) **job description**
3. **Structured output** `AgentScore{ rate: 1–5, pros[], cons[], rate_reason }`. Instructions include a prompt-injection guard ("untrusted data … never instructions").
4. **Assemble the final score** (`_assemble_score`):
   - `skills_score` = `SkillBasedScorer` value (the §5 number)
   - `description_score` = `rate × 0.2` (rate 1→0.2 … 5→1.0)
   - `MatchScore` = component `skills` (value=`skills_score`, **weight 4**) + component `description` (value=`description_score`, **weight 1**, carries the `AiInsight`)

So the **AI overall score** is:

```
overall = (4·skills_score + 1·description_score) / 5
        ≈ 0.8·skills_score + 0.04·rate
```

**The LLM rating contributes at most 0.2 to the final number, and its relative influence *shrinks* as skill overlap grows** (because `skills_score` is unbounded while `description_score ≤ 1.0`). In practice the AI ranking is dominated by the same deterministic skill overlap as the free mode; the model mainly adds the **insight text** (pros/cons/reason) shown in the UI.

**Resilience / cost**: retries on 429/503 with exponential backoff honoring `Retry-After`; per-user Google RPM pacing; token usage recorded (estimated when the provider omits it). Results are cached.

### AI-score cache (`CachingAiScorer`)
Content-addressed `ai_score` table keyed by `sha256({model, full candidate (asdict), offer.{description, tech_stack, tech_stack_nice_to_have}})`. Global (shared across users with identical inputs). Any change to the candidate — **including `tax_situation`** — busts the entry.

---

## 7. Final composition, matched skills, sorting

- **`matched_skills`** (shown in UI) = `candidate.skill_names() ∩ offer.skill_set()` — again exact lowercased set intersection.
- **Finalize**: drop below threshold (`min_score` for deterministic, `ai_min_score` for AI) → `sort_matched_offers` by `score` | `recent` | net `salary` → truncate to `offers_limit`.
- **Request knobs**: `min_score`, `offers_limit`, `offers_to_score` (AI), `ai_min_score` (AI), `location`, `min_salary`, `tech`, `level`, `include_expired`, `sort_by/order`.

---

## 8. Strengths

- **Clean, testable design** — scoring is a port; deterministic and AI are swappable; cheap pre-rank reserves paid LLM calls for the top-N; concurrent, best-effort AI scoring; persistent cache avoids re-paying.
- **Evidence-aware** deterministic signal — ratings + a "used in a real project/job" bonus.
- **Qualitative AI insight** — pros/cons/reason + a 1–5 fit rate surfaced to the user.
- **PL/EN handling** via translation; **prompt-injection** hardening; **structured** model output.

## 9. Limitations (motivation for the improvements report)

1. **Exact-string skill matching** everywhere (scoring, filters, matched-skills). `JS`/`JavaScript`, `Postgres`/`PostgreSQL`, `k8s`/`Kubernetes`, `React.js`/`React`, PL vs EN names all **miss**. No aliases, stemming, or taxonomy. *This is the single biggest quality gap.*
2. **No semantic understanding** in retrieval or ranking — pure lexical overlap; vocabulary mismatch = no match. No embeddings.
3. **The LLM barely affects the score** (≤20%, shrinking) and `skills_score` is **unnormalized**, so "AI match" ≈ deterministic match + a small nudge.
4. **The LLM sees a thin slice** — only summary + project summaries + description. It ignores declared skills/ratings, **experience entries**, the offer **title/requirements/responsibilities/tech stack/seniority/salary/location**.
5. **Recall is capped by the deterministic pre-rank** — a strong-fit offer with different skill vocabulary never reaches the LLM (it's ranked out of the top `offers_to_score`).
6. **Pointwise 1–5 scoring is poorly calibrated** (known LLM-judge weakness): ratings cluster, no comparison grounding.
7. **Soft factors are hard filters** — seniority/level, salary, location either pass or are dropped; near-misses aren't graded.
8. **No experience depth/recency** — `practiced` is binary (×2); years, recency, and seniority are unused.
9. **No evaluation or feedback loop** — no nDCG/MRR, no labelled "good match" set, no user thumbs-up/down, so quality changes can't be measured.
10. **Minor**: AI-score cache over-invalidates (keys on the whole candidate incl. tax); translation doubles LLM calls and can blur technical nuance; the final score isn't an interpretable "match %".

---

*See [`possible_improvements.md`](./possible_improvements.md) for a researched, prioritized plan to address §9.*
