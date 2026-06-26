"""
Trap 12 — Tacrolimus + Fluconazole (narrow TI + CYP3A4 strong inhibitor)
Traversal: direct INTERACTS_WITH edge + CYP3A4 path
Expected:
  - INTERACTS_WITH edge with severity_active = 'contre_indique'
  - tacrolimus -[:SUBSTRATE_OF]-> CYP3A4 <-[:INHIBITS {strength:'strong'}]- fluconazole
  - patient Sarra Fennira takes both (post-transplant + antifungal)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

ddi = driver.execute_query(
    """
    MATCH (a:Molecule {inn: 'tacrolimus'})-[r:INTERACTS_WITH]-(b:Molecule {inn: 'fluconazole'})
    RETURN r.severity_active AS sev, r.clinical_effect AS effect
    """
)

cyp_path = driver.execute_query(
    """
    MATCH (tac:Molecule {inn: 'tacrolimus'})-[:SUBSTRATE_OF]->(cyp:CYPEnzyme {name: 'CYP3A4'})
          <-[r:INHIBITS]-(flu:Molecule {inn: 'fluconazole'})
    RETURN r.strength AS strength
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'tacrolimus_fluconazole'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['tacrolimus', 'fluconazole']
    RETURN collect(m.inn) AS drugs
    """
)
driver.close()

errors = []

if not ddi.records:
    fail("no INTERACTS_WITH edge between tacrolimus and fluconazole")

sev = ddi.records[0]["sev"]
if sev != "contre_indique":
    errors.append(f"severity_active={sev!r} — expected 'contre_indique' (narrow TI drug)")

if not cyp_path.records:
    errors.append("no CYP3A4 path: tacrolimus SUBSTRATE_OF → CYP3A4 ← fluconazole INHIBITS")
else:
    strength = cyp_path.records[0]["strength"]
    if strength != "strong":
        errors.append(f"fluconazole CYP3A4 inhibitor strength={strength!r} — expected 'strong'")

if patient.records:
    drugs = patient.records[0]["drugs"]
    for mol in ("tacrolimus", "fluconazole"):
        if mol not in drugs:
            errors.append(f"patient missing drug: {mol}")
else:
    errors.append("trap patient 'tacrolimus_fluconazole' not found")

if errors:
    fail(" | ".join(errors))

pass_("severity=contre_indique  tacrolimus→CYP3A4(strong)←fluconazole  narrow TI confirmed")
