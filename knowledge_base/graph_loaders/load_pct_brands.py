"""
Graph loader 3 — Tunisian brand name (brand_name_tn) updates.

Mirrors knowledge_base/DB_loaders/load_pct_brands.py.
Reads the PCT CSV and sets brand_name_tn on existing Drug nodes.
Fallback Drug nodes (quetiapine / Kardegic / Depakine) are MERGE'd fresh.
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect

BASE_DIR = os.path.dirname(__file__)
PCT_CSV  = os.path.join(BASE_DIR, "../sources/dataset/pct_human_medicines_recent_rich_rows.csv")

INN_MAP = {
    "acetylsalicylate": "aspirin", "aspirine": "aspirin", "aspirin": "aspirin",
    "amoxicillin": "amoxicillin", "amlodipine": "amlodipine",
    "atorvastatin": "atorvastatin", "carbamazepine": "carbamazepine",
    "ciprofloxacin": "ciprofloxacin",
    "clarithromycine": "clarithromycin", "clarithromycin": "clarithromycin",
    "clopidogrel": "clopidogrel", "diclofenac": "diclofenac",
    "digoxin": "digoxin", "digoxine": "digoxin",
    "enalapril": "enalapril", "fluconazole": "fluconazole",
    "fluoxetine": "fluoxetine", "furosemide": "furosemide",
    "glibenclamide": "glibenclamide", "heparin": "heparin",
    "insuline": "insulin glargine", "insulin": "insulin glargine",
    "ibuprofen": "ibuprofen", "metformin": "metformin",
    "metronidazole": "metronidazole", "naproxen": "naproxen",
    "omeprazole": "omeprazole", "prednisolone": "prednisolone",
    "ramipril": "ramipril", "sertraline": "sertraline",
    "simvastatin": "simvastatin", "spironolactone": "spironolactone",
    "tramadol": "tramadol", "valproate": "valproate",
    "valproic acid": "valproate", "acide valproique": "valproate",
    "losartan": "losartan", "amiodarone": "amiodarone",
    "lithium": "lithium", "risperidone": "risperidone",
    "haloperidol": "haloperidol", "methotrexate": "methotrexate",
    "azathioprine": "azathioprine", "tacrolimus": "tacrolimus",
    "cyclosporine": "cyclosporine", "cyclosporin": "cyclosporine",
    "rifampicin": "rifampicin", "rifampin": "rifampicin",
    "isoniazid": "isoniazid", "phenobarbital": "phenobarbital",
    "phenobarbitone": "phenobarbital", "levodopa": "levodopa",
    "verapamil": "verapamil", "diltiazem": "diltiazem",
    "allopurinol": "allopurinol", "colchicine": "colchicine",
    "levothyroxine": "levothyroxine", "sildenafil": "sildenafil",
    "warfarin": "warfarin",
    "quetiapine": "quetiapine",
}

driver = connect()
updated = skipped = 0
seen_inn: set[str] = set()

with open(PCT_CSV, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        brand = (row.get("princeps") or "").strip()
        dci   = (row.get("code_DCI1") or "").strip().lower()

        if not brand or not dci or brand.upper() in ("NM", "") or dci not in INN_MAP:
            skipped += 1
            continue

        inn = INN_MAP[dci]
        if inn in seen_inn:
            skipped += 1
            continue

        result = driver.execute_query(
            """
            MATCH (m:Molecule {inn: $inn})<-[:BRAND_OF]-(d:Drug)
            WHERE d.brand_name_tn IS NULL
            WITH d LIMIT 1
            SET d.brand_name_tn = $brand
            RETURN d.drug_id AS drug_id
            """,
            inn=inn, brand=brand,
        )
        if result.records:
            seen_inn.add(inn)
            updated += 1
            print(f"  SET  {inn:20s} -> {brand}")
        else:
            skipped += 1

# ── Fallback Drug nodes ────────────────────────────────────────────────────────
FALLBACKS = [
    # (inn, brand_name, brand_name_tn, atc_code, dosage_form)
    ("quetiapine", "Seroquel", "Seroquel",  "N05AH04", "tablet"),
    ("aspirin",    "Kardegic", "Kardegic",  "B01AC06",  "tablet"),
    ("valproate",  "Depakine", "Depakine",  "N03AG01",  "tablet"),
]

fallback_inserted = fallback_skipped = 0
for inn, brand_name, brand_name_tn, atc_code, dosage_form in FALLBACKS:
    drug_id = f"{inn}::{brand_name}"
    result = driver.execute_query(
        "MATCH (d:Drug {drug_id: $drug_id}) RETURN d.drug_id",
        drug_id=drug_id,
    )
    if result.records:
        print(f"  SKIP fallback {inn} / {brand_name}: already present")
        fallback_skipped += 1
        continue

    driver.execute_query(
        """
        MATCH (m:Molecule {inn: $inn})
        MERGE (d:Drug {drug_id: $drug_id})
        SET d.brand_name    = $brand_name,
            d.brand_name_tn = $brand_name_tn,
            d.atc_code      = $atc_code,
            d.dosage_form   = $dosage_form
        MERGE (d)-[:BRAND_OF]->(m)
        """,
        inn=inn, drug_id=drug_id, brand_name=brand_name,
        brand_name_tn=brand_name_tn, atc_code=atc_code, dosage_form=dosage_form,
    )
    print(f"  FALLBACK INSERT  {inn:20s} -> {brand_name}")
    fallback_inserted += 1

driver.close()
print(f"\nPCT brands: {updated} updated, {skipped} skipped")
print(f"Fallbacks:  {fallback_inserted} inserted, {fallback_skipped} skipped")
