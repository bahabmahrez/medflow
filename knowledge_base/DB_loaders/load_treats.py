"""
Load drug indications into the treats table.
Source: hardcoded from DrugBank/WHO ATC indications for all 50 priority drugs.
"""
import os
import psycopg2

DB = dict(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)

# (inn, indication_name, icd11_code, evidence_level)
# evidence_level: A = established, B = probable, C = possible
INDICATIONS = [
    # Anticoagulants
    ("warfarin",        "Venous thromboembolism prevention",     "BD71", "A"),
    ("warfarin",        "Atrial fibrillation stroke prevention", "BC80", "A"),
    ("warfarin",        "Mechanical heart valve prophylaxis",    "BD10", "A"),
    ("heparin",         "Venous thromboembolism treatment",      "BD71", "A"),
    ("heparin",         "Acute coronary syndrome",              "BA80", "A"),
    ("aspirin",         "Secondary cardiovascular prevention",  "BA80", "A"),
    ("aspirin",         "Antiplatelet therapy",                 "BA80", "A"),
    ("clopidogrel",     "Antiplatelet therapy",                 "BA80", "A"),
    ("clopidogrel",     "Acute coronary syndrome",              "BA80", "A"),

    # Statins
    ("atorvastatin",    "Hypercholesterolaemia",                "5C80", "A"),
    ("atorvastatin",    "Cardiovascular risk reduction",        "BA80", "A"),
    ("simvastatin",     "Hypercholesterolaemia",                "5C80", "A"),
    ("simvastatin",     "Cardiovascular risk reduction",        "BA80", "A"),

    # Antidiabetics
    ("metformin",       "Type 2 diabetes mellitus",             "5A11", "A"),
    ("glibenclamide",   "Type 2 diabetes mellitus",             "5A11", "A"),
    ("insulin glargine","Type 1 diabetes mellitus",             "5A10", "A"),
    ("insulin glargine","Type 2 diabetes mellitus",             "5A11", "A"),

    # ACE inhibitors / ARBs
    ("enalapril",       "Hypertension",                         "BA00", "A"),
    ("enalapril",       "Heart failure",                        "BD10", "A"),
    ("ramipril",        "Hypertension",                         "BA00", "A"),
    ("ramipril",        "Post-myocardial infarction",           "BA41", "A"),
    ("losartan",        "Hypertension",                         "BA00", "A"),
    ("losartan",        "Diabetic nephropathy",                 "5A11", "A"),

    # Diuretics
    ("furosemide",      "Heart failure",                        "BD10", "A"),
    ("furosemide",      "Oedema",                               "BD10", "A"),
    ("spironolactone",  "Heart failure",                        "BD10", "A"),
    ("spironolactone",  "Hypertension",                         "BA00", "B"),

    # Calcium channel blockers
    ("amlodipine",      "Hypertension",                         "BA00", "A"),
    ("amlodipine",      "Stable angina",                        "BA80", "A"),
    ("verapamil",       "Hypertension",                         "BA00", "A"),
    ("verapamil",       "Supraventricular tachycardia",         "BC81", "A"),
    ("diltiazem",       "Hypertension",                         "BA00", "A"),
    ("diltiazem",       "Stable angina",                        "BA80", "A"),

    # Antiarrhythmics / cardiac
    ("amiodarone",      "Ventricular tachycardia",              "BC82", "A"),
    ("amiodarone",      "Atrial fibrillation",                  "BC80", "A"),
    ("digoxin",         "Heart failure",                        "BD10", "A"),
    ("digoxin",         "Atrial fibrillation rate control",     "BC80", "A"),

    # Antibiotics
    ("amoxicillin",     "Bacterial infections",                 "1A00", "A"),
    ("amoxicillin",     "Community-acquired pneumonia",         "CA40", "A"),
    ("ciprofloxacin",   "Urinary tract infections",             "GC08", "A"),
    ("ciprofloxacin",   "Respiratory tract infections",         "CA40", "A"),
    ("clarithromycin",  "Community-acquired pneumonia",         "CA40", "A"),
    ("clarithromycin",  "H. pylori eradication",               "DA42", "A"),
    ("metronidazole",   "Anaerobic bacterial infections",       "1A00", "A"),
    ("metronidazole",   "H. pylori eradication",               "DA42", "A"),
    ("isoniazid",       "Tuberculosis",                         "1B10", "A"),
    ("rifampicin",      "Tuberculosis",                         "1B10", "A"),

    # Proton pump inhibitors
    ("omeprazole",      "Gastro-oesophageal reflux disease",    "DA43", "A"),
    ("omeprazole",      "Peptic ulcer disease",                 "DA41", "A"),
    ("omeprazole",      "H. pylori eradication",               "DA42", "A"),

    # Immunosuppressants
    ("tacrolimus",      "Solid organ transplant rejection prevention", "QA01", "A"),
    ("cyclosporine",    "Solid organ transplant rejection prevention", "QA01", "A"),
    ("cyclosporine",    "Rheumatoid arthritis",                 "FA20", "B"),
    ("azathioprine",    "Autoimmune conditions",                "4A40", "A"),
    ("azathioprine",    "Solid organ transplant",               "QA01", "A"),
    ("methotrexate",    "Rheumatoid arthritis",                 "FA20", "A"),
    ("methotrexate",    "Psoriasis",                            "EA90", "A"),

    # CNS / Psychiatry
    ("fluoxetine",      "Major depressive disorder",            "6A70", "A"),
    ("fluoxetine",      "Obsessive-compulsive disorder",        "6B20", "A"),
    ("sertraline",      "Major depressive disorder",            "6A70", "A"),
    ("sertraline",      "Anxiety disorders",                    "6B00", "A"),
    ("haloperidol",     "Schizophrenia",                        "6A20", "A"),
    ("haloperidol",     "Acute psychosis",                      "6A20", "A"),
    ("risperidone",     "Schizophrenia",                        "6A20", "A"),
    ("risperidone",     "Bipolar disorder",                     "6A60", "A"),
    ("quetiapine",      "Schizophrenia",                        "6A20", "A"),
    ("quetiapine",      "Bipolar disorder",                     "6A60", "A"),
    ("lithium",         "Bipolar disorder",                     "6A60", "A"),
    ("lithium",         "Mania prevention",                     "6A60", "A"),
    ("carbamazepine",   "Epilepsy",                             "8A60", "A"),
    ("carbamazepine",   "Bipolar disorder",                     "6A60", "B"),
    ("valproate",       "Epilepsy",                             "8A60", "A"),
    ("valproate",       "Bipolar disorder",                     "6A60", "A"),
    ("phenobarbital",   "Epilepsy",                             "8A60", "A"),
    ("levodopa",        "Parkinson disease",                    "8A00", "A"),

    # Analgesics
    ("tramadol",        "Moderate to severe pain",              "MG30", "A"),
    ("ibuprofen",       "Pain and inflammation",                "MG30", "A"),
    ("ibuprofen",       "Rheumatoid arthritis",                 "FA20", "A"),
    ("diclofenac",      "Pain and inflammation",                "MG30", "A"),
    ("naproxen",        "Pain and inflammation",                "MG30", "A"),

    # Other
    ("allopurinol",     "Gout",                                 "FA92", "A"),
    ("allopurinol",     "Hyperuricaemia",                       "5C58", "A"),
    ("colchicine",      "Acute gout",                           "FA92", "A"),
    ("levothyroxine",   "Hypothyroidism",                       "5A00", "A"),
    ("ethinylestradiol","Contraception",                        "QA21", "A"),
    ("sildenafil",      "Erectile dysfunction",                 "HA00", "A"),
    ("sildenafil",      "Pulmonary arterial hypertension",      "BB01", "A"),
    ("fluconazole",     "Fungal infections",                    "1F20", "A"),
    ("fluconazole",     "Candidiasis",                          "1F23", "A"),
]


def run():
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()

    # Ensure all required ICD-11 codes exist as disease_concepts (insert if missing)
    icd_needed = {row[2] for row in INDICATIONS}
    for icd in icd_needed:
        cur.execute("SELECT id FROM disease_concepts WHERE icd11_code = %s", (icd,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO disease_concepts (icd11_code, condition_name) VALUES (%s, %s)",
                (icd, icd)
            )

    inserted = skipped = 0
    for inn, indication, icd, evidence in INDICATIONS:
        cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
        mol = cur.fetchone()
        if not mol:
            print(f"  SKIP  molecule not found: {inn}")
            skipped += 1
            continue

        cur.execute("SELECT id FROM disease_concepts WHERE icd11_code = %s", (icd,))
        dc = cur.fetchone()

        cur.execute("""
            INSERT INTO treats (molecule_id, disease_concept_id, indication_name, evidence_level, source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (mol[0], dc[0], indication, evidence, "drugbank"))
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    cur.close(); conn.close()
    print(f"treats: {inserted} inserted, {skipped} skipped")


if __name__ == "__main__":
    run()
