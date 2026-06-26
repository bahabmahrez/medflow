"""
Trap 05 — Fluoxetine + Tramadol (serotonin syndrome)
Traversal: direct INTERACTS_WITH edge + shared MolecularTarget (SERT)
Expected:
  - INTERACTS_WITH edge with severity deconseillee or higher
  - clinical_effect mentions serotonin
  - both drugs TARGET serotonin transporter (SERT)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

HIGH = {"contre_indique", "deconseillee", "major"}

driver = connect()

ddi = driver.execute_query(
    """
    MATCH (a:Molecule {inn: 'fluoxetine'})-[r:INTERACTS_WITH]-(b:Molecule {inn: 'tramadol'})
    RETURN r.severity_active AS sev, r.clinical_effect AS effect
    """
)

sert = driver.execute_query(
    """
    MATCH (m:Molecule)-[:TARGETS]->(t:MolecularTarget)
    WHERE m.inn IN ['fluoxetine', 'tramadol']
      AND toLower(t.target_name) CONTAINS 'serotonin transporter'
    RETURN m.inn AS mol, t.target_name AS target
    """
)
driver.close()

errors = []

if not ddi.records:
    fail("no INTERACTS_WITH edge between fluoxetine and tramadol")

sev    = ddi.records[0]["sev"]
effect = (ddi.records[0]["effect"] or "").lower()

if sev not in HIGH:
    errors.append(f"severity_active={sev!r} — expected deconseillee or contre_indique")

if "serotonin" not in effect:
    errors.append(f"clinical_effect does not mention serotonin: {ddi.records[0]['effect']!r}")

sert_mols = {r["mol"] for r in sert.records}
for mol in ("fluoxetine", "tramadol"):
    if mol not in sert_mols:
        errors.append(f"{mol} missing TARGETS serotonin transporter")

if errors:
    fail(" | ".join(errors))

pass_(f"severity={sev}  serotonin mentioned  both drugs target SERT")
