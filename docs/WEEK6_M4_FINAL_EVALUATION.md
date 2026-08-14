# Week 6 - Milestone 4: Final Evaluation & Technical Report

**Date:** 2026-08-14 · **Model of record:** Groq `llama-3.3-70b-versatile` (agent
path) · **Graph:** Neo4j 5, 51 molecules / 38 brands / 48 disease concepts /
50 patients · **Test suite:** 243 passing

Run the whole measurable assessment with:

```bash
docker compose up -d
python -m evaluation.final_eval.run_all
```

---

## 1. Results at a glance

| Suite | Result | Bar | Where |
|---|---|---|---|
| **Sensitivity** (trap patients) | **8/8 (100%)** | must be 100% | [trap_sensitivity.py](../evaluation/final_eval/trap_sensitivity.py) |
| **Specificity** (safe cases) | **10/10, 0 false alarms** | no safe script blocked | [specificity.py](../evaluation/final_eval/specificity.py) |
| **Severity accuracy** | **0 mapping bugs**, 8/12 vs reference | faithful reporting | [severity_accuracy.py](../evaluation/final_eval/severity_accuracy.py) |
| **Latency under load** | **p99 1.61 s at 8 concurrent** | < 2 s | [latency_load.py](../evaluation/final_eval/latency_load.py) |
| **Adversarial battery** | **8/8 (100%)** live on Groq | must not fabricate | `evaluation/agent_eval` |
| Full 25-case agent suite | **unmeasured** — daily token cap hit (§6) | — | `evaluation/agent_eval` |
| **Real pharmacist test** | **not yet run** | qualitative | [PHARMACIST_SESSION_KIT.md](PHARMACIST_SESSION_KIT.md) |

Sensitivity and specificity are reported separately and never averaged: they
trade against each other, and a combined score would hide whichever is worse.

---

## 2. Sensitivity - the number that must be 100%

Every trap patient is a known dangerous scenario. A miss here is a patient
harmed, so this is the one metric with no acceptable shortfall.

```
[PASS] warfarin_aspirin      major           Warfarin + Aspirin
[PASS] metformin_ckd         contraindicated Metformin - contraindicated in Renal impairment
[PASS] simvastatin_clarity   contraindicated Clarithromycin + Simvastatin
[PASS] penicillin_allergy    contraindicated Amoxicillin - direct allergy conflict
[PASS] serotonin_syndrome    major           Tramadol + Fluoxetine
[PASS] elderly_dose          moderate        Ciprofloxacin - dose review needed
[PASS] cyp2c9_overload       major           Fluconazole + Warfarin
[PASS] therapeutic_dup       major           Atorvastatin - already on the active list

SENSITIVITY: 8/8 (100%)    latency: max 145 ms, mean 32 ms
```

Each case asserts three things, not one: the right *kind* of finding appears, at
or above the required *severity*, and it actually *names* the drugs at issue. A
generic alert that happens to fire does not pass.

### The defect this milestone found

**Before this milestone, contraindications fired for nobody.** `metformin_ckd`
reported only a dose note - a false negative on a lactic-acidosis risk.

Root cause was three data defects, not one:

1. `CONTRAINDICATED_FOR` edges point at general concepts (`Renal impairment`,
   N18) while patients carry specific ones (`Chronic kidney disease stage 4`,
   GB61) - and the graph held **zero** concept-to-concept edges.
2. ~30 concepts were named with their own ICD code (`BA00` rather than
   `Hypertension`), so nothing could match them by name.
3. Two concepts were named with a reason sentence, because the loader wrote the
   *reason* into the name field.

Fixed in the knowledge-base layer, where it belongs - not by special-casing the
engine: [load_disease_hierarchy.py](../knowledge_base/graph_loaders/load_disease_hierarchy.py)
repairs the names and adds conservative `IS_A` edges, and
`check_contraindications` now traverses `IS_A*0..3`. The loader is idempotent and
registered last in `run_loaders_graph.py` (patients must exist first). Five
regression tests in `query/tests/test_safety.py` pin the behaviour, including a
check that the hierarchy does **not** create false positives.

The pharmacist sees the inference stated plainly rather than hidden:

> 1. The patient's record lists 'Chronic kidney disease stage 4'.
> 2. The knowledge base classifies 'Chronic kidney disease stage 4' as a form of
>    'Renal impairment' (ICD-11 N18).
> 3. Metformin is recorded as contraindicated for this condition (ANSM/OpenFDA).
> 4. Reason - Risk of lactic acidosis - avoid when renal impairment is severe.

---

## 3. Specificity - not crying wolf

Ten routine, safe prescriptions. Findings are graded because not all noise is
equal: a CONTRAINDICATED/MAJOR alert on a safe script is a **false alarm** that
stops a dispensation; MODERATE/MINOR is **noise**, tolerable in small amounts.

```
SPECIFICITY: 10/10 safe cases free of false alarms (100%)
fully clean screens: 8/10
false alarms (contraindicated/major): 0
low-grade noise (moderate/minor):     2   (0.2 per safe prescription)
```

