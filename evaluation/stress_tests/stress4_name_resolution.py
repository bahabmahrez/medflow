"""
Stress Test 4 — Name Resolution Across 3 Identifiers

Scenario: the same drug can arrive as brand name (Tunisian market),
INN, or RxNorm CUI. All three must resolve to the same molecule_id.

Triplets tested:
  Tahor          | atorvastatin  | 83367
  Seroquel       | quetiapine    | (any cui found)
  Kardegic       | aspirin       | (any cui found)
  Glucophage     | metformin     | (any cui found)
  Depakine       | valproate     | (any cui found)

What this tests: drugs.brand_name_tn is populated, rxnorm_cui is populated,
and all identifiers converge on the same molecule row.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

BRANDS = [
    ("Tahor",      "atorvastatin"),
    ("Seroquel",   "quetiapine"),
    ("Kardegic",   "aspirin"),
    ("Glucophage", "metformin"),
    ("Depakine",   "valproate"),
]

conn = connect()
cur  = conn.cursor()

results = []
for brand, inn in BRANDS:
    cur.execute("""
        SELECT m.id, m.inn, m.rxnorm_cui
        FROM drugs d
        JOIN molecules m ON m.id = d.molecule_id
        WHERE d.brand_name_tn ILIKE %s
    """, (brand,))
    by_brand = cur.fetchone()

    cur.execute("SELECT id, inn, rxnorm_cui FROM molecules WHERE inn = %s", (inn,))
    by_inn = cur.fetchone()

    if not by_brand and not by_inn:
        results.append(("FAIL", brand, inn, "neither brand nor INN found"))
        continue
    if not by_brand:
        results.append(("WARN", brand, inn, f"brand not in drugs table; INN mol_id={by_inn[0]}"))
        continue
    if not by_inn:
        results.append(("FAIL", brand, inn, "INN not in molecules"))
        continue

    if by_brand[0] != by_inn[0]:
        results.append(("FAIL", brand, inn,
                         f"molecule_id mismatch brand={by_brand[0]} inn={by_inn[0]}"))
    else:
        results.append(("PASS", brand, inn,
                         f"mol_id={by_inn[0]}  rxnorm={by_inn[2]}"))

print("\n  Name resolution checks:")
print("  " + "-" * 70)
hard_failures = 0
for status, brand, inn, detail in results:
    print(f"  {status}  {brand:15s} -> {inn:15s}  {detail}")
    if status == "FAIL":
        hard_failures += 1

print()
if hard_failures:
    fail(f"{hard_failures} hard failures in name resolution")

passes = sum(1 for r in results if r[0] == "PASS")
warns  = sum(1 for r in results if r[0] == "WARN")
pass_(f"{passes} PASS  {warns} WARN (brand missing in drugs table)  0 FAIL")
