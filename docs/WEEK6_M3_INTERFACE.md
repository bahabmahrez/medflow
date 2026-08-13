# Week 6 — Milestone 3: The Pharmacist Interface

**Status:** built. 22 tests pass for the non-UI logic (parsing, patient mapping,
message drafting). Run it with `streamlit run interface/app.py`.

One screen, one job: **type or scan a prescription, get the alert report**, with
the patient's medication list in view and the dangerous finding first.

```bash
docker compose up -d
python -m memory                       # once, if you haven't
pip install streamlit
streamlit run interface/app.py         # opens http://localhost:8501
```

---

## 1. What the screen does

```
┌─ sidebar ──────────┐  ┌─ Prescription safety check ─────────────────────────┐
│ Pharmacist code    │  │                                                      │
│  ph-042            │  │  New prescription            │  Karim Ben Salah      │
│  Memory active     │  │  ┌────────────────────────┐  │  68 years · M · 74 kg │
│                    │  │  │ clarithromycin 500mg   │  │                       │
│ Patient            │  │  └────────────────────────┘  │  Active meds (2)      │
│  [test] Karim...   │  │  [ Check prescription ]      │  · warfarin (Coumadin)│
│                    │  │                              │  · simvastatin        │
└────────────────────┘  │ ══════════════════════════   │  Allergies (0)        │
                        │  DO NOT DISPENSE             │  Conditions (1)       │
                        │  HIGH risk · 1 contraindicated · 176 ms              │
                        │ ══════════════════════════                           │
                        │  ▌CONTRAINDICATED       [NEW]                        │
                        │  ▌Simvastatin + Clarithromycin                       │
                        │    Clarithromycin blocks simvastatin metabolism…     │
                        │    ▸ Why — reasoning chain                           │
                        │    ( ) acknowledged ( ) overridden …   [note____]    │
                        │    [Record decision]  [Draft message to prescriber]  │
                        └──────────────────────────────────────────────────────┘
```

Every requirement from the brief, and where it lives in
[interface/app.py](../interface/app.py):

| Requirement | How it is met |
|---|---|
| Enter **or scan** a prescription | Free-text box, one medicine per line. A barcode scanner that types a name and presses Enter works as-is — no special integration. `parse_prescription()` is deliberately forgiving (`clarithromycin 500mg`, `ibuprofen, 400mg`, `Tahor`). |
| See the patient's **active medication count** | Sidebar selector shows it per patient; the context panel repeats it as a heading with the full list. |
| **Colour-coded severity** | red `contraindicated` · orange `major` · yellow `moderate` · blue `minor`, as a coloured left border plus a severity chip. |
| Each alert **expands to show its reasoning chain** | `st.expander("Why — reasoning chain")`, collapsed by default, with the raw graph evidence underneath. |
| **"Contact prescriber" drafts the message** | `interface/prescriber.py` pre-fills patient, drug, finding, severity, the numbered reasoning, current medications, and an ask matched to the recommended action. |
| **Active medication list alongside** | Right-hand context column: meds, allergies (red), conditions, recent labs — in view while judging. |
| **Severity hierarchy — eye to the danger first** | One coloured verdict banner at the top (action first: *DO NOT DISPENSE*), then findings already sorted most-severe-first by the engine. |
| **Fast response** | The engine's measured budget; the screen shows the actual latency and the per-stage breakdown under "Run detail". |
| **Clean "no issues" case** | A calm green banner stating what *was* checked — "12 checks ran against 2 active medications in 41 ms" — never an empty screen. |

---

## 2. How it is wired

```
interface/app.py            Streamlit screen — layout, colour, interaction
   ├─ interface/patient_data.py   PostgreSQL → engine-ready lists
   ├─ interface/prescriber.py     alert → draft message (pure text)
   ├─ engine.scan_prescription    the M1 reactive engine
   └─ memory.MemoryStore          M2: recall + record decisions
```

Three deliberate boundaries:

* **The interface builds no SQL.** `patient_data.py` owns the queries and
  returns plain lists; `to_scan_kwargs()` maps a patient onto the engine's
  keyword arguments. The engine never learns the database exists.
* **The drafter is pure text.** No LLM, nothing to hallucinate — every line of
  the prescriber message comes from the alert on screen. That also makes it
  unit-testable, which is why it is a module and not inline in the UI.
* **Memory is optional.** No pharmacist code entered → the screen still scans,
  every finding shows as new, and the decision buttons are disabled with a hint.
  A memory outage never blocks a safety check.

### Caching
`@st.cache_resource` for the `MemoryStore` (one per session),
`@st.cache_data` for the patient list (5 min) and patient records (1 min) — so
switching patients does not re-query, but edits to the data show up promptly.

---

## 3. The decision loop (where M2 pays off)

