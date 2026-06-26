"""
Trap 17 — Two SSRIs simultaneously (therapeutic duplication via DrugClass)
Traversal: Patient → Drug → Molecule → MEMBER_OF → DrugClass (collect 2+)
Expected:
  - patient Soumaya Hamdi has both fluoxetine and sertraline
  - both are MEMBER_OF an SSRI DrugClass
  - collecting class members from patient medications finds >= 2 SSRIs
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

# Check both drugs are in same DrugClass (SSRI)
ssri_class = driver.execute_query(
    """
    MATCH (m:Molecule)-[:MEMBER_OF]->(c:DrugClass)
    WHERE m.inn IN ['fluoxetine', 'sertraline']
      AND (toLower(c.class_name) CONTAINS 'serotonin reuptake'
        OR toLower(c.class_name) CONTAINS 'ssri'
        OR toLower(c.class_name) CONTAINS 'antidepressant')
    RETURN m.inn AS mol, c.class_name AS class_name
    """
)

# Patient-centric: find all DrugClasses where this patient has >= 2 drugs
dup_check = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'two_ssri'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
          -[:MEMBER_OF]->(c:DrugClass)
    WITH p, c, collect(m.inn) AS mols
    WHERE size(mols) >= 2
    RETURN p.name AS patient, c.class_name AS class_name, mols
    """
)

patient_drugs = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'two_ssri'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
    WHERE m.inn IN ['fluoxetine', 'sertraline']
    RETURN collect(m.inn) AS drugs
    """
)
driver.close()

errors = []

ssri_mols = {r["mol"] for r in ssri_class.records}
for mol in ("fluoxetine", "sertraline"):
    if mol not in ssri_mols:
        errors.append(f"{mol} not found as MEMBER_OF an SSRI DrugClass")

if patient_drugs.records:
    drugs = patient_drugs.records[0]["drugs"]
    for mol in ("fluoxetine", "sertraline"):
        if mol not in drugs:
            errors.append(f"patient missing drug: {mol}")
else:
    errors.append("trap patient 'two_ssri' not found or missing fluoxetine/sertraline")

if not dup_check.records:
    errors.append(
        "patient-centric duplication query found no shared DrugClass with >= 2 drugs — "
        "MEMBER_OF edges or DrugClass grouping may be missing"
    )

if errors:
    fail(" | ".join(errors))

rec = dup_check.records[0]
pass_(
    f"patient={rec['patient']}  class='{rec['class_name']}'  "
    f"duplicated_mols={sorted(rec['mols'])}"
)
