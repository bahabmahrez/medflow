# Week 6 — Overview for the team

**Start here.** This is the map of what Week 6 added, why each piece exists, how
to run it, and what is still open. Per-milestone detail lives in
[WEEK6_M1_REACTIVE_ENGINE.md](WEEK6_M1_REACTIVE_ENGINE.md),
[WEEK6_M2_MEMORY.md](WEEK6_M2_MEMORY.md) and
[WEEK6_M3_INTERFACE.md](WEEK6_M3_INTERFACE.md).

Status at 2026-07-31: **M1 complete and measured · M2 complete and verified ·
M3 built · M4 not started.** Full non-live suite: **216 passed** before M3's
tests, plus 22 interface tests.

---

## 1. What Week 6 is

Weeks 1–5 built the knowledge and the reasoning: a drug-interaction graph, query
functions, a GraphRAG pipeline, then an agent that drives those tools over MCP.
That agent is **conversational** — a pharmacist asks, it reasons, it answers.

Week 6 adds the thing a pharmacy actually runs on: the **reactive flow**. Scan a
prescription, get a complete verdict in under two seconds, with the reasoning
attached, and have the system remember what you decided.

```
        WEEKS 1-5 (conversational)            WEEK 6 (reactive)
   pharmacist asks a question            pharmacist scans a prescription
              |                                       |
        agent/loop.py                        engine/reactive.py
       LLM picks tools via MCP            all checks run concurrently
              |                                       |
        answer in prose                    structured alert report
                                                      |
                                            memory/ (what you decided)
                                                      |
                                            interface/app.py (the screen)
```

Both paths sit on the same `query/` layer and the same graph. Nothing from
Weeks 1–5 was replaced.

---

## 2. The pieces, and why each exists

| Module | What it does | Why it is separate |
|---|---|---|
| [engine/](../engine/) | `scan_prescription()` — runs every safety check concurrently and returns one severity-ordered alert report with reasoning chains | The reactive path must be **deterministic and fast**; no LLM in the hot path means no waiting and nothing to hallucinate |
| [memory/](../memory/) | Records what a pharmacist decided; a reviewed finding returns as a *reminder* | The Memory box of the reference architecture. Kept independent of the engine so a memory outage can never block a safety check |
| [interface/](../interface/) | Streamlit scan screen, patient loading, prescriber-message drafting | UI logic that is worth testing (parsing, mapping, drafting) lives outside Streamlit so it *can* be tested |

Supporting changes in existing code:

* **`query/_neo4j.py`** — one pooled, process-wide driver behind a proxy whose
  `.close()` is a no-op. This is what made the 2-second budget reachable; all
  ten query functions benefit with **no change to their own code**.
* **`query/resolve.py`** — in-process cache plus `resolve_many()` (one
  round-trip for a whole prescription).
* **`db/migrations/002_memory.sql`** — the three memory tables.

---

## 3. Running the whole thing

```bash
# 1. databases
docker compose up -d

# 2. memory tables (once; idempotent)
python -m memory
python -m memory --check

# 3. the pharmacist screen
pip install streamlit
streamlit run interface/app.py          # http://localhost:8501

# 4. prove the latency requirement
python -m engine.benchmark --runs 20

# 5. tests
python -m pytest -m "not live" -q       # everything that needs no API key
python -m pytest engine/tests memory/tests interface/tests -q
```

In the screen: enter a **pharmacist code** (enables memory), pick a `[test]`
patient, type a prescription, press **Check prescription**.

---

## 4. How a scan actually works

Worth understanding before changing anything:

1. **Preload** — every drug name (prescription + active meds) is resolved in
   *one* graph round-trip, warming a process-wide cache.
2. **Backend check** — if resolution errored (as opposed to "drug not found"),
   the scan **stops** and reports `status: "unavailable"`. It must never render
   a dead database as "no issues found".
3. **Fan-out** — pairwise interactions, CYP competition, and the per-drug checks
   (contraindication, allergy, duplication, dose) run concurrently on a thread
   pool sharing the pooled driver.
4. **Alerts** — each finding becomes an alert with a severity, an action, and a
   reasoning chain composed from graph data. A pair flagged by both the direct
   and the CYP check is **merged into one alert** (the more severe leads).
5. **Memory** — if a patient and pharmacist are known, previously reviewed
   findings are annotated and demoted to reminders (never contraindicated ones).
6. **Measure** — `latency_ms`, `within_budget`, and a per-stage breakdown ride
   along on every report.

Measured: **62 ms cold start, 311 ms worst case** (10-drug polypharmacy with
full patient context) against a 2000 ms budget.

---

## 5. Rules the code follows (please keep them)

These are safety invariants, each with a test:

1. **A dead backend is never a clean report.** Unreachable graph →
   `status: "unavailable"`, `risk: UNKNOWN`, explicit "not screened" warning.
2. **An unchecked drug says so.** A name the graph doesn't know gets its own
   alert stating *absence of an alert is not evidence of safety*.
3. **Memory changes presentation, never severity.** Contraindicated findings are
   never demoted to reminders; a finding that has become *more* severe since it
   was reviewed resurfaces as new.
4. **Reasoning chains state only what the graph holds.** If there is no recorded
   mechanism, no mechanism is stated — that is why they are templates, not LLM
   output.
5. **User-facing strings stay ASCII.** The project's console is cp1252; em-dashes
   in alert text crash it. (This bit us twice already.)

---

## 6. Open items for Milestone 4

**Blocking, and the first thing to fix:**

> **Contraindications currently never fire.** The graph holds
> `Renal impairment (N18)` and `Chronic kidney disease stage 4 (GB61)` as two
> unlinked concepts; metformin's `CONTRAINDICATED_FOR` edge points at the first,
> patients carry the second. Across the loaded population, **11 of 11 distinct
> patient conditions have no contraindication edge targeting them**, so the
> `metformin_ckd` trap patient reports only a dose note. This is a false
> negative on a safety check and directly fails M4's sensitivity target. Fix
> belongs in the knowledge-base layer — link the concepts, or re-point the edges
> onto the concepts patients actually carry.

Also open:

* **Alert volume.** A 10-drug patient produces 26 alerts. Merging pairs cut it
  from 39, but M4's "specificity / alert fatigue" measure needs a real look.
* **Severity grading to sanity-check.** `fluoxetine + sertraline` (serotonin
  syndrome trap) is graded `a_prendre_en_compte` → surfaces as **minor**. Worth
  questioning with the pharmacist.
* **Judgement calls to validate with the real pharmacist:** the 90-day memory
  window, the "never demote contraindicated" rule, and collapsing reasoning
  chains by default.
* Record the M4 evaluation: sensitivity (8 traps), specificity, severity
  accuracy, latency under load, plus the adversarial battery from earlier weeks.

---

## 7. Where to look when something breaks

| Symptom | Look at |
|---|---|
| Scan says "NOT CHECKED" | Neo4j down → `docker compose up -d`; check `report["warnings"]` |
| Everything shows as NEW despite decisions | pharmacist code empty, or Postgres down → `python -m memory --check` |
| Tests hang for minutes | a database is down; non-`live` tests still need Neo4j/Postgres |
| `UnicodeEncodeError` printing a report | non-ASCII in user-facing strings (see rule 5) |
| Latency over budget | `report["timings_ms"]` shows the per-stage split |
