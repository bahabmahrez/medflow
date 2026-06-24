"""
Stress Test 3 — CYP Competition Without a Direct Pair

Scenario: omeprazole + clopidogrel have no high-severity direct drug_interaction
row in many DBs (the interaction is CYP2C19 mediated — omeprazole inhibits
CYP2C19 which activates clopidogrel). The engine should detect this via the
CYP graph:
  omeprazole  CYP2C19 INHIBITOR
  clopidogrel CYP2C19 SUBSTRATE

What this tests: CYP pathway data is complete enough to flag indirect
pharmacokinetic competition when the direct row may not exist.

Expected:
  - omeprazole listed as CYP2C19 INHIBITOR
  - clopidogrel listed as CYP2C19 SUBSTRATE
  - Any severity in direct drug_interactions row is reported (informational)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

cur = connect().cursor()

cur.execute("""
    SELECT m.inn, cr.relationship, cr.strength
    FROM cyp_relationships cr
    JOIN molecules m ON m.id = cr.molecule_id
    WHERE m.inn IN ('omeprazole', 'clopidogrel')
      AND cr.enzyme = 'CYP2C19'
""")
cyp = {(r[0], r[1]): r[2] for r in cur.fetchall()}

errors = []
if ("omeprazole", "INHIBITOR") not in cyp:
    errors.append("missing: omeprazole CYP2C19 INHIBITOR")
if ("clopidogrel", "SUBSTRATE") not in cyp:
    errors.append("missing: clopidogrel CYP2C19 SUBSTRATE")

# Report direct row but don't fail if absent — the CYP graph is the point
cur.execute("""
    SELECT di.severity_active
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'omeprazole'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'clopidogrel'
    UNION
    SELECT di.severity_active
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'clopidogrel'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'omeprazole'
""")
direct = cur.fetchone()
direct_sev = direct[0] if direct else "no direct row (CYP graph is primary signal)"

if errors:
    fail(" | ".join(errors))

omep_str  = cyp.get(("omeprazole",  "INHIBITOR"), "?")
clop_str  = cyp.get(("clopidogrel", "SUBSTRATE"), "?")
pass_(
    f"omeprazole=CYP2C19 INHIBITOR {omep_str}  "
    f"clopidogrel=CYP2C19 SUBSTRATE {clop_str}  "
    f"direct row={direct_sev}"
)
