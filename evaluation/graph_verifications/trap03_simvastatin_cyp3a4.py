"""
Trap 03 — Simvastatin + Clarithromycin via CYP3A4 (2-hop inhibition)
Traversal: 2-hop CYP enzyme path
Expected:
  - simvastatin -[:SUBSTRATE_OF]-> CYP3A4
  - clarithromycin -[:INHIBITS {strength:'strong'}]-> CYP3A4
  - patient Nabil Chaabane takes both drugs simultaneously
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

# Check 1: 2-hop CYP3A4 path exists in knowledge graph
path = driver.execute_query(
    """
    MATCH (sim:Molecule {inn: 'simvastatin'})-[:SUBSTRATE_OF]->(cyp:CYPEnzyme {name: 'CYP3A4'})
          <-[r:INHIBITS]-(cla:Molecule {inn: 'clarithromycin'})
    RETURN cyp.name AS cyp, r.strength AS strength
    """
)

# Check 2: patient carries both drugs
patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'simvastatin_cyp3a4'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['simvastatin', 'clarithromycin']
    RETURN collect(m.inn) AS drugs
    """
)
driver.close()

errors = []

if not path.records:
    errors.append("no 2-hop CYP3A4 path: simvastatin SUBSTRATE_OF → CYP3A4 ← clarithromycin INHIBITS")
else:
    strength = path.records[0]["strength"]
    if strength != "strong":
        errors.append(f"clarithromycin CYP3A4 inhibitor strength={strength!r} — expected 'strong'")

if patient.records:
    drugs = patient.records[0]["drugs"]
    for mol in ("simvastatin", "clarithromycin"):
        if mol not in drugs:
            errors.append(f"patient trap_scenario='simvastatin_cyp3a4' missing drug: {mol}")

if errors:
    fail(" | ".join(errors))

pass_("simvastatin → CYP3A4(strong) ← clarithromycin  2-hop path + patient verified")
