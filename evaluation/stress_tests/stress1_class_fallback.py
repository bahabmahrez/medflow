"""
Stress Test 1 — Class-Level Interaction Fallback

Scenario: naproxen + warfarin may not have a direct drug_interactions row,
but the NSAID class has a class_interactions edge with Vitamin K Antagonists.
The engine should surface the risk via the class graph even with no direct pair.

What this tests: class_interactions is populated and queryable as a fallback
when direct drug_interactions coverage is incomplete.

Expected: at least one class interaction row is found connecting an NSAID
          to a Vitamin K Antagonist (or anticoagulant class), with severity
          deconseillee or contre_indique.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

HIGH = {"contre_indique", "deconseillee"}

cur = connect().cursor()

# Step 1: check there IS a direct interaction (most setups will have it)
cur.execute("""
    SELECT di.severity_active
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'naproxen'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'warfarin'
    UNION
    SELECT di.severity_active
    FROM drug_interactions di
    JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'warfarin'
    JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'naproxen'
""")
direct = cur.fetchall()

# Step 2: class-level fallback query
# Find class interactions connecting naproxen's class to warfarin's class
cur.execute("""
    SELECT ca.class_name, cb.class_name, ci.severity
    FROM class_interactions ci
    JOIN drug_classes ca ON ca.id = ci.class_a_id
    JOIN drug_classes cb ON cb.id = ci.class_b_id
    JOIN drug_class_members dcm_a ON dcm_a.drug_class_id = ci.class_a_id
    JOIN drug_class_members dcm_b ON dcm_b.drug_class_id = ci.class_b_id
    JOIN molecules ma ON ma.id = dcm_a.molecule_id AND ma.inn = 'naproxen'
    JOIN molecules mb ON mb.id = dcm_b.molecule_id AND mb.inn = 'warfarin'
""")
class_hits = cur.fetchall()

if not class_hits:
    fail(
        "no class_interactions row connects naproxen's class to warfarin's class — "
        "class fallback engine would miss this interaction"
    )

errors = []
high_class = [r for r in class_hits if r[2] in HIGH]
if not high_class:
    errors.append(
        f"class interaction exists but severity too low: "
        f"{[(r[0], r[1], r[2]) for r in class_hits]}"
    )

if errors:
    fail(" | ".join(errors))

direct_sev = direct[0][0] if direct else "no direct row"
class_sev  = high_class[0][2]
class_pair = f"{high_class[0][0]} + {high_class[0][1]}"
pass_(
    f"direct={direct_sev}  "
    f"class fallback={class_sev} via [{class_pair}]  "
    f"({len(class_hits)} class edge(s) found)"
)
