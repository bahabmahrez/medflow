"""
Trap 20 — Digoxin + Amiodarone (direct DDI: digoxin toxicity)
Traversal: direct INTERACTS_WITH edge
Expected:
  - INTERACTS_WITH edge exists between digoxin and amiodarone
  - severity_active = 'contre_indique' or 'deconseillee'
  - clinical_effect mentions toxicity or arrhythmia
  - patient Walid Tounsi takes both (HF + AF)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

HIGH = {"contre_indique", "deconseillee", "major"}

driver = connect()

ddi = driver.execute_query(
    """
    MATCH (a:Molecule {inn: 'digoxin'})-[r:INTERACTS_WITH]-(b:Molecule {inn: 'amiodarone'})
    RETURN r.severity_active AS sev, r.clinical_effect AS effect
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'digoxin_amiodarone'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['digoxin', 'amiodarone']
    RETURN collect(m.inn) AS drugs
    """
)
driver.close()

errors = []

if not ddi.records:
    fail("no INTERACTS_WITH edge between digoxin and amiodarone")

sev    = ddi.records[0]["sev"]
effect = (ddi.records[0]["effect"] or "").lower()

if sev not in HIGH:
    errors.append(f"severity_active={sev!r} — expected deconseillee or contre_indique")

if not any(w in effect for w in ("toxic", "arrhythmia", "bradycardia", "digoxin", "concentration")):
    errors.append(f"clinical_effect does not mention toxicity or arrhythmia: {ddi.records[0]['effect']!r}")

if patient.records:
    drugs = patient.records[0]["drugs"]
    for mol in ("digoxin", "amiodarone"):
        if mol not in drugs:
            errors.append(f"patient missing drug: {mol}")
else:
    errors.append("trap patient 'digoxin_amiodarone' not found")

if errors:
    fail(" | ".join(errors))

pass_(f"severity={sev}  digoxin toxicity mentioned  patient co-prescribed confirmed")
