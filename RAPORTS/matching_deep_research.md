# Matching — Deep Research (IT market / Python developers)

*Date: 2026-06-26. Deepens [`possible_improvements.md`](./possible_improvements.md) with concrete models, benchmarks, and an architecture tailored to **this app's domain: the Polish IT job market, and Python-developer roles in particular**. Read [`matching_method_report.md`](./matching_method_report.md) first for what exists today.*

---

## 0. Why the IT/Python focus changes the problem

Generic "resume ↔ job" matching advice under-serves this app. Three domain facts dominate:

1. **"Python" is not a role.** The same token maps to wildly different jobs — **backend** (Django/FastAPI/Flask + REST + SQL/ORM), **data engineering** (Spark/Airflow/dbt/Kafka), **ML/DS** (PyTorch/pandas/scikit-learn), **DevOps/automation**, **QA/test-automation**. The current scorer (exact lowercased overlap of `tech_stack`, report §5) will rank a *data-engineer* offer highly for a *backend* candidate purely on the shared "python", "sql", "docker" tokens. **Role disambiguation is the #1 IT-specific failure mode** and exact-string overlap is structurally blind to it. ([Backend vs data engineer overlap](https://blog.boot.dev/backend/backend-engineer-vs-data-engineer/), [Python developer skills](https://distantjob.com/blog/python-developer-skills/))

