"""
Trap 02 — Metformin + Chronic Kidney Disease (contraindication)
Traversal: direct CONTRAINDICATED_FOR edge
Expected:
  - CONTRAINDICATED_FOR edge exists for metformin → renal impairment concept
  - severity = contraindicated
  - reason mentions lactic acidosis or renal clearance
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()
result = driver.execute_query(
    """
    MATCH (m:Molecule {inn: 'metformin'})-[r:CONTRAINDICATED_FOR]->(dc:DiseaseConcept)
    WHERE dc.icd11_code STARTS WITH 'N18'
       OR dc.icd11_code STARTS WITH 'GB6'
       OR toLower(dc.condition_name) CONTAINS 'renal'
       OR toLower(dc.condition_name) CONTAINS 'kidney'
    RETURN r.severity AS sev, r.reason AS reason, dc.icd11_code AS icd
    """
)
driver.close()

if not result.records:
    fail("no CONTRAINDICATED_FOR edge for metformin → renal impairment")

rec    = result.records[0]
sev    = rec["sev"]
reason = (rec["reason"] or "").lower()
errors = []

if sev != "contraindicated":
    errors.append(f"severity={sev!r} — expected 'contraindicated'")

if not any(w in reason for w in ("lactic", "renal", "clearance", "kidney", "ckd", "glomerular")):
    errors.append(f"reason does not mention lactic acidosis or renal: {rec['reason']!r}")

if errors:
    fail(" | ".join(errors))

pass_(f"severity={sev}  icd={rec['icd']}  reason mentions renal/lactic")
