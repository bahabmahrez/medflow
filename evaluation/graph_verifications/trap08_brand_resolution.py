"""
Trap 08 — Brand resolution: Tahor → atorvastatin (same Molecule node)
Traversal: Drug -[:BRAND_OF]-> Molecule
Expected:
  - Drug node with brand_name_tn='Tahor' exists
  - it resolves via BRAND_OF to Molecule {inn:'atorvastatin'}
  - same rxnorm_cui regardless of query path
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, pass_, fail

driver = connect()

by_brand = driver.execute_query(
    """
    MATCH (d:Drug)-[:BRAND_OF]->(m:Molecule {inn: 'atorvastatin'})
    WHERE d.brand_name_tn = 'Tahor' OR d.brand_name = 'Tahor'
    RETURN m.inn AS inn, m.rxnorm_cui AS rxnorm, d.brand_name_tn AS brand_tn
    """
)

by_inn = driver.execute_query(
    """
    MATCH (m:Molecule {inn: 'atorvastatin'})
    RETURN m.rxnorm_cui AS rxnorm
    """
)
driver.close()

errors = []

if not by_brand.records:
    errors.append("no Drug node with brand_name_tn='Tahor' linked to atorvastatin via BRAND_OF")

if not by_inn.records:
    errors.append("atorvastatin Molecule node not found")

if by_brand.records and by_inn.records:
    brand_rxnorm = by_brand.records[0]["rxnorm"]
    inn_rxnorm   = by_inn.records[0]["rxnorm"]
    if brand_rxnorm and inn_rxnorm and brand_rxnorm != inn_rxnorm:
        errors.append(f"rxnorm_cui mismatch: Tahor={brand_rxnorm} atorvastatin={inn_rxnorm}")

if errors:
    fail(" | ".join(errors))

pass_(f"Tahor → atorvastatin via BRAND_OF  rxnorm_cui={by_inn.records[0]['rxnorm']}")
