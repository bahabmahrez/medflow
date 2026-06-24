"""
Trap 8 — Therapeutic Duplication: Tahor (brand) = Atorvastatin (INN)
Expected:
  - Tahor and atorvastatin resolve to the SAME molecule_id
  - molecule has the same rxnorm_cui regardless of how it's queried
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

cur = connect().cursor()

# Query by Tunisian brand name
cur.execute("""
    SELECT m.id, m.inn, m.rxnorm_cui
    FROM drugs d
    JOIN molecules m ON m.id = d.molecule_id
    WHERE d.brand_name_tn ILIKE 'Tahor'
""")
by_brand = cur.fetchall()

# Query by INN
cur.execute("""
    SELECT m.id, m.inn, m.rxnorm_cui
    FROM molecules m
    WHERE m.inn = 'atorvastatin'
""")
by_inn = cur.fetchall()

errors = []
if not by_brand:
    errors.append("Tahor not found in drugs.brand_name_tn")
if not by_inn:
    errors.append("atorvastatin not found in molecules")

if not errors:
    brand_mol_id  = by_brand[0][0]
    inn_mol_id    = by_inn[0][0]
    brand_rxnorm  = by_brand[0][2]
    inn_rxnorm    = by_inn[0][2]

    if brand_mol_id != inn_mol_id:
        errors.append(f"molecule_id mismatch: Tahor={brand_mol_id} atorvastatin={inn_mol_id}")
    if brand_rxnorm != inn_rxnorm:
        errors.append(f"rxnorm_cui mismatch: Tahor={brand_rxnorm} atorvastatin={inn_rxnorm}")

if errors:
    fail(" | ".join(errors))

pass_(f"Tahor and atorvastatin -> same molecule_id={by_inn[0][0]}  rxnorm_cui={by_inn[0][2]}")
