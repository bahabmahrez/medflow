"""
Trap 04 — Penicillin allergy -> cephalosporin cross-reactivity (2-hop allergy path)
Traversal: AllergyGroup -[:CROSS_REACTS_WITH]-> AllergyGroup
Expected:
  - penicillin and cephalosporin AllergyGroup nodes exist
  - bidirectional CROSS_REACTS_WITH edge exists between them
  - amoxicillin Drug node belongs to penicillin AllergyGroup
  - trap patient is allergic to penicillin
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

cross = driver.execute_query(
    """
    MATCH (pen:AllergyGroup {name: 'penicillin'})-[:CROSS_REACTS_WITH]->(ceph:AllergyGroup {name: 'cephalosporin'})
    RETURN pen.name AS pen, ceph.name AS ceph
    """
)

membership = driver.execute_query(
    """
    MATCH (:Drug)-[:BELONGS_TO_ALLERGY_GROUP]->(ag:AllergyGroup {name: 'penicillin'})
    MATCH (:Molecule {inn: 'amoxicillin'})<-[:BRAND_OF]-(:Drug)-[:BELONGS_TO_ALLERGY_GROUP]->(ag)
    RETURN ag.name AS group
    """
)

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'penicillin_allergy'})-[r:ALLERGIC_TO]->(ag:AllergyGroup {name: 'penicillin'})
    RETURN r.reaction_type AS reaction
    """
)
driver.close()

errors = []

if not cross.records:
    errors.append("no CROSS_REACTS_WITH edge: penicillin -> cephalosporin")

if not membership.records:
    errors.append("amoxicillin drug not linked to penicillin AllergyGroup via BELONGS_TO_ALLERGY_GROUP")

if not patient.records:
    errors.append("trap patient 'penicillin_allergy' not found or not ALLERGIC_TO penicillin")
else:
    reaction = patient.records[0]["reaction"]
    if reaction != "anaphylaxis":
        errors.append(f"reaction_type={reaction!r} — expected 'anaphylaxis'")

if errors:
    fail(" | ".join(errors))

pass_("penicillin <-> cephalosporin CROSS_REACTS_WITH  amoxicillin membership  patient allergy verified")
