"""
Stress Test 2 — 6-Drug Polypharmacy

Scenario: a patient is on warfarin, aspirin, enalapril, spironolactone,
simvastatin, omeprazole. The engine must evaluate all 15 pairwise
combinations without crashing, and must find documented interactions
for the clinically significant ones.

What this tests:
  - All 15 pairs can be queried without error
  - At least 3 pairs return a documented interaction (the DB has coverage)
  - No query raises an exception

Expected: >= 3 pairs with interaction data; 0 crashes.
"""
import os, sys
from itertools import combinations
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

DRUGS = ["warfarin", "aspirin", "enalapril", "spironolactone", "simvastatin", "omeprazole"]
PAIRS = list(combinations(DRUGS, 2))   # 15 pairs

conn = connect()
cur  = conn.cursor()

found, not_found, errors_list = [], [], []

for drug_a, drug_b in PAIRS:
    try:
        cur.execute("""
            SELECT di.severity_active, di.clinical_effect
            FROM drug_interactions di
            JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = %s
            JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = %s
            UNION
            SELECT di.severity_active, di.clinical_effect
            FROM drug_interactions di
            JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = %s
            JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = %s
        """, (drug_a, drug_b, drug_b, drug_a))
        rows = cur.fetchall()
        if rows:
            found.append((drug_a, drug_b, rows[0][0]))
        else:
            not_found.append((drug_a, drug_b))
    except Exception as e:
        errors_list.append(f"{drug_a}+{drug_b}: {e}")

print(f"  Pairs evaluated:    {len(PAIRS)}")
print(f"  Interactions found: {len(found)}")
print(f"  No data:            {len(not_found)}")
print(f"  Query errors:       {len(errors_list)}")
print()
for drug_a, drug_b, sev in found:
    print(f"  FOUND  {drug_a:15s} + {drug_b:15s}  -> {sev}")
for drug_a, drug_b in not_found:
    print(f"  --     {drug_a:15s} + {drug_b:15s}  (no direct row)")

if errors_list:
    fail(f"query errors: {errors_list}")
if len(found) < 3:
    fail(f"only {len(found)} interactions found across 15 pairs — expected at least 3")

pass_(f"{len(found)}/15 pairs have documented interactions  0 query errors")
