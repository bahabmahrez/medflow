# Week 6 — Milestone 2: The Memory Module

**Status:** complete and verified against live PostgreSQL on **2026-07-31**.
40 tests pass (30 pure + 10 database round-trips); full non-live suite **216 passed**;
the 2-second scan budget still holds (worst case 210 ms).

The agent no longer starts blank. It remembers what a pharmacist already decided
about a patient, so a finding they reviewed last week arrives as a **reminder**
instead of a fresh red alert.

```python
from engine import scan_prescription
from memory import MemoryStore

store = MemoryStore()
store.init_schema()                                     # once
ph = store.get_or_create_pharmacist("ph-042", "A. Ben Salah")

report = scan_prescription(rx, patient_meds=meds,
                           patient_id=181, pharmacist_id=ph)

store.record_decision(181, ph, report["alerts"][0], "acknowledged",
                      note="Prescriber confirmed; INR monitored weekly.")
```

Observed end-to-end (patient 181, same pharmacist, two consecutive scans):

```
SCAN 1  176 ms   {'new': 3, 'reminders': 0}
  [NEW     ] contraindicated  Simvastatin + Clarithromycin
  [NEW     ] major            Warfarin + Clarithromycin - CYP3A4 competition
  [NEW     ] minor            Warfarin + Simvastatin

SCAN 2   54 ms   {'new': 1, 'reminders': 2}
  [NEW     ] contraindicated  Simvastatin + Clarithromycin
             memory: You overrode this earlier today, but the severity of this
                     finding means it is always shown in full.
  [REMINDER] major            Warfarin + Clarithromycin - CYP3A4 competition
             memory: You reviewed and accepted this earlier today.
  [REMINDER] minor            Warfarin + Simvastatin
             memory: You reviewed and accepted this earlier today.
```

---

## 1. The schema — what is remembered, and why

PostgreSQL, in [db/migrations/002_memory.sql](../db/migrations/002_memory.sql).
Three tables:

### `pharmacists` — *who* reviewed
| column | type | why |
|---|---|---|
| `id` | SERIAL PK | |
| `code` | VARCHAR(64) UNIQUE | badge / login identifier |
| `name` | VARCHAR(255) | display |
| `created_at` | TIMESTAMPTZ | |

Memory is keyed by pharmacist as well as patient. **One pharmacist accepting a
risk is not a decision another pharmacist has made** — a locum on the evening
shift must see the finding at full strength.

### `alert_reviews` — the decisions (the actual memory)
| column | type | why |
|---|---|---|
| `patient_id` → patients | INT FK | memory is per patient |
| `pharmacist_id` → pharmacists | INT FK | …and per pharmacist |
| `scan_id` → prescription_scans | INT FK | which screen it was decided on |
| `fingerprint` | VARCHAR(255) | **stable identity of the finding** (below) |
| `alert_type` | VARCHAR(40) | interaction / contraindication / … |
| `severity` | VARCHAR(20) | severity **at the time of review** — lets us detect escalation |
| `title`, `drugs` | TEXT, TEXT[] | readable audit snapshot |
| `decision` | VARCHAR(30) | `acknowledged` · `overridden` · `prescriber_contacted` · `not_dispensed` · `dismissed` |
| `note` | TEXT | the pharmacist's justification |
| `reviewed_at` | TIMESTAMPTZ | drives recency and expiry |

**Append-only.** A new decision never overwrites the old one. It is a clinical
audit trail (who accepted what, when, and why), it answers "how often has this
come up", and an overwrite would destroy exactly the evidence you would want
after an incident.

### `prescription_scans` — what was screened and shown
Stores the prescription, the full alert report as JSONB, the risk/action, and
`latency_ms`. Gives each alert a provenance and feeds alert-volume and latency
reporting for Milestone 4.

Index `idx_reviews_lookup (patient_id, pharmacist_id, fingerprint, reviewed_at DESC)`
serves the hot path: one query per scan for every finding on screen.

---

## 2. Recognising the same finding twice

