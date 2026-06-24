"""
Trap 7 — Warfarin + Fluconazole (CYP2C9 overload → bleeding)
Expected:
  - warfarin   CYP2C9  SUBSTRATE  (any strength)
  - fluconazole CYP2C9  INHIBITOR  strength = strong or moderate
  - interaction row exists with high severity
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

HIGH_SEVERITY = {"contre_indique", "deconseillee", "major"}

cur = connect().cursor()

# Check 1: CYP2C9 pathway
cur.execute("""
    SELECT m.inn, cr.relationship, cr.strength
    FROM cyp_relationships cr
    JOIN molecules m ON m.id = cr.molecule_id
    WHERE m.inn IN ('warfarin', 'fluconazole') AND cr.enzyme = 'CYP2C9'
""")
cyp = {(r[0], r[1]): r[2] for r in cur.fetchall()}

errors = []
if ("warfarin", "SUBSTRATE") not in cyp:
    errors.append("missing: warfarin CYP2C9 SUBSTRATE")

if ("fluconazole", "INHIBITOR") not in cyp:
    errors.append("missing: fluconazole CYP2C9 INHIBITOR")
else:
    strength = cyp[("fluconazole", "INHIBITOR")]
    if strength not in ("strong", "moderate"):
        errors.append(f"fluconazole CYP2C9 INHIBITOR strength={strength!r} — expected strong or moderate")

# Check 2: drug interaction row
cur.execute("""
    SELECT di.severity_active
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'warfarin'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'fluconazole'
    UNION
    SELECT di.severity_active
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'fluconazole'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'warfarin'
""")
inter = cur.fetchall()
if not inter:
    errors.append("no drug_interactions row for warfarin + fluconazole")
elif inter[0][0] not in HIGH_SEVERITY:
    errors.append(f"interaction severity={inter[0][0]!r} — expected deconseillee or higher")

if errors:
    fail(" | ".join(errors))

pass_(f"warfarin=CYP2C9 SUBSTRATE  fluconazole=CYP2C9 INHIBITOR {cyp.get(('fluconazole','INHIBITOR'))}  interaction severity={inter[0][0]}")