2. **Exact tech tokens carry real meaning, but so does adjacency.** `AWS`≠`Azure`, `Postgres`≠`MySQL`, `React`≠`React Native` — so you cannot throw away lexical precision. Yet a strong **Django** dev genuinely fits a **FastAPI/Flask** role (framework adjacency), and a backend+SQL dev partially fits data engineering (transferable skills). Exact matching gives **zero** credit for FastAPI when the candidate listed Django. You need **both** lexical precision *and* semantic adjacency → **hybrid retrieval**. ([transferable backend→data eng](https://medium.com/@1segaladi/transitioning-from-backend-developer-to-data-engineering-transferable-skills-aa3a16a71a4a))

3. **Polish IT offers are bilingual.** Prose is Polish; tech terms are English; boards like **JustJoin.it / NoFluffJobs** even separate **required vs nice-to-have** stacks and publish salary + seniority. Our `Offer` already has `tech_stack` vs `tech_stack_nice_to_have` and `levels` — signal the current scorer barely uses. Multilingual embeddings score Polish directly (the PL→EN translation step, report §6, becomes optional). ([Polish IT boards](https://justjoin.it/), [IT talent in Poland 2025](https://correctcontext.com/it-talent-in-poland-the-complete-2025-guide-for-tech-companies/))

Everything below is shaped by these three facts.

---

## 1. Skill normalization for tech — Lightcast over ESCO for the stack

The report's §1 recommendation stands, but for **IT specifically the taxonomy choice matters**:

- **Lightcast Open Skills** — ~**32,000 skills**, built *from hundreds of millions of job postings*, refreshed biweekly, with an explicit **"software skills" category** and **aliases/acronyms/abbreviations/historic names** per skill. This is far richer on concrete tooling (frameworks, libraries, versions) than ESCO and is the better fit for normalizing a *tech stack*. ([Lightcast Open Skills](https://lightcast.io/open-skills), [taxonomy KB](https://kb.lightcast.io/en/articles/7216059-lightcast-skills-taxonomy))
- **ESCO** — better for **occupation/role** linking and EU-multilingual coverage (PL labels), useful for the *role-level* signal (see §3). ([ESCO/EQF job matching](https://arxiv.org/html/2512.03195v1))
- Practical tech layer: a curated **alias map** for the long tail this app actually sees (`js→javascript`, `k8s→kubernetes`, `postgres→postgresql`, `py→python`, `tf→terraform|tensorflow` (disambiguate!), `gcp→google cloud`), plus Unicode/case folding and abbreviation expansion — the standard preprocessing before embedding-based candidate ranking. ([normalising titles/skills](https://www.jobspikr.com/blog/normalising-data-job-titles-skills-locations/))

Modern extraction is **LLM-supervised**: GPT-4o-mini labels skill spans (explicit *and implicit*) → fine-tune a small multilingual encoder (`paraphrase-multilingual-mpnet-base-v2`) to map spans to the taxonomy. This is directly applicable to enriching scraped offers and free-text profile fields. ([LLM-supervised multilingual skill extraction](https://link.springer.com/chapter/10.1007/978-3-031-97144-0_9), [Skill-LLM](https://arxiv.org/html/2410.12052v1), [ESCO skill extraction, 13,896 skills](https://aclanthology.org/2025.genaik-1.15.pdf))

> **Concrete:** normalize every candidate skill and every offer `tech_stack`/`tech_stack_nice_to_have` token to a Lightcast canonical id at ingest; keep the raw string for display. Exact-overlap quality jumps immediately, and it's the substrate every later stage relies on.

---

## 2. Retrieval — hybrid (dense + lexical), Postgres-native

**Why hybrid, emphatically, for IT:** pure dense blurs hard tech tokens (`AWS`/`Azure`); pure lexical misses role/adjacency. Hybrid lets each cover the other's blind spot, and the measured lift is large — one Postgres write-up went **~62% → ~84% retrieval precision** adding full-text + RRF over pure vector. ([OpenSearch hybrid](https://opensearch.org/blog/building-effective-hybrid-search-in-opensearch-techniques-and-best-practices/), [pgvector + FTS + RRF](https://dev.to/lpossamai/building-hybrid-search-for-rag-combining-pgvector-and-full-text-search-with-reciprocal-rank-fusion-6nk))

**Embedding model (self-host, multilingual, free):**

| Model | Why for us | Note |
|---|---|---|
| **BGE-M3** | 100+ langs incl. Polish; **emits dense + sparse + ColBERT from one model** → hybrid without running two models; strong retrieval | Best default for this app |
| multilingual-e5-large | proven multilingual retrieval baseline | simpler, smaller |
| Qwen3-Embedding (0.6/4/8B) | top MTEB multilingual (8B ≈ 70.6) | heavier; overkill to start |
| jina-embeddings-v3 | long-doc "late chunking" (long offer descriptions) | good for verbose offers |

([BGE-M3 / open embeddings guide](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models), [mE5 report](https://arxiv.org/pdf/2402.05672), [MTEB 2026](https://www.codesota.com/benchmarks/mteb))

**Architecture given our constraints** (the `offers` table is **scraper-owned, read-only**, app is multi-tenant):
- App-owned **`offer_embedding`** table (`offer_id`, `vector`, `model_version`, `computed_at`), populated by a small refresh job — never touch the scraper's schema (consistent with the existing read-only `OfferRepository`).
- **pgvector + HNSW** for dense (HNSW = better recall, no `nprobe` tuning); Postgres **`tsvector`/BM25** (or `pg_textsearch`, GA mid-2026) for lexical; fuse with **Reciprocal Rank Fusion**. All in the Postgres you already run — no new infra. ([pgvector HNSW + RRF](https://danubedata.ro/blog/pgvector-rag-managed-postgres-2026), [Postgres BM25](https://www.pedroalonso.net/blog/postgres-bm25-search/), [ParadeDB hybrid](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual))
- This **replaces the lexical-only pre-rank** in `MatchOffersWithAiUseCase`, fixing the recall ceiling (report §9.5) so the LLM shortlist is drawn from *semantically* relevant offers.

**Domain SOTA worth knowing (person-job fit):** **ConFit** uses contrastive dense retrieval (E5 encoders) for resume↔job and beats prior PJF baselines; **ConFit v2** adds *runner-up hard-negative mining* + LLM job-posting augmentation; **ConFit v3** adds LLM sliding-window re-ranking for controllability/explainability. **Two-tower** (separate candidate/offer encoders + ANN) is the standard scalable architecture. This is the exact recipe for our domain. ([ConFit v2](https://arxiv.org/pdf/2502.12361), [ConFit v3](https://arxiv.org/html/2605.09760v1), [two-tower deep dive](https://www.shaped.ai/blog/the-two-tower-model-for-recommendation-systems-a-deep-dive))

---

## 3. The IT-specific scoring features the model is missing

Beyond retrieval, the *score* should encode what actually decides a software-role fit. These become graded features feeding `MatchScore` (not hard filters, report §9.7):

- **Role/specialization fit.** Classify both sides into {backend, data-eng, ML/DS, frontend, fullstack, DevOps, QA, …} (LLM or a small classifier over title+stack) and penalize cross-role mismatches. Stops the "shared Python token" over-match (§0.1).
- **Seniority fit.** Use the offer `levels` + candidate experience **years/recency** as a *distance*, not a gate: senior↔junior mismatch heavily down-weighted, ±1 level lightly. Seniority is one of the largest IT-fit factors. ([senior vs mid Python](https://distantjob.com/blog/python-developer-skills/))
- **Must-have vs nice-to-have asymmetry.** We *already store* `tech_stack` vs `tech_stack_nice_to_have`. A missing **must-have** should heavily penalize; a missing nice-to-have shouldn't. Today they're summed ~equally (report §5).
- **Adjacency credit.** Django↔FastAPI↔Flask, pandas↔Polars, Postgres↔MySQL, AWS↔GCP — partial credit via taxonomy siblings / embedding similarity instead of 0/1. Captures transferable skills.
- **Recency/depth.** Years with a skill and how recent (a 2015 Django stint ≠ current). The current `practiced` flag is binary ×2.
- **Salary & location as graded fit**, not just filters (proximity to target; remote/on-site/hybrid compatibility) — Polish boards expose salary + remote explicitly.

---

## 4. LLM stage — reranker, not a 20%-weighted afterthought

Report §9.3: today the LLM is ≤20% of the score and shrinking. Two better roles:

- **Cross-encoder reranker first** (cheap, big lift): take top ~100 from hybrid retrieval → cross-encoder → top ~10–20. Typical **+5 to +15 nDCG@10**, **50–100 ms** self-hosted on GPU. Multilingual picks: **bge-reranker-v2-m3**, **jina-reranker-v2-base-multilingual** (100+ langs, ~6× throughput vs v1), **Cohere Rerank 3.5** (API, ~600 ms, 100+ langs), **mxbai-rerank-v2**. For European langs all major rerankers are fine; bge/jina are the strong self-host options. ([reranker guide 2026](https://localaimaster.com/blog/reranking-cross-encoders-guide), [jina-reranker-v2 multilingual](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual), [reranker benchmark](https://aimultiple.com/rerankers))
- **LLM listwise rerank of the shortlist** (when used): **RankGPT-style** listwise prompting beats pointwise 1–5 for calibration, but autoregressive LLMs show **position bias** (different order → different ranking). Mitigate with **permutation self-consistency** (shuffle ~20×, aggregate), **sliding windows**, or **FIRST** (first-token-logit decoding, faster). Best long-term: **distill** a big LLM's permutations into a small specialized reranker (RankGPT distillation; **LANTERN** distills LLM job-person fit + explanations into an efficient model). ([RankGPT/permutation distillation context](https://arxiv.org/html/2604.27599v1), [FIRST](https://arxiv.org/html/2406.15657v1), [LANTERN](https://arxiv.org/pdf/2510.05490), [LLM reranker empirical analysis](https://aclanthology.org/2025.findings-emnlp.305.pdf))

For this app's economics (per-user keys, **Gemini free-tier ~10 RPM**), the win is: **embeddings + cross-encoder do the heavy lifting cheaply**, and the LLM is reserved for **listwise reranking + explanations on the final ~10** — or made opt-in. This also relieves the rate-limit pressure noted elsewhere in the repo.

And feed the LLM the **full signal + a rubric** (report §9.4/§5): candidate skills+ratings, **experience**, seniority, and the offer's title/requirements/responsibilities/stack/seniority/salary — scored per-criterion (skills coverage, must-have gaps, seniority fit, domain relevance) with justifications. Rubric + structured output measurably beats a holistic 1–5. ([rubric-based LLM-judge](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80))

---

## 5. Evaluation — the part that makes all of the above safe to ship

You cannot improve what you can't measure (report §9.9). For an IT/Python corpus:

- **Build a golden set**: ~30–50 representative Python profiles (backend/data/ML/junior/senior) × graded-relevant offers. Seed labels with an **LLM relevance judge** then spot-check — **UMBRELA**-style LLM judgments correlate **highly with human labels at the run level** for nDCG@20/100 & Recall@100 (TREC 2024 RAG track), so they're good enough to *rank competing configs* cheaply (weaker per-topic — keep humans for the hard cases). ([UMBRELA large-scale study](https://arxiv.org/html/2411.08275v1), [TRUE reproducible LLM judgments](https://arxiv.org/html/2509.25602v2))
- **Metrics**: nDCG@10, MRR, Recall@K offline; gate changes in CI.
- **Online**: capture **apply / save / dismiss / thumbs** per (user, offer) — the label source for everything below.
- Watch **role-confusion** explicitly (e.g., % of data-eng offers shown to backend candidates) as a domain KPI.

## 6. Closing the loop — learn the ranker from feedback

Once feedback exists, train a **learning-to-rank** model (e.g., LambdaMART / a fine-tuned reranker) on it — but implicit clicks/applies suffer **position bias** (top items get more interaction regardless of true fit). Use **unbiased LTR** (IPW / **Unbiased LambdaMART** / doubly-robust) so the model learns fit, not screen position. This is how the system gets *better than the LLM* over time, cheaply, on *our* users' behavior. ([Unbiased LambdaMART](https://dl.acm.org/doi/10.1145/3308558.3313447), [Unbiased LTR advances & applications](https://dl.acm.org/doi/10.1145/3616855.3636451))

## 7. Calibration — present an honest "match %"

Map the final ranker score to a calibrated 0–100% (isotonic/Platt against the golden-set/feedback labels) so "87% match" actually means something, and surface the component breakdown + the LLM's pros/cons as the **explainability** layer IT candidates expect. ([explainable job recsys](https://arxiv.org/html/2605.27656v1))

---

## 8. Target pipeline (for this app)

```
ingest:  scraped offer ──► normalize skills (Lightcast) ──► embed (BGE-M3) ──► offer_embedding (pgvector)
                                              └─► role + seniority tags

query:   profile ──► normalize + embed
           │
        HYBRID RETRIEVE  (pgvector HNSW dense  ⊕  tsvector/BM25 lexical, RRF)        ~ top 100
           │
        CROSS-ENCODER RERANK  (bge/jina-reranker-v2-m3)                              ~ top 10–20
           │
        FEATURE SCORE  (role fit · seniority distance · must-have gaps · adjacency · salary/location)
           │
        [optional] LLM LISTWISE RERANK + rubric explanation  (final ~10, position-bias-mitigated)
           │
        CALIBRATE → match %   ──►   feedback (apply/dismiss) ──► Unbiased LTR retrains the ranker
                                              └──────────────► offline eval (nDCG/MRR, UMBRELA golden set)
```

Every stage is an adapter behind a port — minimal churn to the domain/use-case layer:

| Stage | New port / change | Notes |
|---|---|---|
| Skill normalization | `SkillNormalizer` (domain) | static alias map → Lightcast/ESCO adapter |
| Embeddings + hybrid | `EmbeddingProvider` + `offer_embedding` table | pgvector; app-owned (offers stay read-only) |
| Cross-encoder | `Reranker` adapter (an `OfferScorer`) | self-host bge/jina or Cohere API |
| Feature scoring | new `ScoreComponent`s | role/seniority/must-have/adjacency/salary |
| LLM rerank + rubric | extend `LLMScoringStrategy` | listwise; full signal; reserve for top-K |
| Evaluation | `app/evaluation/` + golden set | nDCG/MRR; LLM-judge labels |
| Feedback / LTR | feedback table + trainer | unbiased LTR on apply/dismiss |

---

## 9. Prioritized roadmap (IT/Python-tuned)

| # | Step | Impact | Effort | IT/Python rationale |
|---|---|---|---|---|
| 1 | **Skill normalization** (alias map → Lightcast) | ★★★ | ◆ | Kills `JS/JavaScript`, `k8s/Kubernetes`, PL/EN misses; substrate for all else |
| 2 | **Must-have vs nice-to-have asymmetry + normalize/rebalance score** | ★★★ | ◆ | We already store both stacks; cheap, big precision win |
| 3 | **Evaluation harness + feedback capture** (golden set, nDCG, thumbs) | ★★★ | ◆◆ | Proves everything; track role-confusion KPI |
| 4 | **Role + seniority features** | ★★★ | ◆◆ | Fixes the "Python ≠ role" over-match — the #1 domain bug |
| 5 | **Full-signal + rubric LLM prompt; drop forced translation** | ★★ | ◆–◆◆ | Big AI-mode lift; multilingual model reads PL directly |
| 6 | **Hybrid retrieval (BGE-M3 + pgvector + tsvector/RRF)** | ★★★ | ◆◆◆ | Recall ceiling + adjacency (Django→FastAPI) |
| 7 | **Cross-encoder reranker** | ★★★ | ◆◆ | +5–15 nDCG before/instead of the costly LLM |
| 8 | **LLM listwise rerank (calibrated) + match %** | ★★ | ◆◆ | Calibrated ranking + explainability |
| 9 | **Unbiased LTR on feedback** | ★★★ | ◆◆◆ | Self-improving on our users' behavior |

**Sequence:** quick wins **1→2** (both modes, days) → **3** (so the rest is measurable) → **4** (the domain-defining fix) → **5** (cheap AI lift) → bigger retrieval/rerank bets **6→7→8** → long-game **9**. Each validated against the #3 harness.

---

## Sources

**Embeddings / hybrid retrieval**
- [Open-source embedding models guide — BGE-M3 (BentoML)](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models) · [Multilingual E5 report](https://arxiv.org/pdf/2402.05672) · [MTEB 2026 leaderboard](https://www.codesota.com/benchmarks/mteb)
- [pgvector + FTS + RRF (DEV)](https://dev.to/lpossamai/building-hybrid-search-for-rag-combining-pgvector-and-full-text-search-with-reciprocal-rank-fusion-6nk) · [pgvector HNSW on managed Postgres](https://danubedata.ro/blog/pgvector-rag-managed-postgres-2026) · [Postgres BM25](https://www.pedroalonso.net/blog/postgres-bm25-search/) · [ParadeDB hybrid manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual) · [OpenSearch hybrid best practices](https://opensearch.org/blog/building-effective-hybrid-search-in-opensearch-techniques-and-best-practices/)

**Person-job fit / domain SOTA**
- [ConFit v2 (arXiv)](https://arxiv.org/pdf/2502.12361) · [ConFit v3 — LLM re-ranking (arXiv)](https://arxiv.org/html/2605.09760v1) · [Two-tower deep dive (Shaped)](https://www.shaped.ai/blog/the-two-tower-model-for-recommendation-systems-a-deep-dive) · [LANTERN — distilling LLM job-person fit (arXiv)](https://arxiv.org/pdf/2510.05490) · [Generative job recommendations (arXiv)](https://arxiv.org/pdf/2307.02157)

**Skill taxonomy / extraction (IT)**
- [Lightcast Open Skills](https://lightcast.io/open-skills) · [Lightcast taxonomy KB](https://kb.lightcast.io/en/articles/7216059-lightcast-skills-taxonomy) · [LLM-supervised multilingual skill extraction (Springer)](https://link.springer.com/chapter/10.1007/978-3-031-97144-0_9) · [Skill-LLM (arXiv)](https://arxiv.org/html/2410.12052v1) · [Enhancing job matching with ESCO/EQF (arXiv)](https://arxiv.org/html/2512.03195v1)

**Rerankers (cross-encoder + LLM)**
- [Reranking & cross-encoders 2026 (Local AI Master)](https://localaimaster.com/blog/reranking-cross-encoders-guide) · [jina-reranker-v2 multilingual (HF)](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual) · [Reranker benchmark (AIMultiple)](https://aimultiple.com/rerankers) · [FIRST listwise (arXiv)](https://arxiv.org/html/2406.15657v1) · [Position-invariant listwise reranking (arXiv)](https://arxiv.org/html/2604.27599v1) · [LLM rerankers empirical analysis (EMNLP'25)](https://aclanthology.org/2025.findings-emnlp.305.pdf)

**Evaluation / learning-to-rank**
- [UMBRELA: LLM relevance assessments at scale (arXiv)](https://arxiv.org/html/2411.08275v1) · [TRUE: reproducible LLM relevance judgments (arXiv)](https://arxiv.org/html/2509.25602v2) · [Unbiased LambdaMART (WWW)](https://dl.acm.org/doi/10.1145/3308558.3313447) · [Unbiased LTR: advances & applications (WSDM)](https://dl.acm.org/doi/10.1145/3616855.3636451)

**IT / Polish market context**
- [Backend vs data engineer (Boot.dev)](https://blog.boot.dev/backend/backend-engineer-vs-data-engineer/) · [Python developer skills (DistantJob)](https://distantjob.com/blog/python-developer-skills/) · [Backend→data-eng transferable skills (Medium)](https://medium.com/@1segaladi/transitioning-from-backend-developer-to-data-engineering-transferable-skills-aa3a16a71a4a) · [JustJoin.it](https://justjoin.it/) · [IT talent in Poland 2025](https://correctcontext.com/it-talent-in-poland-the-complete-2025-guide-for-tech-companies/)
