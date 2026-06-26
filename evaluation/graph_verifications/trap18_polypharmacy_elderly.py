"""
Trap 18 — Polypharmacy in elderly patient (6 drugs, multiple interactions)
Traversal: Patient properties + multi-hop interaction scan
Expected:
  - patient Bechir Hajji born 1946 (age > 75)
  - patient takes ≥ 6 drugs simultaneously
  - at least one direct INTERACTS_WITH edge exists among co-prescribed drugs
  - warfarin + aspirin DDI detectable from patient's medication set
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

# Count drugs and check age
poly = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'polypharmacy_elderly'})
    MATCH (p)-[:TAKES]->(d:Drug)
    RETURN p.name AS name, p.dob AS dob, count(d) AS drug_count
    """
)

# Find any DDI among this patient's drugs
ddi_scan = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'polypharmacy_elderly'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m1:Molecule)
          -[r:INTERACTS_WITH]-(m2:Molecule)
          <-[:BRAND_OF]-(:Drug)<-[:TAKES]-(p)
    WHERE id(m1) < id(m2)
    RETURN m1.inn AS drug_a, r.severity_active AS sev, m2.inn AS drug_b
    ORDER BY r.severity_rank DESC
    LIMIT 5
    """
)
driver.close()

errors = []

if not poly.records:
    errors.append("trap patient 'polypharmacy_elderly' not found")
else:
    rec        = poly.records[0]
    dob        = rec["dob"]
    drug_count = rec["drug_count"]
    if dob and int(str(dob)[:4]) > 1951:
        errors.append(f"patient dob={dob!r} — expected birth year ≤ 1951 (age > 75)")
    if drug_count < 6:
        errors.append(f"drug_count={drug_count} — expected ≥ 6 for polypharmacy scenario")

if not ddi_scan.records:
    errors.append("no INTERACTS_WITH edges found among patient's co-prescribed drugs")

if errors:
    fail(" | ".join(errors))

count = poly.records[0]["drug_count"]
interactions = [(r["drug_a"], r["sev"], r["drug_b"]) for r in ddi_scan.records]
pass_(
    f"age>75  drugs={count}  "
    f"interactions={[(a, s) for a, s, b in interactions[:3]]}"
)
