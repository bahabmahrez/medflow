"""
Trap 01 — Warfarin + Aspirin (direct DDI, bleeding risk)
Traversal: direct INTERACTS_WITH edge
Expected:
  - edge exists with severity_active in {contre_indique, deconseillee, major}
  - clinical_effect mentions bleeding/haemorrhage
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

HIGH = {"contre_indique", "deconseillee", "major"}

driver = connect()
result = driver.execute_query(
    """
    MATCH (a:Molecule {inn: 'warfarin'})-[r:INTERACTS_WITH]-(b:Molecule {inn: 'aspirin'})
    RETURN r.severity_active AS sev, r.clinical_effect AS effect
    """
)
driver.close()

if not result.records:
    fail("no INTERACTS_WITH edge between warfarin and aspirin")

rec    = result.records[0]
sev    = rec["sev"]
effect = (rec["effect"] or "").lower()
errors = []

if sev not in HIGH:
    errors.append(f"severity_active={sev!r} — expected deconseillee or contre_indique")

if not any(w in effect for w in ("haemorrhage", "hemorrhage", "bleeding", "bleed", "saignement")):
    errors.append(f"clinical_effect does not mention bleeding: {rec['effect']!r}")

if errors:
    fail(" | ".join(errors))

pass_(f"severity={sev}  bleeding mentioned in clinical_effect")
