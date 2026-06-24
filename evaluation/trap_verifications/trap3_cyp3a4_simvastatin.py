"""
Trap 3 — Simvastatin + Clarithromycin (CYP3A4 inhibition → rhabdomyolysis)
Expected:
  - simvastatin  CYP3A4  SUBSTRATE   (any strength)
  - clarithromycin  CYP3A4  INHIBITOR  strength=strong
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

cur = connect().cursor()
cur.execute("""
    SELECT m.inn, cr.relationship, cr.strength
    FROM cyp_relationships cr
    JOIN molecules m ON m.id = cr.molecule_id
    WHERE m.inn IN ('simvastatin', 'clarithromycin')
      AND cr.enzyme = 'CYP3A4'
""")
rows = {(r[0], r[1]): r[2] for r in cur.fetchall()}

errors = []
if ("simvastatin", "SUBSTRATE") not in rows:
    errors.append("missing: simvastatin CYP3A4 SUBSTRATE")

if ("clarithromycin", "INHIBITOR") not in rows:
    errors.append("missing: clarithromycin CYP3A4 INHIBITOR")
elif rows[("clarithromycin", "INHIBITOR")] != "strong":
    errors.append(f"clarithromycin CYP3A4 INHIBITOR strength={rows[('clarithromycin','INHIBITOR')]!r} — expected 'strong'")

if errors:
    fail(" | ".join(errors))

pass_("simvastatin=CYP3A4 SUBSTRATE  clarithromycin=CYP3A4 INHIBITOR strong")
