"""
Trap 5 — Fluoxetine + Tramadol (serotonin syndrome)
Expected:
  - interaction row exists with severity deconseillee or higher
  - clinical_effect or mechanism mentions serotonin
  - CYP2D6 pathway confirms fluoxetine inhibits tramadol activation
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

HIGH_SEVERITY = {"contre_indique", "deconseillee", "major"}

cur = connect().cursor()

# Check 1: drug interaction row
cur.execute("""
    SELECT di.severity_active, di.clinical_effect, di.mechanism_type
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'fluoxetine'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'tramadol'
    UNION
    SELECT di.severity_active, di.clinical_effect, di.mechanism_type
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'tramadol'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'fluoxetine'
""")
rows = cur.fetchall()

if not rows:
    fail("no interaction row found for fluoxetine + tramadol")

sev, effect, mechanism = rows[0]
errors = []

if sev not in HIGH_SEVERITY:
    errors.append(f"severity_active={sev!r} — expected deconseillee or contre_indique")

combined = ((effect or "") + " " + (mechanism or "")).lower()
if "serotonin" not in combined:
    errors.append(f"clinical_effect/mechanism does not mention serotonin: {effect!r}")

# Check 2: CYP2D6 pathway — fluoxetine inhibits, tramadol is substrate
cur.execute("""
    SELECT m.inn, cr.relationship, cr.strength
    FROM cyp_relationships cr
    JOIN molecules m ON m.id = cr.molecule_id
    WHERE m.inn IN ('fluoxetine', 'tramadol') AND cr.enzyme = 'CYP2D6'
""")
cyp = {(r[0], r[1]): r[2] for r in cur.fetchall()}

if ("fluoxetine", "INHIBITOR") not in cyp:
    errors.append("missing: fluoxetine CYP2D6 INHIBITOR")
if ("tramadol", "SUBSTRATE") not in cyp:
    errors.append("missing: tramadol CYP2D6 SUBSTRATE")

if errors:
    fail(" | ".join(errors))

pass_(f"severity={sev}  serotonin mentioned  CYP2D6 pathway confirmed")
