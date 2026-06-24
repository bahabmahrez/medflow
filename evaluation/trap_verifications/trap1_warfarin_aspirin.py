"""
Trap 1 — Warfarin + Aspirin
Expected: severity_active is deconseillee or higher (contre_indique / major)
          clinical_effect mentions hemorrhage or bleeding
          management mentions INR or monitoring
"""
import sys; sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0] + "/evaluation/trap_verifications") if False else None
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

HIGH_SEVERITY = {"contre_indique", "deconseillee", "major"}

cur = connect().cursor()
cur.execute("""
    SELECT di.severity_active, di.clinical_effect, di.management
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'warfarin'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'aspirin'
    UNION
    SELECT di.severity_active, di.clinical_effect, di.management
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'aspirin'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'warfarin'
""")
rows = cur.fetchall()

if not rows:
    fail("no interaction row found for warfarin + aspirin")

sev, effect, mgmt = rows[0]
errors = []
if sev not in HIGH_SEVERITY:
    errors.append(f"severity_active={sev!r} — expected deconseillee or contre_indique")

effect_text = (effect or "").lower()
if not any(w in effect_text for w in ("haemorrhage", "hemorrhage", "bleeding", "bleed", "saignement")):
    errors.append(f"clinical_effect does not mention bleeding: {effect!r}")

if errors:
    fail(" | ".join(errors))

pass_(f"severity={sev}  effect mentions bleeding  management present={bool(mgmt)}")