The two noise items are both real CYP3A4 competitions (`atorvastatin + amlodipine`,
`tramadol + amlodipine`) graded moderate. They are pharmacologically true, so
suppressing them would be wrong; whether they are *useful* at the counter is a
question for the pharmacist (§6).

**The honest limit:** 10 hand-picked safe cases is a small sample, and the cases
were chosen by the same person who built the system. A real specificity figure
needs a consecutive run of unselected prescriptions.

---

## 4. Severity accuracy - two different questions

The grade drives the action, so it was tested along two axes that are usually
conflated:

**A. Does the engine report the knowledge base faithfully?** An engineering
question with a right answer. **0 mapping bugs across 12 pairs, 0 missed.**

**B. Is the knowledge base clinically right?** Not a question this project can
answer alone. The reference column is the author's reading of standard practice,
not an authority, so disagreements are printed as REVIEW, never FAIL. **8/12
agree**; the four disagreements are queued for the pharmacist:

| Combination | Reference | System | Note |
|---|---|---|---|
| omeprazole + clopidogrel | moderate | major | Clinically debated interaction |
| diclofenac + methotrexate | major | moderate | Reduced MTX clearance |
| verapamil + simvastatin | major | moderate | CYP3A4; statin myopathy |
| rifampicin + warfarin | major | contraindicated | Strong inducer |

Writing this harness surfaced a **flaw in the harness itself**: it first reported
`verapamil + simvastatin` as a mapping bug. It was not. That alert is a *merged*
alert (direct interaction + CYP competition), and merged alerts deliberately
carry the more severe of the two findings, so their severity need not equal the
stored ANSM grade. The check now asserts the correct invariant - a merged alert
must be *at least* as severe as its stored grade - and the engine was right all
along.

---

## 5. Latency under load

The 2-second promise is made to a pharmacist with a patient at the counter, and a
promise that only holds on an idle machine is worth little. Heavy 10-drug scan
with full patient context, driven concurrently:

| concurrent | p50 | p95 | **p99** | max | scans/s |
|---:|---:|---:|---:|---:|---:|
| 1 | 208 | 240 | **248** | 250 | 4.8 |
| 2 | 292 | 344 | **373** | 389 | 6.7 |
| 4 | 559 | 631 | **652** | 660 | 7.0 |
| 8 | 1285 | 1587 | **1608** | 1614 | 6.3 |

**PASS** - p99 within budget at every level tested. Cold start is 62 ms; a
single warm scan is 32-210 ms depending on complexity.

**The honest limit:** throughput plateaus at roughly **7 scans/second** and p99 at
8 concurrent users leaves only ~20% headroom. A community pharmacy with 1-3
terminals is comfortably inside that; a hospital dispensary with a dozen
concurrent users would breach the budget. The bottleneck is Neo4j round-trips per
scan, not the engine.

---

## 6. Adversarial battery

Run live against Groq `llama-3.3-70b-versatile` - the first live agent run of the
project.

```
Adversarial :  8/8  (100%)
```

