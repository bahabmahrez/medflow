# Week 6 — Milestone 1: The Reactive Engine

**Status:** complete and verified against the live graph on **2026-07-31**.
31 unit tests pass; the full non-live suite is green (**176 passed**); the
2-second requirement is **met with ~6x headroom** (worst observed 311 ms).

The pharmacist's core workflow: scan a prescription, get one complete,
severity-ordered alert report, fast enough to use with a patient at the counter.

```python
from engine import scan_prescription

report = scan_prescription(
    [{"drug": "clarithromycin", "dose": "500mg"}],
    patient_meds=["simvastatin", "warfarin", "amiodarone"],
    conditions=["atrial fibrillation"], allergies=["penicillin"],
    age=78, labs={"creatinine_umol_L": 165},
)
report["summary"]["action_label"]   # "Do not dispense"
report["latency_ms"], report["within_budget"]
```

---

## 1. What it does

One call runs the complete check set — pairwise interactions across the new
prescription *and* the active list, CYP competition, contraindications against
conditions, allergy conflicts (direct and cross-reactive), therapeutic
duplication, and dose appropriateness against age/labs — then returns a single
**alert report**:

| Field | Meaning |
|---|---|
| `summary.overall_risk` | HIGH / MEDIUM / LOW / NONE / UNKNOWN |
| `summary.recommended_action` | `do_not_dispense` · `contact_prescriber` · `dispense_with_note` · `dispense` — the most cautious action any finding demands |
| `alerts[]` | findings sorted most-dangerous-first |
| `alerts[].severity` | `contraindicated` (red) · `major` (orange) · `moderate` (yellow) · `minor` (blue) |
| `alerts[].explanation` | one-line plain language |
| `alerts[].reasoning_chain` | the ordered steps from patient data to conclusion |
| `alerts[].evidence` | the raw graph fields behind the finding |
| `latency_ms` · `within_budget` · `timings_ms` | per-run measurement |
| `unresolved_drugs` · `warnings` | what could **not** be checked |

Files: [engine/reactive.py](../engine/reactive.py) (orchestration),
[engine/alerts.py](../engine/alerts.py) (severity, actions, reasoning),
[engine/benchmark.py](../engine/benchmark.py) (latency proof).

---

## 2. Meeting the 2-second budget

The budget was not a tuning exercise — the original path could not have met it.
A 7-drug scan created **40+ Neo4j drivers**, because every check re-resolved
every drug name and each `resolve_drug_name` built and tore down its own driver.

Four changes, in order of impact:

1. **One pooled driver instead of one per call.**
   [query/_neo4j.py](../query/_neo4j.py) now holds a process-wide driver behind a
   `_SharedDriver` proxy whose `.close()` is a deliberate no-op, so the existing
   `driver = connect() … finally: driver.close()` pattern in all ten query
   functions reuses the pool without a single change to their code.
2. **Preload + cache the drug reference data.** `resolve_many()` resolves the
   whole prescription in one round-trip and warms an in-process cache, so every
   downstream check hits memory instead of the graph. Transient errors are never
   cached.
3. **Concurrency.** Independent checks are fanned out over a shared thread pool.
   They share the pooled driver, so parallelism costs no extra connections.
4. **No inference in the hot path.** Reasoning chains are composed from graph
   data, so a scan never waits on an LLM.

**Fail-fast:** the driver's 30-second default retry was cut to a few seconds
(`NEO4J_CONNECTION_TIMEOUT`, `NEO4J_MAX_RETRY_TIME`). A pharmacist needs a clear
failure faster than a slow one.

### Measured result — 2026-07-31, 20 runs per scenario

```bash
docker compose up -d
python -m engine.benchmark --runs 20      # exits non-zero if any p95 > 2000 ms
```

Cold start (empty cache, first connection): **62 ms**

