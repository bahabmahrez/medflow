"""
Load Tunisian brand names from the PCT (Pharmacie Centrale de Tunisie) catalogue.
Reads directly from pct_human_medicines_recent_rich_rows.csv — no intermediate file needed.

Hardcoded fallbacks (bottom of file) handle:
  - molecules that have no drugs row yet (e.g. quetiapine)
  - alternate brand spellings not present in the PCT CSV (Kardegic, Depakine)
"""
import csv, os, psycopg2

BASE_DIR = os.path.dirname(__file__)
PCT_CSV  = os.path.join(BASE_DIR, "../sources/dataset/pct_human_medicines_recent_rich_rows.csv")

# Maps PCT DCI (INN) names to our canonical INNs
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
    "quetiapine": "quetiapine", "clonazepam": "clonazepam",
}

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)
cur = conn.cursor()

updated = skipped = 0
seen_inn = set()

with open(PCT_CSV, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        brand = (row.get("princeps") or "").strip()
        dci   = (row.get("code_DCI1") or "").strip().lower()

        if not brand or not dci or brand.upper() in ("NM", ""):
            skipped += 1
            continue

        inn = INN_MAP.get(dci)
        if not inn:
            skipped += 1
            continue

        if inn in seen_inn:
            skipped += 1
            continue

        cur.execute("""
            UPDATE drugs SET brand_name_tn = %s
            FROM molecules
            WHERE drugs.molecule_id = molecules.id
              AND molecules.inn = %s
              AND drugs.brand_name_tn IS NULL
        """, (brand, inn))

        if cur.rowcount:
            seen_inn.add(inn)
            updated += 1
            print(f"  SET  {inn:20s} -> {brand}")
        else:
            skipped += 1

# ── Hardcoded fallbacks ────────────────────────────────────────────────────────
# These handle three cases the PCT CSV does not cover:
#   1. quetiapine: molecule exists but has no drugs row at all — insert one.
#   2. aspirin:    PCT CSV sets Aspégic; Kardegic is a widely-used alternate
#                  brand — store it in brand_name so ILIKE resolution finds it.
#   3. valproate:  PCT CSV sets Dépakine (with accent); Depakine (no accent) is
#                  the spelling used in the stress test and in common clinical
#                  use — store unaccented form in brand_name for broad matching.
#
# Add new fallbacks here (never patch the DB directly) so clean rebuilds work.

FALLBACKS = [
    # (inn, brand_name, brand_name_tn, atc_code, dosage_form)
    ("quetiapine", "Seroquel",  "Seroquel",  "N05AH04", "tablet"),
    ("aspirin",    "Kardegic",  "Kardegic",   "B01AC06", "tablet"),
    ("valproate",  "Depakine",  "Depakine",   "N03AG01", "tablet"),
]

fallback_inserted = fallback_skipped = 0

for inn, brand_name, brand_name_tn, atc_code, dosage_form in FALLBACKS:
    cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
    mol = cur.fetchone()
    if not mol:
        print(f"  SKIP fallback {inn}: molecule not in DB")
        fallback_skipped += 1
        continue

    mol_id = mol[0]

    # Check if a drugs row with this brand_name already exists
    cur.execute("""
        SELECT id FROM drugs
        WHERE molecule_id = %s AND brand_name ILIKE %s
    """, (mol_id, brand_name))
    if cur.fetchone():
        print(f"  SKIP fallback {inn} / {brand_name}: already present")
        fallback_skipped += 1
        continue

    cur.execute("""
        INSERT INTO drugs (molecule_id, brand_name, brand_name_tn, atc_code, dosage_form)
        VALUES (%s, %s, %s, %s, %s)
    """, (mol_id, brand_name, brand_name_tn, atc_code, dosage_form))
    print(f"  FALLBACK INSERT  {inn:20s} -> {brand_name}")
    fallback_inserted += 1

conn.commit()
print(f"\nPCT brands: {updated} updated, {skipped} skipped")
print(f"Fallbacks:  {fallback_inserted} inserted, {fallback_skipped} skipped")
cur.close()
conn.close()