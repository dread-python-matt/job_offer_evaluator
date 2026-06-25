# Polish Net‑from‑Gross (netto z brutto) — Expert Reference (2026, IT focus)

Reference for calculating **net (take‑home) pay from gross** in Poland for the three IT
contract types — **umowa o pracę** (permanent), **umowa zlecenie** (contract/mandate), and
**B2B** (JDG / self‑employment). Figures are **2026** and were verified against ZUS and Polish
accounting sources (see [Sources](#sources)); they match the constants in
`app/domain/salary_calculator.py`.

> Scope: the **employee/contractor net** perspective (what lands in the pocket). Employer‑side
> costs (the "total cost of employment") are noted only where they matter for B2B‑vs‑UoP
> comparison.

---

## 0. The mental model

Net pay is gross minus **three independent stacks**, applied in order and on different bases:

1. **ZUS społeczne** (social insurance) — pension + disability + sickness. Comes off first.
2. **Składka zdrowotna** (health, ~9%) — base and deductibility depend on contract/tax form.
3. **PIT** (income tax) — computed on a base *already reduced* by ZUS społeczne and costs (KUP).

Plus contract‑specific **KUP** (tax‑deductible costs) and **reliefs** that can zero a stack.
The contract types differ mostly in: (a) who pays ZUS and how much, (b) how health is computed,
(c) which PIT form is available.

> **Key intuition for IT:** UoP/zlecenie ZUS is a **percentage** of gross (scales with salary).
> B2B ZUS is a **fixed złoty amount** (≈1,788 zł/mo in 2026 on "duży ZUS"). That's why B2B gets
> dramatically more efficient as income rises — the social burden stops growing.

---

## 1. 2026 constants

| Constant | 2026 value | Used for |
|---|---|---|
| Minimum wage (`płaca minimalna`) | **4,806 zł/mo** | Health minimums, preferential ZUS, zlecenie floor |
| Min. hourly rate (zlecenie) | 31.40 zł/h | Zlecenie minimum |
| Forecast average wage (`prognozowane przeciętne`) | **9,420 zł** | B2B "duży ZUS" base |
| **Duży ZUS** social base (60% of avg) | **5,652.60 zł** | B2B standard social base |
| Preferential ZUS base (30% of min wage) | 1,441.80 zł | B2B first 24 months |
| Annual pension/disability cap (`30‑krotność`) | ~282,600 zł/yr | Emerytalna+rentowa stop above this |
| Tax‑free amount (`kwota wolna`) | 30,000 zł/yr → **300 zł/mo credit** | PIT‑2 monthly reduction |
| 1st bracket / threshold | **12%** up to **120,000 zł/yr**, then **32%** | Skala podatkowa |
| Youth relief cap (`ulga dla młodych`) | **85,528 zł/yr** | Under‑26 PIT exemption |
| 50% KUP annual cap (copyright) | 120,000 zł/yr | IT honorarium deduction |

**Health (`składka zdrowotna`) 2026:**

| Tax form | Health formula | 2026 minimum / fixed | Deductible? |
|---|---|---|---|
| Skala (UoP, zlecenie, B2B‑skala) | 9% of income | min **432.54 zł** (9% × 4,806) | **No** (since Polski Ład) |
| B2B liniowy (19%) | 4.9% of income | min 432.54 zł | Partly — up to **14,100 zł/yr** |
| B2B ryczałt | fixed by annual revenue tier | ≤60k: **498.35** · 60–300k: **830.58** · >300k: **1,495.04** zł/mo | 50% of paid health off revenue |

> `Rok składkowy` for B2B health runs **Feb–Jan**, not the calendar year — January 2026's health
> minimum (314.96 zł) differs from Feb‑onward (432.54 zł).

---

## 2. ZUS rates — who pays what

| Contribution | Total rate | **UoP** (employee side) | **Zlecenie** (contractor side) | **B2B** (self, full) |
|---|---|---|---|---|
| Emerytalna (pension) | 19.52% | 9.76% | 9.76% | 19.52% |
| Rentowa (disability) | 8% | 1.5% | 1.5% | 8% |
| Chorobowa (sickness) | 2.45% | 2.45% (mandatory) | 2.45% (**voluntary**) | 2.45% (**voluntary**) |
| Wypadkowa (accident) | 1.67%* | — (employer) | — (payer) | 1.67% |
| Fundusz Pracy | 2.45% | — (employer) | — (payer) | 2.45% |
| **Employee/self total** | | **13.71%** | **11.26%** (+2.45% if sickness) | **fixed kwota** (below) |

\* Accident rate is 1.67% for small payers (≤9 insured); varies for larger firms. Health (9%) is
**on top** of all the above.

**B2B "duży ZUS" 2026** (on the 5,652.60 base): pension 1,103.39 + disability 452.21 + accident
94.40 + Fundusz Pracy 138.49 = **≈1,788.49 zł/mo mandatory**, + 138.49 if voluntary sickness ⇒
≈1,926.98 zł. Flat amount regardless of how much you invoice.

---

## 3. Umowa o pracę (permanent / UoP)

```
social   = gross × 13.71%                       # 9.76 + 1.5 + 2.45
health   = (gross − social) × 9%                # not deductible
kup      = 250 zł  (or 300 commuting, or 50% honorarium)
base     = round(gross − social − kup)          # to whole zł
pit      = round(base × 12% − 300)              # 32% above 120k/yr; 300 credit needs PIT-2
net      = gross − social − health − pit
```

**Example — 10,000 zł gross, over 26, PIT‑2, standard KUP:**
- social = 1,371.00 → health base = 8,629.00 → health = 776.61
- taxable = 8,629 − 250 = 8,379 → PIT = 8,379 × 12% − 300 = **705.48**
- **net = 10,000 − 1,371 − 776.61 − 705 ≈ 7,147 zł** (~71.5%)

Gotchas: above ~23,550 zł/mo cumulative the pension/disability cap kicks in (those stop, net %
jumps); 32% bracket starts at 120,000 zł/yr cumulative; employer also pays ~20% on top.

---

## 4. Umowa zlecenie (contract / mandate)

Like UoP but: **sickness is voluntary**, **KUP is 20%** (lump‑sum, on gross−social) or 50% for
copyright, and ZUS depends on **other titles** (`zbieg tytułów`).

```
social   = gross × 11.26%        # 9.76 + 1.5  (+2.45 if voluntary sickness)
health   = (gross − social) × 9%
kup      = (gross − social) × 20%        # or 50% honorarium
base     = round(gross − social − kup)
pit      = round(base × 12% − 300)       # credit only if PIT-2 filed
net      = gross − social − health − pit
```

**Example — 10,000 zł gross, over 26, no sickness, 20% KUP:**
social 1,126 → health 798.66 → KUP 1,774.80 → base 7,099 → PIT 551.88 → **net ≈ 7,523 zł**.

**Critical cases:**
- **Student under 26** (§6): **no ZUS, no health, no PIT** → **net = gross**.
- **Zbieg tytułów:** if the person already earns ≥ minimum wage from a UoP elsewhere, a parallel
  zlecenie owes **only health** (social optional/none). Multiple zlecenia depend on order/amounts.
  This is where most real‑world zlecenie net calcs go wrong.

---

## 5. B2B (JDG — self‑employment), the IT default

Three knobs: **ZUS scheme**, **health**, **PIT form**. Pick once, recompute everything.

### 5a. ZUS scheme
- **Preferencyjny** (first 24 months, base 1,441.80): mandatory social ≈ 456 zł/mo.
- **Mały ZUS Plus** (income‑based, up to 36 months): base between 1,441.80 and 5,652.
- **Duży ZUS** (default afterwards, base 5,652.60): **≈1,788 zł/mo** mandatory. Sickness +138.

### 5b. PIT form (the real IT decision)

| Form | Rate | Cost deduction | Health | Best when |
|---|---|---|---|---|
| **Ryczałt** | **12%** (software dev) or **8.5%** (support/testing/training) | none (taxes revenue) | fixed tier, 50% deductible | Low real costs (most contractors) |
| **Liniowy** | 19% flat | full costs | 4.9% income, 14.1k deductible | High costs, high income |
| **Skala** | 12%/32% | full costs | 9% income, not deductible | Low income / spouse / many reliefs |
| **IP Box** | **5%** on qualified IP income | — | per underlying form | Software copyright income (§6) |

**Ryczałt rate for IT:** **12%** for actual software development / IT consulting
(PKWiU 62.01.1, 62.03.1, 58.21/58.29). **8.5%** only for clearly *non‑software* work (manual
testing, helpdesk, some training) — heavily scrutinised; get an `interpretacja indywidualna`
before relying on it.

**Example — B2B ryczałt 12%, 20,000 zł/mo revenue, duży ZUS, no sickness, tier 2 health:**
```
social   = 5,652.60 × 31.64% = 1,788.49
health   = 830.58                        # annual rev 240k → 60–300k tier
base     = 20,000 − 1,788.49 − 0.5×830.58 = 17,796.22 → 17,796
pit      = 17,796 × 12% = 2,135.52
net      = 20,000 − 1,788.49 − 830.58 − 2,135.52 ≈ 15,245 zł   (~76%)
```
The **flat ZUS** makes the effective rate *improve* with income.

---

## 6. IT‑specific reliefs

| Relief | Who | Effect | Applies to |
|---|---|---|---|
| **Ulga dla młodych** (under 26) | Age < 26 | PIT **exempt** on income up to **85,528 zł/yr** | UoP + zlecenie. **Not** B2B, **not** dzieło |
| **Student zlecenie** | Student **and** < 26 | **No ZUS, no health** (plus youth PIT relief) → net = gross | Zlecenie only (UoP always has ZUS) |
| **PIT‑2 / kwota wolna** | Single‑payer filer | 300 zł/mo tax credit; without it monthly PIT is 300 higher | UoP, zlecenie, B2B‑skala |
| **50% KUP** (copyright) | Code = a "work", contract transfers rights | Halves PIT base on the honorarium portion, cap 120,000 zł/yr | UoP, zlecenie |
| **IP Box** | B2B, qualified software IP | **5% PIT** on IP income | B2B (skala/liniowy) |

**Nuances:**
- Youth relief is **PIT‑only** — an under‑26 employee still pays full ZUS + health; they just owe
  no income tax (up to the cap). Student status is what removes ZUS, and **only on zlecenie**.
- Above the 85,528 cap, the excess is taxed under skala; the 30,000 kwota wolna / 300 credit then
  applies to that excess.
- **50% KUP and youth relief stack** (different mechanisms), each with its own annual cap.
- **IP Box 2026 caveat:** proposed change (project UD116) would restrict the 5% rate to firms
  employing ≥3 people. As of mid‑2026 it is **not yet in force**, but it's the biggest pending
  risk for solo B2B programmers.

---

## 7. Rounding & annualisation gotchas

- ZUS contributions round to **grosze**; PIT base and the monthly advance (`zaliczka`) round to
  **whole złoty**.
- The 12%→32% bracket, the 85,528 youth cap, the 120,000 50%‑KUP cap, and the ~282,600 pension cap
  are all **annual/cumulative** — a purely monthly calc approximates them by dividing by 12,
  slightly off for variable‑income or threshold‑crossing months.
- Health has a **floor** (432.54 zł) — in low/loss B2B months you still pay the minimum.

---

## 8. Mapping to `app/domain/salary_calculator.py`

The code is **2026‑accurate** for the baseline cases — every constant was verified:
- `EMPLOYMENT_SOCIAL_SECURITY_RATE = 0.1371`, civil `0.1126`, health 9%, KUP 250 / 20% ✓
- `B2B_FULL_ZUS_BASE_2026 = 5,652.60`, mandatory rate `0.3164`, ryczałt health tiers
  `498.35 / 830.58 / 1,495.04`, 50% health deductible ✓
- 120,000 bracket, 300 credit, 12% / 32% ✓

**Modelled** via the optional `TaxSituation` value object (`app/domain/entities.py`), threaded
through `SalaryCalculator.calculate(..., situation=...)` and exposed on the user profile and the
`/salary/calculate` request (all fields optional; defaults reproduce the baseline):
1. **Under‑26 youth relief** → zero PIT on UoP/zlecenie up to the (monthly‑approximated) cap.
2. **Student + under‑26 on zlecenie** → zero ZUS + health (net = gross).
3. **PIT‑2 toggle** (`applies_tax_credit`) → governs the 300 zł/mo tax‑reducing amount.
4. **B2B tax form** (`b2b_tax_form`: ryczałt 12% · ryczałt 8.5% · liniowy 19% · skala) and
   **ZUS scheme** (`b2b_zus_scheme`: duży ZUS · preferential · ulga na start).

**Not yet modelled** (the `TaxSituation` VO extends without reworking the calculator):
5. **Mały ZUS Plus** (needs prior‑year income) and **IP Box 5%** (qualified‑IP share; 2026 legal
   flux). The monthly‑constant approximation also applies annual thresholds (32% bracket, youth
   cap, pension cap) as ÷12.

---

## Sources

2026 figures verified against:
- [ZUS — składki na ubezpieczenia społeczne 2026](https://www.zus.pl/en/-/nowe-wysoko%C5%9Bci-sk%C5%82adek-na-ubezpieczenia-spo%C5%82eczne-w-2026-r.)
- [Składki ZUS 2026 — ifirma.pl](https://www.ifirma.pl/blog/skladki-zus-2026-ile-wynosza-aktualne-skladki-zus-dla-przedsiebiorcow/) · [biznes.gov.pl — składki przedsiębiorcy](https://www.biznes.gov.pl/pl/portal/00274)
- [Składka zdrowotna 2026 — inFakt](https://www.infakt.pl/blog/skladka-zdrowotna-2026-skala-podatkowa-podatek-liniowy-ryczalt-i-inne-formy/) · [poradnikprzedsiebiorcy — składka zdrowotna](https://poradnikprzedsiebiorcy.pl/-nowy-polski-lad-skladka-zdrowotna-uzalezniona-od-dochodu-i-bez-odliczenia)
- [Ryczałt dla programisty 2026 — podatkiprogramisty.pl](https://podatkiprogramisty.pl/ryczalt-programisty-jakie-podatki-placi-programista-na-ryczalcie/) · [Kody PKD w IT a stawka ryczałtu](https://poradnikprzedsiebiorcy.pl/-kody-pkd-w-it-i-ich-wplyw-na-stawke-ryczaltu)
- [Ulga dla młodych 2025/2026](https://pomagam.pl/blog/zerowy-pit-dla-mlodych-2025-2026-ulga-dla-mlodych-podatek-zasady-zwolnienia) · [Student na umowie zlecenie — składki ZUS](https://poradnikprzedsiebiorcy.pl/-student-na-umowie-zlecenie-a-skladki-zus)
- [IP Box i 50% koszty dla IT — Traple](https://www.traple.pl/50-koszty-i-ip-box-czyli-ulgi-podatkowe-dla-pracownikow-z-branzy-it/) · [IP Box 2026 — Infor](https://ksiegowosc.infor.pl/podatki/ulgi/7493670,ip-box-2026-rzad-nie-zdazyl-zmiany-projekt-ud116-co-dalej-prace-trwaja-legislacja-ulgi-podatkowe-likwidacja-koszty-programowanie-programisci-outsourcing-koszty-pracy-podatki-mf-gov-pl.html)

*Tax law changes annually and individual situations vary (zbieg tytułów, reliefs, joint filing).
Treat this as an engineering reference for the calculator, not tax advice.*
