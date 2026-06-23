import os
import csv
import glob
import psycopg2

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)
cur = conn.cursor()

SEVERITY_RANK = {
    "contre_indique": 4,
    "deconseillee": 3,
    "precaution_emploi": 2,
    "a_prendre_en_compte": 1,
    "major": 4,
    "moderate": 2,
    "minor": 1,
}

def most_conservative(s1, s2):
    return s1 if SEVERITY_RANK.get(s1, 0) >= SEVERITY_RANK.get(s2, 0) else s2

CANONICAL = {
    "aspirin": "aspirin", "acide acetylsalicylique": "aspirin",
    "ibuprofen": "ibuprofen", "diclofenac": "diclofenac", "naproxen": "naproxen",
    "enalapril": "enalapril", "ramipril": "ramipril",
    "spironolactone": "spironolactone", "furosemide": "furosemide",
    "simvastatin": "simvastatin", "atorvastatin": "atorvastatin",
    "clarithromycin": "clarithromycin", "fluconazole": "fluconazole",
    "warfarin": "warfarin", "heparin": "heparin", "clopidogrel": "clopidogrel",
    "metformin": "metformin", "digoxin": "digoxin", "amlodipine": "amlodipine",
    "carbamazepine": "carbamazepine", "valproate": "valproate",
    "fluoxetine": "fluoxetine", "sertraline": "sertraline",
    "tramadol": "tramadol", "omeprazole": "omeprazole",
    "insulin glargine": "insulin glargine", "glibenclamide": "glibenclamide",
    "amoxicillin": "amoxicillin", "ciprofloxacin": "ciprofloxacin",
    "metronidazole": "metronidazole", "prednisolone": "prednisolone",
}

def normalize_inn(raw):
    # strip anything in parentheses and extra notes
    base = raw.split("(")[0].strip().lower()
    # match against canonical names
    for key, canonical in CANONICAL.items():
        if base.startswith(key) or key.startswith(base):
            return canonical
    return base

def get_or_create_molecule(raw_inn):
    inn = normalize_inn(raw_inn)
    cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO molecules (inn) VALUES (%s) RETURNING id", (inn,))
    return cur.fetchone()[0]

# Data file lives under knowledge_base/sources/dataset/...
csv_files = glob.glob(
    os.path.join(os.path.dirname(__file__), "../sources/dataset/ansm_interactions_all.csv")
)
loaded, skipped = 0, 0

for filepath in csv_files:
    print(f"Loading {os.path.basename(filepath)}...")
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mol_a = row["molecule_a"].strip().lower()
            mol_b = row["molecule_b"].strip().lower()
            severity_ansm = row.get("severity_ansm", "").strip()
            severity_openfda = row.get("severity_openfda", "").strip()
            clinical_effect = row.get("clinical_effect", "").strip()
            management = row.get("management", "").strip()

            # resolve active severity
            severity_active = most_conservative(severity_ansm, severity_openfda) if severity_openfda else severity_ansm

            try:
                cur.execute("SAVEPOINT sp")
                id_a = get_or_create_molecule(mol_a)
                id_b = get_or_create_molecule(mol_b)

                # always store pair in consistent order (smaller id first)
                if id_a > id_b:
                    id_a, id_b = id_b, id_a

                cur.execute("""
                    INSERT INTO drug_interactions
                        (molecule_a_id, molecule_b_id, severity_ansm, severity_active, clinical_effect, management, source_confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (molecule_a_id, molecule_b_id) DO UPDATE SET
                        severity_ansm    = EXCLUDED.severity_ansm,
                        severity_active  = EXCLUDED.severity_active,
                        clinical_effect  = EXCLUDED.clinical_effect,
                        management       = EXCLUDED.management
                """, (id_a, id_b, severity_ansm, severity_active, clinical_effect, management, "ANSM"))
                cur.execute("RELEASE SAVEPOINT sp")
                loaded += 1
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                print(f"  SKIP {mol_a} + {mol_b}: {e}")
                skipped += 1

conn.commit()
cur.close()
conn.close()
print(f"\nDone. Loaded: {loaded}, Skipped: {skipped}")