Covers leading questions ("it's fine, right?"), claimed authority ("I'm a senior
pharmacist"), invented drugs, dose fishing, out-of-scope requests, and tool
misuse (the agent must not inject a training-data-plausible drug name into a tool
call). Traces for all 8 are in `evaluation/runs/`.

**A structural point worth stating:** the reactive engine used by the interface
has **no LLM in its hot path** at all. Reasoning chains are composed from graph
data. It therefore cannot be prompt-injected, cannot hallucinate an interaction,
and cannot be talked out of a contraindication - the adversarial surface belongs
only to the conversational agent, which is a separate path.

### The full 25-case agent suite could not be measured

Attempting the whole suite immediately afterwards returned **4/25**, and a
re-run of one tier returned **0/7**. Neither is a quality result: both are
**Groq free-tier throttling**. The provider returned

```
429 - Rate limit reached ... tokens per day (TPD): Limit 100000, Used 96958
```

The 25 agentic runs (each one a multi-turn tool-calling loop) exhausted the
100k-token daily allowance. The adversarial 8/8 above was captured *before*
exhaustion and stands; the rest needs either a paid tier or a run spread across
days. **It is recorded as unmeasured rather than reported as 4/25**, because
publishing a throttled score as a quality figure would be straightforwardly
misleading.

**A real bug this uncovered.** Every provider failure - including the 429 - was
reported to the user as *"the model produced a malformed tool request"*. That
blames the model for a quota problem and cost real debugging time during this
evaluation. `agent/loop.py` now classifies the failure and names the actual
cause (`rate_limited` / `auth_error` / `llm_error`), keeps the raw provider error
in `trace["error"]`, and three tests pin the behaviour.

---

## 7. Real pharmacist test - NOT YET RUN

The remaining Milestone 4 requirement. It cannot be simulated, so it is recorded
as outstanding rather than approximated.

Preparation is complete in [PHARMACIST_SESSION_KIT.md](PHARMACIST_SESSION_KIT.md):
setup commands, eight cases ordered easy-to-hard, think-aloud protocol, an
observation sheet, and the three design decisions we most want challenged.

Write the session up here as §7 the same day it happens.

---

## 8. Production-readiness assessment (honest)

### What is genuinely ready
- **Detection of the modelled dangers** is reliable: 8/8 traps, 0 false alarms,
  0 severity-mapping bugs, all pinned by 243 automated tests.
- **The latency promise holds** for community-pharmacy concurrency, with
  measurements rather than assertions.
- **Failure modes are safe.** A dead graph reports "NO safety check was
  performed - verify manually" rather than an empty, reassuring screen. A dead
  memory database costs annotations, never alerts. An unresolvable drug name is
  surfaced as "absence of an alert is not evidence of safety".
- **The reasoning is inspectable.** Every finding shows the steps behind it, and
  chains omit fields the graph does not hold instead of inventing them.

### What is not ready
- **Knowledge-base coverage is the real ceiling.** 51 molecules and 304
  interactions is a demonstration corpus, not a formulary. The system is only as
  safe as what it knows, and it does not know most of a real pharmacy's stock.
  This is the single biggest gap between this build and something dispensable.
- **No clinical validation.** Severity grades have never been reviewed by a
  pharmacist; four are already known to be arguable (§4).
- **Specificity is measured on 10 self-selected cases.** Not a real-world rate.
- **Capacity ceiling ~7 scans/s** (§5), and every scan opens fresh Neo4j
  round-trips; there is no query-level caching beyond drug-name resolution.
- **Single-node, no auth, no audit-grade identity.** `NEO4J_AUTH: none`,
  pharmacist identity is a self-declared code with no authentication. Fine for a
  demo, unacceptable where dispensing decisions are attributable.
- **No regulatory posture.** No CE marking, no ANSM/DPM engagement, no clinical
  risk file. In most jurisdictions this class of tool is a regulated medical
  device.

### Verdict
**Suitable for supervised pilot use as a second opinion; not suitable for
unsupervised clinical use.** The engineering is sound and its failure modes are
conservative, but the knowledge base is too small and has never been clinically
reviewed. The correct next step is the pharmacist session, then expanding the
formulary - in that order, because the session may change what "correct" means.

---

## 9. Demo walkthrough - the reactive flow

Ten minutes, showing the mechanism rather than just the output.

**Setup:** `docker compose up -d` then `streamlit run interface/app.py`. Set a
pharmacist code in the sidebar so memory records under a real identity.

**1. The calm case (30s).** Any non-trap patient, prescribe `amoxicillin 1g`.
A green "no issues found" screen - deliberately calm rather than empty, because
"nothing found" is a result, not a blank.

**2. The classic (1 min).** Patient **Karim Ben Salah** (on warfarin), prescribe
`aspirin 100mg`. One orange MAJOR alert. Expand it: five reasoning steps ending
in a recommended action. Point out that the mechanism text comes from the graph -
nothing is generated.

**3. The one SQL cannot do (2 min).** Patient **Nabil Chaabane** (on
simvastatin), prescribe `clarithromycin 500mg`. Red CONTRAINDICATED, *Do not
dispense*. The chain shows the direct ANSM interaction **and**, folded in as a
supporting finding, the CYP3A4 pathway - two findings about one pair collapsed
into one alert. This is the graph traversal earning its place.

**4. The one that was broken (2 min).** Patient **Fatma Trabelsi** (CKD stage 4),
prescribe `metformin 1000mg`. Red contraindication. Step 2 of the chain says the
knowledge base *classifies CKD stage 4 as a form of renal impairment* - the
concept hierarchy added in M4. Worth saying plainly: before this milestone, this
screen showed only a dose note.

**5. Memory (2 min).** On the case-3 screen, record a decision
("prescriber contacted", with a note). Re-scan the same prescription: the MAJOR
CYP finding returns as a grey **REMINDER** carrying *"You contacted the prescriber
about this earlier today"* - while the CONTRAINDICATED finding stays red, because
memory never softens the top severity band.

**6. Speed and failure (1.5 min).** Show the latency readout on each scan
(32-310 ms). Then `docker compose stop neo4j` and scan again: the screen says
**NO safety check was performed - verify manually**, not "no issues found". Restart
with `docker compose start neo4j`.

**Closing line:** the reactive path never calls an LLM. Every sentence on screen
is assembled from graph data, which is why it fits in 300 ms and why it cannot
invent an interaction.

---

## 10. Reproducing everything

```bash
docker compose up -d
python -m memory                                  # memory schema (idempotent)

python -m pytest -m "not live" -q                 # 243 passed
python -m evaluation.final_eval.run_all           # sensitivity/specificity/severity/load
python -m engine.benchmark --runs 20              # cold-start + per-scenario latency

# live LLM (needs GROQ_API_KEY)
python -m evaluation.agent_eval.runner --tier adversarial
python -m evaluation.agent_eval.runner            # all 25 agentic cases
python -m evaluation.llm_eval.runner              # 30 GraphRAG cases

streamlit run interface/app.py                    # the pharmacist screen
```

Every evaluation run is logged as timestamped JSON in `evaluation/runs/`.
