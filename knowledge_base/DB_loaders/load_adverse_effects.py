"""
Load adverse effects from OpenFDA pharmacovigilance data.

Sources (in priority order):
  1. OpenFDA adverse event API — top-10 reported reactions per drug
     GET https://api.fda.gov/drug/event.json?search=...&count=reaction&limit=10
  2. Hardcoded critical life-threatening adverse effects — ensures key safety
     signals are always present regardless of API availability

Tables populated:
  adverse_effects (molecule_id, adverse_effect_name, severity, frequency, source)

Severity mapping (CTCAE-inspired):
  life_threatening — rhabdomyolysis, lactic acidosis, pancytopenia, fatal arrhythmia
  severe           — hemorrhage, hepatotoxicity, nephrotoxicity, QT prolongation
  moderate         — myopathy, tremor, dysglycemia, thyroid dysfunction
  mild             — nausea, headache, dizziness
"""

import os
import time
import requests
import psycopg2

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)
cur = conn.cursor()

OPENFDA_BASE = "https://api.fda.gov/drug/event.json"

# ── Hardcoded critical adverse effects ───────────────────────────────────────
# Life-threatening and severe effects that MUST be in the DB for clinical safety.
# Format: (inn, effect_name, severity, frequency)
CRITICAL_AE: list[tuple[str, str, str, str]] = [
    # Warfarin
    ("warfarin",         "Haemorrhage",                    "life_threatening", "common"),
    ("warfarin",         "International normalised ratio increased", "severe",  "common"),
    # Heparin
    ("heparin",          "Heparin-induced thrombocytopenia", "severe",          "uncommon"),
    ("heparin",          "Haemorrhage",                    "severe",            "common"),
    # Metformin
    ("metformin",        "Lactic acidosis",                "life_threatening",  "rare"),
    ("metformin",        "Nausea",                         "mild",              "common"),
    # Statins
    ("simvastatin",      "Rhabdomyolysis",                 "life_threatening",  "rare"),
    ("simvastatin",      "Myopathy",                       "severe",            "uncommon"),
    ("atorvastatin",     "Rhabdomyolysis",                 "life_threatening",  "rare"),
    ("atorvastatin",     "Myopathy",                       "severe",            "uncommon"),
    ("atorvastatin",     "Elevated liver enzymes",         "moderate",          "uncommon"),
    # Clarithromycin
    ("clarithromycin",   "QT interval prolongation",       "severe",            "uncommon"),
    ("clarithromycin",   "Hepatotoxicity",                 "severe",            "rare"),
    # Fluconazole
    ("fluconazole",      "Hepatotoxicity",                 "severe",            "rare"),
    ("fluconazole",      "QT interval prolongation",       "severe",            "rare"),
    # Methotrexate
    ("methotrexate",     "Pancytopenia",                   "life_threatening",  "uncommon"),
    ("methotrexate",     "Hepatotoxicity",                 "severe",            "uncommon"),
    ("methotrexate",     "Pulmonary toxicity",             "severe",            "rare"),
    # Tacrolimus
    ("tacrolimus",       "Nephrotoxicity",                 "severe",            "common"),
    ("tacrolimus",       "Neurotoxicity (tremor, seizures)", "severe",          "uncommon"),
    ("tacrolimus",       "Hyperglycaemia",                 "moderate",          "common"),
    # Cyclosporine
    ("cyclosporine",     "Nephrotoxicity",                 "severe",            "common"),
    ("cyclosporine",     "Hypertension",                   "moderate",          "common"),
    # Amiodarone
    ("amiodarone",       "Pulmonary toxicity",             "severe",            "uncommon"),
    ("amiodarone",       "Thyroid dysfunction",            "moderate",          "common"),
    ("amiodarone",       "QT interval prolongation",       "severe",            "common"),
    ("amiodarone",       "Hepatotoxicity",                 "severe",            "rare"),
    # Lithium
    ("lithium",          "Lithium toxicity",               "life_threatening",  "uncommon"),
    ("lithium",          "Tremor",                         "moderate",          "common"),
    ("lithium",          "Polyuria",                       "moderate",          "common"),
    ("lithium",          "Hypothyroidism",                 "moderate",          "common"),
    # Carbamazepine
    ("carbamazepine",    "Stevens-Johnson syndrome",       "life_threatening",  "rare"),
    ("carbamazepine",    "Aplastic anaemia",               "life_threatening",  "rare"),
    ("carbamazepine",    "Hyponatraemia",                  "moderate",          "common"),
    # Valproate
    ("valproate",        "Hepatotoxicity",                 "life_threatening",  "rare"),
    ("valproate",        "Pancreatitis",                   "severe",            "rare"),
    ("valproate",        "Thrombocytopenia",               "severe",            "uncommon"),
    # Phenobarbital
    ("phenobarbital",    "Dependence",                     "severe",            "common"),
    ("phenobarbital",    "Stevens-Johnson syndrome",       "life_threatening",  "rare"),
    # Fluoxetine
    ("fluoxetine",       "Serotonin syndrome",             "life_threatening",  "rare"),
    ("fluoxetine",       "Suicidal ideation",              "severe",            "uncommon"),
    ("fluoxetine",       "QT interval prolongation",       "moderate",          "uncommon"),
    # Tramadol
    ("tramadol",         "Serotonin syndrome",             "life_threatening",  "rare"),
    ("tramadol",         "Seizure",                        "severe",            "uncommon"),
    ("tramadol",         "Respiratory depression",         "severe",            "uncommon"),
    # Ciprofloxacin
    ("ciprofloxacin",    "Tendon rupture",                 "severe",            "uncommon"),
    ("ciprofloxacin",    "QT interval prolongation",       "severe",            "uncommon"),
    # Ibuprofen / NSAIDs
    ("ibuprofen",        "Gastrointestinal haemorrhage",   "severe",            "uncommon"),
    ("ibuprofen",        "Acute kidney injury",            "severe",            "uncommon"),
    ("diclofenac",       "Gastrointestinal haemorrhage",   "severe",            "uncommon"),
    ("diclofenac",       "Cardiovascular events",          "severe",            "uncommon"),
    ("naproxen",         "Gastrointestinal haemorrhage",   "severe",            "uncommon"),
    # Digoxin
    ("digoxin",          "Digoxin toxicity",               "life_threatening",  "uncommon"),
    ("digoxin",          "Arrhythmia",                     "severe",            "common"),
    # Spironolactone
    ("spironolactone",   "Hyperkalaemia",                  "severe",            "common"),
    ("spironolactone",   "Gynaecomastia",                  "moderate",          "common"),
    # Furosemide
    ("furosemide",       "Hypokalaemia",                   "severe",            "common"),
    ("furosemide",       "Ototoxicity",                    "severe",            "rare"),
    # Azathioprine
    ("azathioprine",     "Myelosuppression",               "life_threatening",  "uncommon"),
    ("azathioprine",     "Lymphoma",                       "severe",            "rare"),
    # Rifampicin
    ("rifampicin",       "Hepatotoxicity",                 "severe",            "uncommon"),
    ("rifampicin",       "Flu-like syndrome",              "moderate",          "common"),
    # Isoniazid
    ("isoniazid",        "Peripheral neuropathy",          "moderate",          "common"),
    ("isoniazid",        "Hepatotoxicity",                 "severe",            "uncommon"),
    # Allopurinol
    ("allopurinol",      "Stevens-Johnson syndrome",       "life_threatening",  "rare"),
    ("allopurinol",      "Toxic epidermal necrolysis",     "life_threatening",  "rare"),
    # Colchicine
    ("colchicine",       "Myopathy",                       "severe",            "uncommon"),
    ("colchicine",       "Myelosuppression",               "severe",            "rare"),
    # Glibenclamide
    ("glibenclamide",    "Hypoglycaemia",                  "severe",            "common"),
    # Clopidogrel
    ("clopidogrel",      "Haemorrhage",                    "severe",            "common"),
    ("clopidogrel",      "Thrombotic thrombocytopenic purpura", "life_threatening", "rare"),
    # Prednisolone
    ("prednisolone",     "Adrenal suppression",            "severe",            "common"),
    ("prednisolone",     "Osteoporosis",                   "moderate",          "common"),
    ("prednisolone",     "Hyperglycaemia",                 "moderate",          "common"),
]

