"""
Trap 07 — Warfarin + Fluconazole via CYP2C9 (strong inhibitor → INR spike)
Traversal: 2-hop CYP2C9 path
Expected:
  - warfarin -[:SUBSTRATE_OF]-> CYP2C9
  - fluconazole -[:INHIBITS {strength:'strong'}]-> CYP2C9
  - patient Mariem Ayari takes both; INR elevated (2.1 rising)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

path = driver.execute_query(
    """
    MATCH (war:Molecule {inn: 'warfarin'})-[r1:SUBSTRATE_OF]->(cyp:CYPEnzyme {name: 'CYP2C9'})
          <-[r2:INHIBITS]-(flu:Molecule {inn: 'fluconazole'})
    RETURN cyp.name AS cyp, r2.strength AS strength
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'cyp2c9_overload'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['warfarin', 'fluconazole']
    RETURN collect(m.inn) AS drugs, p.inr AS inr
    """
)
driver.close()

errors = []

if not path.records:
    errors.append("no CYP2C9 path: warfarin SUBSTRATE_OF → CYP2C9 ← fluconazole INHIBITS")
else:
    strength = path.records[0]["strength"]
    if strength != "strong":
        errors.append(f"fluconazole CYP2C9 inhibitor strength={strength!r} — expected 'strong'")

if patient.records:
    drugs = patient.records[0]["drugs"]
    for mol in ("warfarin", "fluconazole"):
        if mol not in drugs:
            errors.append(f"patient trap_scenario='cyp2c9_overload' missing drug: {mol}")

if errors:
    fail(" | ".join(errors))

inr = patient.records[0]["inr"] if patient.records else "?"
pass_(f"warfarin → CYP2C9(strong) ← fluconazole  patient INR={inr}")
