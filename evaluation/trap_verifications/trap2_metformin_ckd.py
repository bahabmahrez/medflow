"""
Trap 2 — Metformin + Chronic Kidney Disease
Expected: contraindication entry for metformin + renal impairment (N18)
          severity = contraindicated
          reason mentions lactic acidosis or renal clearance
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

cur = connect().cursor()
cur.execute("""
    SELECT c.severity, c.reason
    FROM contraindications c
    JOIN molecules m ON m.id = c.molecule_id AND m.inn = 'metformin'
    JOIN disease_concepts dc ON dc.id = c.disease_concept_id
    WHERE dc.icd11_code LIKE 'N18%'
       OR dc.condition_name ILIKE '%renal%'
       OR dc.condition_name ILIKE '%kidney%'
""")
rows = cur.fetchall()

if not rows:
    fail("no contraindication row found for metformin + renal impairment (N18)")

sev, reason = rows[0]
errors = []
if sev != "contraindicated":
    errors.append(f"severity={sev!r} — expected 'contraindicated'")

reason_lower = (reason or "").lower()
if not any(w in reason_lower for w in ("lactic", "renal", "clearance", "kidney", "ckd")):
    errors.append(f"reason does not mention lactic acidosis or renal: {reason!r}")

if errors:
    fail(" | ".join(errors))

pass_(f"severity={sev}  reason mentions renal/lactic")
