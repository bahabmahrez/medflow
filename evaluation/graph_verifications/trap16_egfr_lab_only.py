"""
Trap 16 — Lab-only contraindication: high creatinine with no CKD ICD code
Traversal: Patient.creatinine_umol_L property + CONTRAINDICATED_FOR edge
Expected:
  - patient Tahar Khiari has creatinine_umol_L > 150 (implies eGFR < 30)
  - patient has NO HAS_CONDITION edge to a CKD DiseaseConcept (no ICD N18/GB6x)
  - metformin CONTRAINDICATED_FOR renal impairment edge exists in knowledge graph
  - the risk is detectable only via lab property, NOT via diagnosis code
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

# Patient has elevated creatinine and takes metformin
lab_risk = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'metformin_egfr_lab_only'})
    WHERE p.creatinine_umol_L > 150
    MATCH (p)-[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule {inn: 'metformin'})
    RETURN p.name AS name, p.creatinine_umol_L AS cre
    """
)

# Confirm no CKD diagnosis code
ckd_dx = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'metformin_egfr_lab_only'})
          -[:HAS_CONDITION]->(dc:DiseaseConcept)
    WHERE dc.icd11_code STARTS WITH 'N18'
       OR dc.icd11_code STARTS WITH 'GB6'
       OR toLower(dc.condition_name) CONTAINS 'kidney'
       OR toLower(dc.condition_name) CONTAINS 'renal'
    RETURN dc.icd11_code AS icd
    """
)

# Confirm the contraindication edge exists in knowledge graph
ci_edge = driver.execute_query(
    """
    MATCH (m:Molecule {inn: 'metformin'})-[r:CONTRAINDICATED_FOR]->(dc:DiseaseConcept)
    WHERE dc.icd11_code STARTS WITH 'N18'
       OR dc.icd11_code STARTS WITH 'GB6'
       OR toLower(dc.condition_name) CONTAINS 'renal'
    RETURN r.severity AS sev
    """
)
driver.close()

errors = []

if not lab_risk.records:
    errors.append(
        "patient 'metformin_egfr_lab_only' not found, creatinine <= 150 umol/L, "
        "or not taking metformin"
    )

if ckd_dx.records:
    errors.append(
        f"patient has CKD diagnosis code {ckd_dx.records[0]['icd']!r} — "
        "trap should have NO CKD ICD code (lab-only trigger)"
    )

if not ci_edge.records:
    errors.append("metformin CONTRAINDICATED_FOR renal impairment edge missing from knowledge graph")

if errors:
    fail(" | ".join(errors))

cre = lab_risk.records[0]["cre"] if lab_risk.records else "?"
pass_(
    f"creatinine={cre} umol/L  no CKD ICD code  "
    "metformin contraindication detectable via lab property only"
)
