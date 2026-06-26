"""
Trap 09 — Warfarin + Amiodarone (direct contre_indique DDI)
Traversal: direct INTERACTS_WITH edge
Expected:
  - edge exists with severity_active = 'contre_indique'
  - reason mentions CYP2C9 inhibition or INR potentiation
  - patient Yassine Gharbi takes both; INR = 3.8 (supratherapeutic)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

ddi = driver.execute_query(
    """
    MATCH (a:Molecule {inn: 'warfarin'})-[r:INTERACTS_WITH]-(b:Molecule {inn: 'amiodarone'})
    RETURN r.severity_active AS sev, r.clinical_effect AS effect, r.mechanism_type AS mech
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'warfarin_amiodarone'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['warfarin', 'amiodarone']
    RETURN collect(m.inn) AS drugs, p.inr AS inr
    """
)
driver.close()

errors = []

if not ddi.records:
    fail("no INTERACTS_WITH edge between warfarin and amiodarone")

sev = ddi.records[0]["sev"]
if sev != "contre_indique":
    errors.append(f"severity_active={sev!r} — expected 'contre_indique'")

combined = ((ddi.records[0]["effect"] or "") + " " + (ddi.records[0]["mech"] or "")).lower()
if not any(w in combined for w in ("cyp2c9", "inr", "warfarin", "anticoag", "haemorrhage", "bleeding")):
    errors.append("clinical_effect/mechanism does not mention CYP2C9 or anticoagulation potentiation")

if patient.records:
    drugs = patient.records[0]["drugs"]
    inr   = patient.records[0]["inr"]
    for mol in ("warfarin", "amiodarone"):
        if mol not in drugs:
            errors.append(f"patient missing drug: {mol}")
    if inr is not None and inr < 3.0:
        errors.append(f"patient INR={inr} — expected > 3.0 for supratherapeutic amiodarone effect")
else:
    errors.append("trap patient 'warfarin_amiodarone' not found")

if errors:
    fail(" | ".join(errors))

inr = patient.records[0]["inr"] if patient.records else "?"
pass_(f"severity=contre_indique  patient INR={inr}  warfarin+amiodarone co-prescribed")
