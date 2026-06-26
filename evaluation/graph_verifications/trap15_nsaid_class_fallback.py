"""
Trap 15 — NSAID + VKA class-level interaction fallback
Traversal: DrugClass -[:CLASS_INTERACTS_WITH]-> DrugClass
Expected:
  - CLASS_INTERACTS_WITH edge exists between NSAID class and VKA class
  - ibuprofen is MEMBER_OF the NSAID class
  - warfarin is MEMBER_OF the VKA/anticoagulant class
  - patient Mounira Selmi has warfarin + ibuprofen + prednisolone (3-way)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

class_interaction = driver.execute_query(
    """
    MATCH (nsaid:DrugClass)-[r:CLASS_INTERACTS_WITH]-(vka:DrugClass)
    WHERE (toLower(nsaid.class_name) CONTAINS 'nsaid'
        OR toLower(nsaid.class_name) CONTAINS 'anti-inflammatory'
        OR nsaid.atc_code STARTS WITH 'M01')
      AND (toLower(vka.class_name) CONTAINS 'anticoagulant'
        OR toLower(vka.class_name) CONTAINS 'vka'
        OR vka.atc_code STARTS WITH 'B01')
    RETURN nsaid.class_name AS nsaid_class, vka.class_name AS vka_class, r.severity AS sev
    LIMIT 1
    """
)

ibuprofen_class = driver.execute_query(
    """
    MATCH (m:Molecule {inn: 'ibuprofen'})-[:MEMBER_OF]->(c:DrugClass)
    RETURN c.class_name AS class_name, c.atc_code AS atc
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'nsaid_anticoagulant_steroid'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['warfarin', 'ibuprofen', 'prednisolone']
    RETURN collect(m.inn) AS drugs
    """
)
driver.close()

errors = []

if not class_interaction.records:
    errors.append("no CLASS_INTERACTS_WITH edge between NSAID class and VKA/anticoagulant class")

if not ibuprofen_class.records:
    errors.append("ibuprofen has no MEMBER_OF edge to a DrugClass")

if patient.records:
    drugs = patient.records[0]["drugs"]
    for mol in ("warfarin", "ibuprofen", "prednisolone"):
        if mol not in drugs:
            errors.append(f"patient missing drug: {mol}")
else:
    errors.append("trap patient 'nsaid_anticoagulant_steroid' not found")

if errors:
    fail(" | ".join(errors))

ci = class_interaction.records[0]
pass_(
    f"CLASS_INTERACTS_WITH: {ci['nsaid_class']} ↔ {ci['vka_class']}  "
    "patient on warfarin+ibuprofen+prednisolone"
)
