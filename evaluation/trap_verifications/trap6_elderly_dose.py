"""
Trap 6 — Ciprofloxacin + Renal Impairment (dose adjustment required)
Expected:
  - contraindication row for ciprofloxacin + renal impairment (N18)
  - severity = dose_adjustment or contraindicated
  - reason mentions dose, interval, or renal
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

cur = connect().cursor()
cur.execute("""
    SELECT c.severity, c.reason
    FROM contraindications c
    JOIN molecules m ON m.id = c.molecule_id AND m.inn = 'ciprofloxacin'
    JOIN disease_concepts dc ON dc.id = c.disease_concept_id
    WHERE dc.icd11_code LIKE 'N18%'
       OR dc.condition_name ILIKE '%renal%'
       OR dc.condition_name ILIKE '%kidney%'
""")
rows = cur.fetchall()

if not rows:
    fail("no contraindication row found for ciprofloxacin + renal impairment")

sev, reason = rows[0]
errors = []

if sev not in ("dose_adjustment", "contraindicated", "monitoring"):
    errors.append(f"severity={sev!r} — expected dose_adjustment or contraindicated")

reason_lower = (reason or "").lower()
if not any(w in reason_lower for w in ("dose", "interval", "renal", "gfr", "clearance", "kidney", "ckd")):
    errors.append(f"reason does not mention dose adjustment or renal: {reason!r}")

if errors:
    fail(" | ".join(errors))

pass_(f"severity={sev}  reason mentions dose/renal adjustment")