Alert ids (`INT-01`, `CYP-02`) are positional and change between runs, so memory
keys on a **fingerprint** derived from clinical content
([memory/fingerprint.py](../memory/fingerprint.py)):

```
ddi:clarithromycin|simvastatin        alg:amoxicillin|penicillin
ci:metformin|chronic kidney disease   dup:atorvastatin
dose:ciprofloxacin|renal_impairment
```

Two properties matter:

* **Order-free** — `warfarin + aspirin` and `aspirin + warfarin` are one
  finding, and which drug is "new" this time is irrelevant.
* **Merge-stable** — direct interactions and CYP competition for the same pair
  share the `ddi:` prefix. Milestone 1 merges those into one alert and *which one
  leads depends on their relative severity*, so keying on the alert's type would
  make the identity flip between scans and silently lose the memory.

Contraindications key on the graph's **matched concept**, not the typed text, so
"CKD stage 4" and "renal failure" resolve to the same memory. Duplications key on
the molecule, not the brand.

---

## 3. What memory changes — and what it must never change

Memory changes **presentation only**. The clinical severity is never rewritten:
an overridden contraindication is still a contraindication today. Two rules
enforce that ([memory/recall.py](../memory/recall.py)):

1. **`NEVER_DEMOTED`** — `contraindicated` findings always stay a full alert.
   They still carry the memory annotation ("you overrode this earlier today"),
   but they are never softened into a quiet reminder. A red-level finding that
   fades because someone clicked through it once is how alert-suppression
   systems hurt people.
2. **Escalation resets memory.** If a finding is more severe now than when it was
   reviewed (severity is stored per review for exactly this), the earlier
   decision no longer applies and it resurfaces as **new**, flagged
   `escalated: true`.

Reviews also **expire** after `DEFAULT_WINDOW_DAYS` (90, configurable): a
decision from two years ago is history, not a current judgement.

Ordering: reminders sink below new findings **of the same severity**, so
attention lands on what is genuinely new — but a major reminder still outranks a
minor new finding.

Each alert gains:
```python
{"status": "new" | "reminder",
 "memory": {"decision", "decision_label", "note", "reviewed_at",
            "reviewed_ago", "times_seen", "severity_when_reviewed",
            "escalated", "reason_shown"}}
```
and the report gains `summary.memory` = `{new, reminders, has_memory, escalated}`
so the interface can say "3 findings — 1 new, 2 already reviewed".

---

## 4. Failure behaviour

Memory is a convenience layer over a safety system, and it is wired so it can
never subtract from safety:

* the import is **lazy**, so the engine has no hard dependency on PostgreSQL;
* the call is **guarded** — if the database is down the scan still completes with
  every finding shown as new, plus a warning `memory unavailable, showing every
  finding as new: …`;
* connections use a short `connect_timeout`, matching the graph driver's
  fail-fast policy.

A memory outage costs the annotations, never the alerts.

---

## 5. Verification

```bash
docker compose up -d
python -m memory                     # apply the schema (idempotent)
python -m memory --check             # report status

python -m pytest memory/tests -q     # 40 tests (store tests skip without PG)
python -m pytest -m "not live" -q    # 216 passed
```

Tests cover fingerprint stability (order, case, merge, brand vs INN), the recall
policy (reminder demotion, never-demote, escalation, expiry, ordering,
non-mutation), the store round-trip against real PostgreSQL (append-only history,
`times_seen`, pharmacist scoping, recurring patterns), and the engine
integration including the outage path.

---

## 6. Notes for Milestone 3

The interface has everything it needs on each alert: `status` (`new`/`reminder`)
for visual weight, `memory.reason_shown` as a ready one-line caption,
`memory.note` for what was written last time, and `summary.memory` for the
"N new, M already reviewed" header. Recording a decision from the UI is one call:
`store.record_decision(patient_id, pharmacist_id, alert, decision, note=...)`.

**Open question for the real-pharmacist test (M4):** the 90-day window and the
"never demote contraindicated" rule are judgement calls made here, not clinical
standards. Both are single constants — worth asking the pharmacist whether they
match how a real counter works.
