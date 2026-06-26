"""
Trap 06 — Elderly dose context (ciprofloxacin, age > 75, creatinine adjustment)
Traversal: Patient properties + Drug node
Expected:
  - trap patient Hedi Boughanmi exists, born 1948 (age > 75)
  - patient takes ciprofloxacin
  - patient creatinine_umol_L > 100 (requires dose adjustment)
  - ciprofloxacin Drug node exists with dose_elderly property set
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

patient = driver.execute_query(
    """
    MATCH (p:Patient {trap_scenario: 'elderly_dose'})
          -[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule {inn: 'ciprofloxacin'})
    RETURN p.name AS name, p.dob AS dob, p.creatinine_umol_L AS cre
    """
)

dose = driver.execute_query(
    """
    MATCH (d:Drug)-[:BRAND_OF]->(m:Molecule {inn: 'ciprofloxacin'})
    WHERE d.dose_elderly IS NOT NULL
    RETURN d.dose_elderly AS elderly_dose
    """
)
driver.close()

errors = []

if not patient.records:
    errors.append("trap patient 'elderly_dose' not found or not taking ciprofloxacin")
else:
    rec = patient.records[0]
    dob = rec["dob"]
    cre = rec["cre"]
    # Verify approximate age > 75 from stored DOB string (born 1948)
    if dob and int(str(dob)[:4]) > 1951:
        errors.append(f"patient dob={dob!r} — expected birth year <= 1951 for age > 75")
    if cre is not None and cre <= 100:
        errors.append(f"creatinine={cre} umol/L — expected > 100 to flag dose adjustment")

if not dose.records:
    errors.append("ciprofloxacin Drug node missing dose_elderly property")

if errors:
    fail(" | ".join(errors))

cre_val = patient.records[0]["cre"] if patient.records else "?"
pass_(f"patient age > 75  creatinine={cre_val} umol/L  ciprofloxacin dose_elderly set")
