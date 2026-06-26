"""
Trap 19 — NSAID + Active Peptic Ulcer (contraindication via DA41)
Traversal: Patient -[:HAS_CONDITION]-> DiseaseConcept <- [:CONTRAINDICATED_FOR]- Molecule
Expected:
  - patient Ines Chaouech has DA41 (peptic ulcer)
  - ibuprofen CONTRAINDICATED_FOR peptic ulcer concept
  - patient takes ibuprofen despite the contraindication
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

# Patient-centric: find condition ↔ contraindicated drug overlap
ci_match = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'nsaid_peptic_ulcer_ci'})
          -[:HAS_CONDITION]->(dc:DiseaseConcept)
          <-[r:CONTRAINDICATED_FOR]-(m:Molecule)
          <-[:BRAND_OF]-(:Drug)<-[:TAKES]-(p)
    RETURN p.name AS patient, m.inn AS drug, dc.icd11_code AS icd, r.severity AS sev
    """
)

# Also verify the knowledge graph edge exists independently
ci_edge = driver.execute_query(
    """
    MATCH (m:Molecule {inn: 'ibuprofen'})-[r:CONTRAINDICATED_FOR]->(dc:DiseaseConcept)
    WHERE dc.icd11_code = 'K27'
       OR toLower(dc.condition_name) CONTAINS 'peptic'
       OR toLower(dc.condition_name) CONTAINS 'gastric ulcer'
    RETURN r.severity AS sev, dc.icd11_code AS icd, dc.condition_name AS cname
    """
)
driver.close()

errors = []

if not ci_edge.records:
    errors.append("ibuprofen CONTRAINDICATED_FOR peptic ulcer (DA41) edge missing from knowledge graph")

if not ci_match.records:
    errors.append(
        "patient-centric contraindication traversal found no match — "
        "patient may lack DA41 condition, or ibuprofen CONTRAINDICATED_FOR edge is absent"
    )
else:
    rec = ci_match.records[0]
    if rec["drug"] != "ibuprofen":
        errors.append(f"expected ibuprofen as contraindicated drug, got {rec['drug']!r}")
    if rec["sev"] not in ("contraindicated", "contre_indique"):
        errors.append(f"severity={rec['sev']!r} — expected contraindicated/contre_indique")

if errors:
    fail(" | ".join(errors))

rec = ci_match.records[0]
pass_(
    f"patient={rec['patient']}  ibuprofen CONTRAINDICATED_FOR {rec['icd']}  "
    "patient-centric traversal detected"
)