| Scenario | p50 | p95 | max | alerts |
|---|---:|---:|---:|---:|
| single new drug, no context | 0.0 | 0.0 | 0.0 | 0 |
| trap: warfarin + aspirin (direct) | 6.7 | 14.2 | 66.2 | 1 |
| trap: simvastatin + clarithromycin (CYP3A4) | 17.4 | 22.2 | 40.5 | 3 |
| trap: penicillin allergy (cross-reactive) | 7.5 | 14.4 | 59.0 | 1 |
| trap: elderly + renal impairment (dose) | 18.9 | 30.8 | 33.7 | 2 |
| trap: therapeutic duplication (brand vs INN) | 7.0 | 9.6 | 24.1 | 1 |
| **heavy: 8 active meds + 2 new + full context** | **259.1** | **291.5** | **311.4** | 26 |
| **ALL** | **8.4** | **264.3** | **311.4** | |

**PASS** — every scenario inside the 2000 ms budget; the worst case (a
10-drug polypharmacy scan with conditions, allergies, age and labs) lands at
**311 ms, ~6x under budget**.

---

## 3. Why the reasoning chains are deterministic

Each finding reads like a colleague explaining *why*:

> **Simvastatin + Clarithromycin — CYP3A4 competition (strong)** → *Contact prescriber*
> 1. Clarithromycin (newly prescribed) is recorded as a strong inhibitor of CYP3A4.
> 2. Simvastatin (an active medication) is metabolised by CYP3A4.
> 3. There is no direct interaction edge between these two drugs - this risk is
>    visible only through the metabolic pathway they share.
> 4. With CYP3A4 inhibited, simvastatin is cleared more slowly and its plasma
>    concentration rises above the expected range.
> 5. Clinical consequence - simvastatin accumulation, myopathy and rhabdomyolysis risk.
> 6. Because the inhibitor is graded strong, the recommended handling is to
>    contact the prescriber before dispensing.

Every sentence is derived from data the graph already returned. That choice buys
two things at once: the scan stays inside its budget (no inference call), and
**fabrication becomes structurally impossible** — if the graph records no
mechanism, no mechanism is stated (see the test asserting absent fields are
omitted rather than invented). It also upholds the project's standing rule that
the knowledge base is the only source of truth.

The LLM keeps its role in the *conversational* agent (`agent/loop.py`), where a
pharmacist asks follow-up questions. The reactive scan is the deterministic path.

---

### One pair, one alert

A drug pair can be flagged twice — once as a documented direct interaction and
once as enzyme competition. Showing both is redundant at the counter and
inflates alert counts, which is what drives alert fatigue (the heavy scenario
dropped from **39 alerts to 26** once merged). The more severe finding leads and
the other is folded in as a *Supporting finding* line, so nothing is lost.

This also fixed a correctness bug: the CYP chain's signature insight — *"there
is no direct interaction edge between these two drugs"* — was stated
unconditionally, and was simply false for a pair that had one. It is now
asserted only when true.

---

## 4. Two safety behaviours worth knowing

**An unchecked drug is never silently ignored.** A name the graph doesn't know
produces its own alert stating that no check could run for it, and that *absence
of an alert is not evidence of safety*.

**A dead backend never renders as "no issues found."** If resolution fails, the
scan short-circuits and returns `status: "unavailable"` with
`overall_risk: "UNKNOWN"` and an explicit warning that the prescription has
**not** been screened. This was a real bug found during development: with the
database down, the engine reported three real drugs as "not in the knowledge
base" and produced a clean-looking report — exactly the failure mode that would
get someone hurt.

---

## 5. Verification

```bash
python -m pytest engine/tests -q     # 31 tests, no DB or LLM needed
python -m pytest -m "not live" -q    # full suite — 176 passed (DBs up)
python -m engine.benchmark --runs 20 # latency proof (needs docker compose up -d)
```

Unit tests cover severity/action mapping, every reasoning-chain builder,
ordering and roll-up, pair merging, the unknown-drug and backend-unavailable
paths, and the latency instrumentation.

---

## 6. Follow-ups for the rest of Week 6

- `scan_prescription` is the natural seam for **Milestone 2 (memory)**: pass a
  patient/pharmacist id and downgrade alerts already reviewed and dismissed.
- Milestone 3's Streamlit screen renders this report directly — `severity`,
  `color`, `explanation`, `reasoning_chain` and `action_label` exist for it, and
  the "no issues" case is already a distinct calm state (`overall_risk: NONE`).
