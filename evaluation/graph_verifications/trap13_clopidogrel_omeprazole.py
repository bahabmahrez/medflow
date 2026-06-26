"""
Trap 13 — Clopidogrel + Omeprazole via CYP2C19 (loss of antiplatelet effect)
Traversal: 2-hop CYP2C19 path
Expected:
  - clopidogrel -[:SUBSTRATE_OF]-> CYP2C19
  - omeprazole -[:INHIBITS]-> CYP2C19
  - patient Ons Haddad takes both (ACS patient on antiplatelet + PPI)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

path = driver.execute_query(
    """
    MATCH (clop:Molecule {inn: 'clopidogrel'})-[:SUBSTRATE_OF]->(cyp:CYPEnzyme {name: 'CYP2C19'})
          <-[:INHIBITS]-(ome:Molecule {inn: 'omeprazole'})
    RETURN clop.inn AS substrate, cyp.name AS cyp, ome.inn AS inhibitor
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'clopidogrel_omeprazole'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['clopidogrel', 'omeprazole']
    RETURN collect(m.inn) AS drugs
    """
)
driver.close()

errors = []

if not path.records:
    errors.append("no CYP2C19 path: clopidogrel SUBSTRATE_OF -> CYP2C19 <- omeprazole INHIBITS")

if patient.records:
    drugs = patient.records[0]["drugs"]
    for mol in ("clopidogrel", "omeprazole"):
        if mol not in drugs:
            errors.append(f"patient missing drug: {mol}")
else:
    errors.append("trap patient 'clopidogrel_omeprazole' not found")

if errors:
    fail(" | ".join(errors))

pass_("clopidogrel->CYP2C19<-omeprazole  2-hop path  ACS patient co-prescribed")
