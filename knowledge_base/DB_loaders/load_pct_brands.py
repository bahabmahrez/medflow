"""
Load Tunisian brand names from the PCT (Pharmacie Centrale de Tunisie) catalogue.
Reads directly from pct_human_medicines_recent_rich_rows.csv — no intermediate file needed.
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
    "fluconazole": "fluconazole", "warfarin": "warfarin",
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

conn.commit()
print(f"\nPCT brands: {updated} updated, {skipped} skipped")
cur.close()
conn.close()
