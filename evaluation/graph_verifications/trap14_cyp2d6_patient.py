"""
Trap 14 — CYP2D6 patient-centric traversal (fluoxetine inhibits tramadol activation)
Traversal: Patient -> Drug -> Molecule -> CYP2D6 <- Molecule <- Drug <- Patient
Expected:
  - starting from the patient node, Cypher finds the CYP2D6 conflict automatically
  - fluoxetine inhibits CYP2D6 which activates tramadol (prodrug -> active M1)
  - patient Zied Barka co-prescribed both
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

# Patient-centric traversal: find CYP2D6 conflicts for this patient
conflict = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'tramadol_fluoxetine_cyp2d6'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(sub:Molecule)
          -[:SUBSTRATE_OF]->(cyp:CYPEnzyme {name: 'CYP2D6'})
          <-[:INHIBITS]-(inh:Molecule)
          <-[:BRAND_OF]-(:Drug)<-[:TAKES]-(p)
    RETURN p.name AS patient, sub.inn AS substrate, cyp.name AS cyp, inh.inn AS inhibitor
    """
)

# Also verify individual CYP2D6 relationships exist in knowledge graph
cyp_check = driver.execute_query(
    """
    MATCH (flu:Molecule {inn: 'fluoxetine'})-[:INHIBITS]->(cyp:CYPEnzyme {name: 'CYP2D6'})
          <-[:SUBSTRATE_OF]-(tra:Molecule {inn: 'tramadol'})
    RETURN flu.inn AS inhibitor, cyp.name AS cyp, tra.inn AS substrate
    """
)
driver.close()

errors = []

if not cyp_check.records:
    errors.append("fluoxetine INHIBITS CYP2D6 or tramadol SUBSTRATE_OF CYP2D6 edges missing")

if not conflict.records:
    errors.append(
        "patient-centric CYP2D6 traversal found no conflict — "
        "patient not taking both drugs or CYP2D6 edges absent"
    )
else:
    rec = conflict.records[0]
    if rec["substrate"] != "tramadol":
        errors.append(f"expected substrate=tramadol, got {rec['substrate']!r}")
    if rec["inhibitor"] != "fluoxetine":
        errors.append(f"expected inhibitor=fluoxetine, got {rec['inhibitor']!r}")

if errors:
    fail(" | ".join(errors))

rec = conflict.records[0]
pass_(
    f"patient={rec['patient']}  {rec['substrate']}->{rec['cyp']}<-{rec['inhibitor']}  "
    "patient-centric CYP2D6 traversal succeeded"
)
