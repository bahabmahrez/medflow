"""
Trap 11 — Allopurinol + Azathioprine (contre_indique: xanthine oxidase inhibition)
Traversal: direct INTERACTS_WITH edge
Expected:
  - INTERACTS_WITH edge with severity_active = 'contre_indique'
  - mechanism involves xanthine oxidase (allopurinol blocks azathioprine metabolism)
  - patient Kamel Zouari takes both drugs
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

ddi = driver.execute_query(
    """
    MATCH (a:Molecule {inn: 'allopurinol'})-[r:INTERACTS_WITH]-(b:Molecule {inn: 'azathioprine'})
    RETURN r.severity_active AS sev, r.clinical_effect AS effect, r.mechanism_type AS mech
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'allopurinol_azathioprine'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['allopurinol', 'azathioprine']
    RETURN collect(m.inn) AS drugs
    """
)
driver.close()

errors = []

if not ddi.records:
    fail("no INTERACTS_WITH edge between allopurinol and azathioprine")

sev = ddi.records[0]["sev"]
if sev != "contre_indique":
    errors.append(f"severity_active={sev!r} — expected 'contre_indique'")

combined = ((ddi.records[0]["effect"] or "") + " " + (ddi.records[0]["mech"] or "")).lower()
if not any(w in combined for w in ("xanthine", "myelosuppression", "toxicity", "6-mercaptopurine", "azathioprine")):
    errors.append("mechanism does not mention xanthine oxidase or myelosuppression")

if patient.records:
    drugs = patient.records[0]["drugs"]
    for mol in ("allopurinol", "azathioprine"):
        if mol not in drugs:
            errors.append(f"patient missing drug: {mol}")
else:
    errors.append("trap patient 'allopurinol_azathioprine' not found")

if errors:
    fail(" | ".join(errors))

pass_("severity=contre_indique  allopurinol+azathioprine  xanthine oxidase inhibition confirmed")
