# Matching — Possible Improvements (researched)

*Date: 2026-06-26. Companion to [`matching_method_report.md`](./matching_method_report.md), which describes the current method and its limitations (§9). This report proposes a researched, prioritized plan to improve **match quality**, mapped onto the existing Clean/Hexagonal architecture (the `OfferScorer` port, `FilterChain`, `candidate_offers`) so changes stay low-churn.*

> **Go deeper:** [`matching_deep_research.md`](./matching_deep_research.md) extends this with concrete models/benchmarks and an architecture tailored to the **Polish IT market and Python-developer roles** (role disambiguation, seniority, must-have vs nice-to-have, hybrid pgvector retrieval, cross-encoder + LLM reranking, evaluation, unbiased LTR).*

## The shape modern systems converge on

Across 2026 production write-ups and research, job/candidate matching has settled on a **funnel**:

```
normalize (skills/titles) → retrieve (hybrid: lexical + dense embeddings)
        → rerank (cross-encoder) → judge (LLM, only the final shortlist)
        → evaluate (offline metrics + online feedback)
```

> "Production wins come from **hybrid retrieval (dense + sparse), reranking, and disciplined evaluation** — not just picking a model." ([OpenSearch](https://opensearch.org/blog/building-effective-hybrid-search-in-opensearch-techniques-and-best-practices/), [Embeddings in Practice](https://medium.com/@adnanmasood/embeddings-in-practice-a-research-implementation-guide-9dbf20961590))

Our current pipeline is essentially **lexical-overlap retrieval + a thin, down-weighted LLM pass, with no normalization and no evaluation**. The improvements below move it toward the funnel, in priority order.

---

## 1. Normalize skills (aliases + taxonomy) — *highest ROI, lowest cost*

**Problem (report §9.1):** exact-string matching misses `JS`/`JavaScript`, `k8s`/`Kubernetes`, `Postgres`/`PostgreSQL`, PL vs EN, etc. Every downstream number inherits this error.

**Approach:**
- Short term: a **canonicalization map** (alias → canonical) + Unicode/case folding + abbreviation expansion, applied wherever skills are compared (`skill_utils.py`, `offer_filters.py`, `matched_skills`). Cheap, deterministic, immediately lifts both modes.
- Medium term: map skills/titles to a **standard taxonomy — ESCO (EU market, multilingual) or O\*NET** — so synonyms and PL/EN variants collapse to one concept. Research uses Sentence-Transformer embeddings (e.g. `paraphrase-multilingual-mpnet-base-v2`) to rank candidate skills by cosine similarity against the taxonomy, with confidence scores. ([Enhancing Job Matching with ESCO/EQF](https://arxiv.org/html/2512.03195v1), [Contrastive bi-encoders for ESCO skill extraction](https://arxiv.org/html/2601.09119), [CareerBERT](https://arxiv.org/pdf/2503.02056), [JobsPikr: normalising titles/skills](https://www.jobspikr.com/blog/normalising-data-job-titles-skills-locations/))

**Fits:** a new `SkillNormalizer` port (domain) + an adapter (static map now, ESCO/embedding-backed later); inject into `weighted_skill_ratio` and the filters. No use-case changes.

---

## 2. Semantic retrieval (embeddings) + hybrid — *fixes recall*

**Problem (§9.2, §9.5):** retrieval/pre-rank is pure lexical overlap, so a strong-fit offer with different vocabulary is never surfaced and never reaches the LLM.

**Approach:** embed the candidate (summary + skills + experience) and each offer (title + description + tech) into a shared vector space; retrieve by cosine similarity. Combine with the existing keyword signal — **hybrid (BM25/lexical + dense)** is the 2026 standard because lexical nails exact tech tokens while dense captures meaning/intent. Fuse with RRF or a weighted blend. ([HF: semantic job matching with RAG/embeddings](https://huggingface.co/blog/MCP-1st-Birthday/building-jobly-semantic-job-matching-with-rag-and), [AI semantic-similarity job matching](https://www.sciencedirect.com/science/article/pii/S0020025525008643), [OpenSearch hybrid](https://opensearch.org/blog/building-effective-hybrid-search-in-opensearch-techniques-and-best-practices/))

**Fits:** add an `EmbeddingProvider` port + a vector index. Postgres-native option: **`pgvector`** on the app side (offers are read-only/scraper-owned, so store embeddings in an app-owned `offer_embedding` table keyed by offer id, refreshed by a small job). Replace/augment the deterministic pre-rank in `MatchOffersWithAiUseCase` so the LLM shortlist is drawn from semantic+lexical candidates, not lexical-only.

---

## 3. Rerank the shortlist with a cross-encoder — *cheap precision before the LLM*

**Problem (§9.3, §9.5):** the only re-ranking is the weak deterministic skill sum; the LLM is expensive and barely weighted.

**Approach:** insert a **cross-encoder reranker** between retrieval and the LLM. It jointly attends over each (candidate, offer) pair and is far more precise than bi-encoder/lexical similarity — typical **+5 to +15 nDCG@10** on standard benchmarks, at a fraction of LLM cost/latency. Take top ~100 from retrieval → cross-encoder → top ~10–20 → (optionally) LLM. Models: BGE-reranker-v2-m3, Cohere Rerank 3, Jina Reranker v2, mxbai-rerank. ([Reranking & cross-encoders guide 2026](https://localaimaster.com/blog/reranking-cross-encoders-guide), [Top rerankers for RAG](https://www.analyticsvidhya.com/blog/2025/06/top-rerankers-for-rag/))

**Fits:** a `Reranker`/`OfferScorer` adapter slotted as the pre-LLM ranker. Often lifts quality enough that the LLM can be reserved for the final few (or dropped for cost-sensitive users).

---

## 4. Fix the score composition — *make the score mean something*

**Problem (§9.3, §9.10):** `skills_score` is unbounded so the LLM contributes ≤20% (shrinking), and the final number isn't an interpretable "match %".

**Approach:**
- **Normalize** each signal to [0,1] before weighting (cap/så scale the skill ratio; keep the LLM rate as `rate/5`).
- **Re-balance weights** deliberately (e.g. skills 0.4 / semantic 0.3 / LLM 0.3) — or, cleaner, make the **LLM (or cross-encoder) the ranker** and use skills as one input feature, rather than a fixed 4:1 blend that drowns it.
- Present a calibrated **match %** with the component breakdown (we already carry named `ScoreComponent`s — surface them).

**Fits:** purely in `_assemble_score` / `MatchScore` weighting; no architecture change.

---

## 5. Give the LLM the full signal + a rubric — *more accurate judgments*

**Problem (§9.4):** the prompt sees only summary + project summaries + description. It ignores declared skills/ratings, **experience**, and the offer's **title / requirements / responsibilities / tech stack / seniority / salary / location**.

**Approach:** expand the prompt to the full structured candidate and offer, and score against an explicit **rubric** (skills coverage, seniority fit, domain/experience relevance, must-have gaps) returning **per-criterion sub-scores** with justifications. Rubric-based, structured evaluation measurably improves consistency and agreement vs a single holistic 1–5. ([Rubric-based evals & LLM-as-judge](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80), [Ultimate guide to LLM-as-a-judge 2026](https://www.mlaidigital.com/blogs/the-ultimate-guide-to-llm-as-a-judge-in-2026))

**Fits:** `LLMScoringStrategy._build_prompt` + a richer `AgentScore` (sub-scores). Keep the prompt-injection guard.

---

## 6. Better LLM scoring protocol — *calibration*

**Problem (§9.6):** isolated pointwise 1–5 ratings are noisy and cluster.

**Approach:** prefer **comparative** judging where it matters — **listwise/pairwise reranking** of the shortlist grounds each judgment against the others and agrees better with humans than pointwise scores (mind position bias; shuffle/aggregate). Add light **calibration** (fixed rubric anchors, or normalize per-request). For a single match list, an LLM **listwise rerank of the top-K** is a strong, well-supported pattern. ([Pointwise vs pairwise vs listwise survey](https://arxiv.org/html/2412.05579v2), [RankLLM](https://arxiv.org/pdf/2505.19284), [FairJudge: debiased LLM judge](https://arxiv.org/pdf/2602.06625))

**Fits:** an alternative `OfferScorer`/reranker that scores the shortlist as a set instead of per-offer.

---

## 7. Turn hard filters into graded features — *don't drop near-misses*

**Problem (§9.7, §9.8):** seniority/level, salary, location are pass/fail; a role 5% under target salary or one level off vanishes.

**Approach:** keep hard filters only for true dealbreakers (e.g. wrong country if remote not allowed); convert the rest into **graded fit features** folded into the score (salary proximity, seniority distance, location/remote compatibility). Weight required vs nice-to-have skills differently. This is standard in learning-to-rank / multi-criteria matching.

**Fits:** new `OfferFilter`→`feature` components feeding `MatchScore`; the salary/level data is already loaded.

---

## 8. Evaluation harness + feedback loop — *so we can tell if any of this helps*

**Problem (§9.9):** no metrics, no labels, no feedback — quality changes are flying blind.

**Approach:**
- **Offline:** a small **golden set** of (profile → relevant offers) and report **Recall@K / MRR / nDCG@10** in CI; this is the agreed yardstick for these systems. ([HF Jobly](https://huggingface.co/blog/MCP-1st-Birthday/building-jobly-semantic-job-matching-with-rag-and), [explainable job recsys](https://arxiv.org/html/2605.27656v1))
- **Online:** capture user **thumbs up/down / apply / dismiss** on matches → the label source that powers reranker fine-tuning and regression tracking.
- **LLM-as-judge for *evaluation*** (offline scoring of ranking quality), distinct from using it in the live path — with the calibration caveats from §6.

**Fits:** a new `app/evaluation/` module + a feedback table (per-user, per-offer signal). Cheap to start; compounding value.

---

## 9. Cost / latency / explainability (cross-cutting)

- Embeddings + cross-encoder make **recall and precision cheap**, letting the **expensive LLM shrink to the final shortlist** (or become opt-in) — directly easing the Gemini free-tier rate-limit pressure noted elsewhere.
- Cache embeddings and reranks; tighten the AI-score cache key (drop `tax_situation`, report §9.10).
- Reconsider always translating: multilingual embeddings/models can score PL directly, removing the extra translation call.
- We already produce `pros/cons/reason` + named components — surface them as the **explainability** layer modern candidates expect. ([explainable job recsys](https://arxiv.org/html/2605.27656v1), [JobMatchAI: KG + semantic + XAI](https://arxiv.org/pdf/2603.14558))

---

## Prioritized roadmap

| # | Improvement | Impact | Effort | Notes |
|---|---|---|---|---|
| 1 | **Skill normalization** (alias map → ESCO/embeddings) | ★★★ | ◆ low | Quick win; lifts *both* modes immediately; new `SkillNormalizer` port |
| 4 | **Normalize + rebalance score composition** | ★★ | ◆ low | `_assemble_score` only; makes the score interpretable |
| 8 | **Evaluation harness + feedback capture** | ★★★ | ◆◆ med | Prerequisite to *prove* everything else; start with a golden set + nDCG |
| 5 | **Full-signal + rubric LLM prompt** | ★★ | ◆ low–med | Big accuracy lift for the AI mode at ~same cost |
| 2 | **Semantic + hybrid retrieval** (pgvector) | ★★★ | ◆◆◆ high | Fixes recall ceiling; `EmbeddingProvider` port + `offer_embedding` table |
| 3 | **Cross-encoder reranker** | ★★★ | ◆◆ med | Precision before the LLM; +5–15 nDCG typical; reserve/replace LLM |
| 6 | **Listwise/calibrated LLM judging** | ★★ | ◆◆ med | Better calibration than pointwise 1–5 |
| 7 | **Graded soft factors** (salary/seniority/location) | ★★ | ◆◆ med | Stop dropping near-misses |

**Suggested sequence:** ship **#1 + #4** (quick wins, both modes) → stand up **#8** (so the rest is measurable) → **#5** (cheap AI-mode lift) → then the bigger retrieval/reranking bets **#2 → #3 → #6/#7**, each validated against the #8 harness.

Every step slots behind existing ports (`OfferScorer`, `FilterChain`, `OfferRepository`) or adds one new port (`SkillNormalizer`, `EmbeddingProvider`, `Reranker`), so the domain/use-case layer stays stable and changes are adapter-local and TDD-able.

---

## Sources

- [Building Jobly: semantic job matching with RAG + embeddings (Hugging Face)](https://huggingface.co/blog/MCP-1st-Birthday/building-jobly-semantic-job-matching-with-rag-and)
- [Intelligent job recommendation: semantic retrieval + explainable AI (arXiv)](https://arxiv.org/html/2605.27656v1)
- [AI-driven semantic-similarity job matching framework (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0020025525008643)
- [JobMatchAI: knowledge graphs + semantic search + XAI (arXiv)](https://arxiv.org/pdf/2603.14558)
- [CareerBERT: matching resumes to ESCO jobs (arXiv)](https://arxiv.org/pdf/2503.02056)
- [Enhancing job matching with ESCO & EQF taxonomies (arXiv)](https://arxiv.org/html/2512.03195v1)
- [Contrastive bi-encoders for ESCO skill extraction (arXiv)](https://arxiv.org/html/2601.09119)
- [Normalising job titles, skills & locations (JobsPikr)](https://www.jobspikr.com/blog/normalising-data-job-titles-skills-locations/)
- [Building effective hybrid search (OpenSearch)](https://opensearch.org/blog/building-effective-hybrid-search-in-opensearch-techniques-and-best-practices/)
- [Embeddings in practice: research & implementation guide (Medium)](https://medium.com/@adnanmasood/embeddings-in-practice-a-research-implementation-guide-9dbf20961590)
- [Reranking & cross-encoders for RAG: BGE, Cohere, Jina (2026)](https://localaimaster.com/blog/reranking-cross-encoders-guide)
- [Top rerankers for RAG (Analytics Vidhya)](https://www.analyticsvidhya.com/blog/2025/06/top-rerankers-for-rag/)
- [RankLLM: reranking with LLMs (arXiv)](https://arxiv.org/pdf/2505.19284)
- [LLMs-as-Judges: comprehensive survey (arXiv)](https://arxiv.org/html/2412.05579v2)
- [Rubric-based evals & LLM-as-a-judge (Medium)](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80)
- [The ultimate guide to LLM-as-a-Judge in 2026 (MLAI Digital)](https://www.mlaidigital.com/blogs/the-ultimate-guide-to-llm-as-a-judge-in-2026)
- [FairJudge: adaptive, debiased, consistent LLM-as-a-judge (arXiv)](https://arxiv.org/pdf/2602.06625)
