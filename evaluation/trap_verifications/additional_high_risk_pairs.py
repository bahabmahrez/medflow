"""
Additional high-risk pair checks — 5 critical contre_indique / deconseillee pairs
that must be in the DB before Week 2 ends.

Pairs checked:
  warfarin + amiodarone       → contre_indique
  tacrolimus + fluconazole    → contre_indique
  rifampicin + warfarin       → contre_indique
  methotrexate + ibuprofen    → deconseillee or major
  allopurinol + azathioprine  → contre_indique
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect

HIGH = {"contre_indique", "deconseillee", "major"}
CONTRE = {"contre_indique"}

conn = connect()
cur  = conn.cursor()

PAIRS = [
    ("warfarin",     "amiodarone",  CONTRE, "warfarin + amiodarone"),
    ("tacrolimus",   "fluconazole", CONTRE, "tacrolimus + fluconazole"),
    ("rifampicin",   "warfarin",    CONTRE, "rifampicin + warfarin"),
    ("methotrexate", "ibuprofen",   HIGH,   "methotrexate + ibuprofen"),
    ("allopurinol",  "azathioprine",CONTRE, "allopurinol + azathioprine"),
]

results = []
for drug_a, drug_b, expected_sevs, label in PAIRS:
    cur.execute("""
        SELECT di.severity_active
        FROM drug_interactions di
        JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = %s
        JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = %s
        UNION
        SELECT di.severity_active
        FROM drug_interactions di
        JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = %s
        JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = %s
    """, (drug_a, drug_b, drug_b, drug_a))
    rows = cur.fetchall()

    if not rows:
        results.append((label, "FAIL", "no interaction row found"))
    else:
        sev = rows[0][0]
        if sev in expected_sevs:
            results.append((label, "PASS", sev))
        else:
            expected_str = "/".join(sorted(expected_sevs))
            results.append((label, "FAIL", f"severity={sev!r} expected {expected_str}"))

print("\nAdditional high-risk pair checks:")
print("-" * 65)
all_pass = True
for label, status, detail in results:
    print(f"  {status}  {label:35s}  {detail}")
    if status == "FAIL":
        all_pass = False

print()
if all_pass:
    print("ALL PASS")
    raise SystemExit(0)
else:
    print("SOME CHECKS FAILED")
    raise SystemExit(1)