Under each finding: a decision (`acknowledged`, `overridden`,
`prescriber_contacted`, `not_dispensed`, `dismissed`), an optional note, and
**Record decision**. That writes to `alert_reviews`, and the *next* scan for that
patient shows the finding as `ALREADY REVIEWED` with a caption —
*"You reviewed and accepted this 3 days ago. Note: prescriber confirmed."*

Contraindicated findings stay red and marked NEW even after review, by design —
see [WEEK6_M2_MEMORY.md §3](WEEK6_M2_MEMORY.md).

Each scan is also logged to `prescription_scans` (what was screened, what was
shown, how long it took), wrapped so logging can never break the screen.

---

## 4. Design choices worth knowing (and challenging)

These were judgement calls, not requirements. The real-pharmacist test in
Milestone 4 is the right place to check them:

1. **Everything on one screen, no navigation.** A counter workflow is
   interrupt-driven; a second page is a place to lose context.
2. **The verdict is a sentence, not a score.** "DO NOT DISPENSE" beats
   "risk: 0.87" for someone deciding in seconds.
3. **Reasoning collapsed by default.** Keeps the screen scannable while leaving
   the evidence one click from the claim. If pharmacists distrust collapsed
   evidence, expanding the top finding by default is a one-line change.
4. **Decisions need a pharmacist code, not a login.** Enough to attribute the
   audit trail without pretending to be an authentication system.
5. **Unknown drugs are shown as a warning, not hidden.** "Absence of an alert is
   not evidence of safety" is stated on screen.

---

## 5. Verification

```bash
python -m pytest interface/tests -q    # 22 tests, no Streamlit needed
streamlit run interface/app.py         # the screen itself
```

Tests cover prescription parsing (doses, bullets, multi-word names, the
"trailing word without digits is not a dose" case), the patient→engine mapping,
lab-name mapping, and the drafted message (identifies patient and drug, states
severity, includes the reasoning, matches the ask to the action, stays
cp1252-safe for console demos).

The Streamlit layer itself is not unit-tested — that is why the logic worth
testing lives outside it.

**Manual smoke run.** Pick a `[test]` patient (they reproduce the known traps),
type the drug from their scenario. These are **measured outputs, 2026-07-31**,
not expectations:

| Patient (scenario) | Type this | Verdict | Top finding | ms |
|---|---|---|---|---|
| Karim Ben Salah (`warfarin_aspirin`) | `aspirin 100mg` | Contact prescriber | Aspirin + Warfarin — major | 116 |
| Nabil Chaabane (`simvastatin_clarity`) | `clarithromycin 500mg` | **Do not dispense** | Clarithromycin + Simvastatin — contraindicated | 10 |
| Amira Khelifi (`penicillin_allergy`) | `amoxicillin 1g` | **Do not dispense** | Amoxicillin — direct allergy conflict | 19 |
| Sonia Mansouri (`serotonin_syndrome`) | `sertraline 50mg` | Dispense with note | Fluoxetine + Sertraline — minor | 19 |
| Hedi Boughanmi (`elderly_dose`) | `ciprofloxacin 500mg` | Dispense with note | Ciprofloxacin — dose review (age) | 10 |
| (`cyp2c9_overload`) | `fluconazole 200mg` | Contact prescriber | Fluconazole — already taken | 12 |
| (`therapeutic_dup`) | `atorvastatin 20mg` | Contact prescriber | Atorvastatin — already taken as… | 8 |
| (`therapeutic_dup`) | `amoxicillin 1g` | **Dispense** | — calm green "no issues found" | 5 |
| Fatma Trabelsi (`metformin_ckd`) | `metformin 850mg` | Dispense with note | dose review only — **see defect below** | 10 |

### Known defect — contraindications never fire (found by this smoke run)

`metformin_ckd` should be **CONTRAINDICATED**. It is not, and the cause is a
data-linkage gap rather than anything in the engine:

* the graph holds two *separate, unlinked* concepts — `Renal impairment` (N18)
  and `Chronic kidney disease stage 4` (GB61);
* metformin's `CONTRAINDICATED_FOR` edge points only at **Renal impairment (N18)**;
* the patient's record says **CKD stage 4 (GB61)**.

Clinically the same thing, structurally disconnected, so the substring/ICD match
in `check_contraindications` finds nothing. Checked across the whole loaded
population: **11 of 11 distinct patient conditions have no contraindication edge
targeting them**, so the contraindication check currently cannot fire for any
patient in the database.

This is a **false negative on a safety check** and the first thing Milestone 4
must fix — its sensitivity target is "the 8 trap patients must all pass". The
fix belongs in the knowledge-base layer (link the concepts, or re-point the
edges onto the concepts patients actually carry), not in the interface.
