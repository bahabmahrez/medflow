"""
Trap 10 — Rifampicin (CYP inducer) + Warfarin (subtherapeutic anticoagulation)
Traversal: 2-hop CYP2C9 induction path
Expected:
  - rifampicin -[:INDUCES]-> CYP2C9
  - warfarin -[:SUBSTRATE_OF]-> CYP2C9
  - induction 2-hop path: rifampicin → CYP2C9 ← warfarin
  - patient Hajer Belhaj has INR = 1.3 (subtherapeutic due to induction)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

path = driver.execute_query(
    """
    MATCH (rif:Molecule {inn: 'rifampicin'})-[:INDUCES]->(cyp:CYPEnzyme {name: 'CYP2C9'})
          <-[:SUBSTRATE_OF]-(war:Molecule {inn: 'warfarin'})
    RETURN rif.inn AS inducer, cyp.name AS cyp, war.inn AS substrate
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'rifampicin_inducer'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['warfarin', 'rifampicin']
    RETURN collect(m.inn) AS drugs, p.inr AS inr
    """
)
driver.close()

errors = []

if not path.records:
    errors.append("no CYP2C9 induction path: rifampicin INDUCES → CYP2C9 ← warfarin SUBSTRATE_OF")

if patient.records:
    drugs = patient.records[0]["drugs"]
    inr   = patient.records[0]["inr"]
    for mol in ("warfarin", "rifampicin"):
        if mol not in drugs:
            errors.append(f"patient missing drug: {mol}")
    if inr is not None and inr > 2.0:
        errors.append(f"patient INR={inr} — expected < 2.0 (subtherapeutic due to CYP induction)")
else:
    errors.append("trap patient 'rifampicin_inducer' not found")

if errors:
    fail(" | ".join(errors))

inr = patient.records[0]["inr"] if patient.records else "?"
pass_(f"rifampicin INDUCES CYP2C9 ← warfarin SUBSTRATE_OF  patient INR={inr} (subtherapeutic)")