# Frequency rank for deduplication (higher = more important to keep)
FREQ_RANK = {"common": 3, "uncommon": 2, "rare": 1}
SEV_RANK  = {"life_threatening": 4, "severe": 3, "moderate": 2, "mild": 1}


def insert_ae(mol_id: int, name: str, severity: str, frequency: str, source: str) -> None:
    cur.execute("""
        INSERT INTO adverse_effects
            (molecule_id, adverse_effect_name, severity, frequency, source)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (mol_id, name, severity, frequency, source))


# ── Step 1: hardcoded critical adverse effects ────────────────────────────────
hardcoded = 0
for (inn, effect, severity, frequency) in CRITICAL_AE:
    cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
    mol = cur.fetchone()
    if not mol:
        continue
    insert_ae(mol[0], effect, severity, frequency, "curated")
    hardcoded += 1

print(f"Hardcoded AEs loaded: {hardcoded}")

# ── Step 2: OpenFDA adverse event API — top-10 reactions per drug ─────────────
cur.execute("SELECT id, inn FROM molecules ORDER BY inn")
molecules = cur.fetchall()

api_loaded = 0
api_failed = 0

# Frequency bucket from count rank (1=most reported, 10=least of top 10)
def rank_to_frequency(rank: int) -> str:
    if rank <= 2: return "common"
    if rank <= 5: return "uncommon"
    return "rare"

for mol_id, inn in molecules:
    try:
        resp = requests.get(
            OPENFDA_BASE,
            params={
                "search":  f'patient.drug.medicinalproduct:"{inn}"',
                "count":   "patient.reaction.reactionmeddrapt.exact",
                "limit":   "10",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            api_failed += 1
            time.sleep(0.5)
            continue

        results = resp.json().get("results", [])
        for rank, item in enumerate(results, start=1):
            effect_name = item.get("term", "").strip().title()
            if not effect_name:
                continue
            frequency = rank_to_frequency(rank)
            # Severity: not available from count endpoint — use 'moderate' as default
            insert_ae(mol_id, effect_name, "moderate", frequency, "openfda")
            api_loaded += 1

    except Exception as e:
        print(f"  OpenFDA error for {inn}: {e}")
        api_failed += 1

    time.sleep(0.4)

print(f"OpenFDA AEs loaded:   {api_loaded}  (failed: {api_failed})")

conn.commit()

# ── Summary ───────────────────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM adverse_effects")
total = cur.fetchone()[0]

cur.execute("""
    SELECT severity, COUNT(*) FROM adverse_effects
    GROUP BY severity ORDER BY severity
""")
by_sev = cur.fetchall()

print(f"\nTotal adverse_effects:  {total}")
print(f"By severity: {dict(by_sev)}")

cur.close()
conn.close()
