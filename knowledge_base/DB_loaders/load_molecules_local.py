"""
Load all 50 priority molecules from local hardcoded data.
No external API calls — uses RxNorm CUIs and ChEMBL IDs from verified public sources.
Run this instead of load_rxnorm_chembl.py when APIs are unavailable.
"""

import os
import psycopg2

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)
cur = conn.cursor()

# (inn, rxnorm_cui, chembl_id, half_life_hours, elimination_route)
# Sources: RxNorm CUIs from rxnorm_mapping.csv + public RxNav;
#          ChEMBL IDs from ebi.ac.uk/chembl;
#          half-life and elimination from standard pharmacology references.
MOLECULES = [
    # ── Anticoagulants / Antiplatelets ───────────────────────────────────────
    ("warfarin",         "11289",  "CHEMBL1547",   40,    "hepatic"),
    ("heparin",          "235473", None,            1.5,   "hepatic"),
    ("aspirin",          "1191",   "CHEMBL25",      0.33,  "renal"),
    ("clopidogrel",      "236991", "CHEMBL1771",    6,     "hepatic"),

    # ── Antidiabetics ────────────────────────────────────────────────────────
    ("metformin",        "235743", "CHEMBL1431",    6.5,   "renal"),
    ("glibenclamide",    "4815",   "CHEMBL1421",    10,    "hepatic"),
    ("insulin glargine", "274783", None,            24,    "subcutaneous"),

    # ── Cardiovascular ───────────────────────────────────────────────────────
    ("enalapril",        "203123", "CHEMBL578",     11,    "renal"),
    ("ramipril",         "35296",  "CHEMBL991",     17,    "renal"),
    ("amlodipine",       "104416", "CHEMBL1150",    35,    "hepatic"),
    ("furosemide",       "4603",   "CHEMBL1273",    2,     "renal"),
    ("spironolactone",   "9997",   "CHEMBL1078",    20,    "hepatic"),
    ("digoxin",          "3407",   "CHEMBL249",     36,    "renal"),
    ("atorvastatin",     "83367",  "CHEMBL1487",    14,    "hepatic"),
    ("simvastatin",      "36567",  "CHEMBL1262",    3,     "hepatic"),
    ("amiodarone",       "703",    "CHEMBL633",     1440,  "hepatic"),
    ("verapamil",        "11170",  "CHEMBL6966",    7,     "hepatic"),
    ("diltiazem",        "3443",   "CHEMBL701",     6,     "hepatic"),
    ("losartan",         "52175",  "CHEMBL902",     9,     "hepatic"),

    # ── Anti-inflammatory ────────────────────────────────────────────────────
    ("ibuprofen",        "5640",   "CHEMBL521",     2,     "renal"),
    ("diclofenac",       "3355",   "CHEMBL139",     2,     "hepatic"),
    ("naproxen",         "7258",   "CHEMBL154",     14,    "renal"),
    ("prednisolone",     "34372",  "CHEMBL131",     3,     "hepatic"),

    # ── Antibiotics / Antifungals ────────────────────────────────────────────
    ("amoxicillin",      "133008", "CHEMBL1706",    1.5,   "renal"),
    ("ciprofloxacin",    "235851", "CHEMBL2010",    5,     "renal"),
    ("metronidazole",    "103866", "CHEMBL137",     8,     "hepatic"),
    ("clarithromycin",   "21212",  "CHEMBL1741",    5,     "hepatic"),
    ("fluconazole",      "4450",   "CHEMBL106",     30,    "renal"),
    ("rifampicin",       "9384",   "CHEMBL374478",  3.5,   "hepatic"),
    ("isoniazid",        "6038",   "CHEMBL64",      5,     "hepatic"),

    # ── Neurological / Psychiatric ───────────────────────────────────────────
    ("carbamazepine",    "2002",   "CHEMBL108",     36,    "hepatic"),
    ("valproate",        "40254",  "CHEMBL109",     16,    "hepatic"),
    ("fluoxetine",       "227224", "CHEMBL41",      72,    "hepatic"),
    ("sertraline",       "155137", "CHEMBL275",     26,    "hepatic"),
    ("tramadol",         "10689",  "CHEMBL2219",    6,     "hepatic"),
    ("phenobarbital",    "8134",   "CHEMBL40",      100,   "hepatic"),
    ("levodopa",         "6375",   "CHEMBL1009",    1.5,   "hepatic"),
    ("lithium",          "6448",   "CHEMBL78",      24,    "renal"),
    ("haloperidol",      "5064",   "CHEMBL37",      24,    "hepatic"),
    ("risperidone",      "35636",  "CHEMBL498",     24,    "hepatic"),

    # ── Gastric ──────────────────────────────────────────────────────────────
    ("omeprazole",       "283742", "CHEMBL1113",    1.5,   "hepatic"),

    # ── Immunosuppressants / Oncology ────────────────────────────────────────
    ("methotrexate",     "6851",   "CHEMBL34819",   10,    "renal"),
    ("azathioprine",     "1520",   "CHEMBL932",     5,     "hepatic"),
    ("tacrolimus",       "161461", "CHEMBL1237",    12,    "hepatic"),
    ("cyclosporine",     "3008",   "CHEMBL160",     19,    "hepatic"),

    # ── Rheumatology ────────────────────────────────────────────────────────
    ("allopurinol",      "519",    "CHEMBL1356",    15,    "renal"),
    ("colchicine",       "2683",   "CHEMBL107",     30,    "hepatic"),

    # ── Endocrinology ───────────────────────────────────────────────────────
    ("levothyroxine",    "10582",  "CHEMBL43815",   168,   "hepatic"),
    ("ethinylestradiol", "3638",   "CHEMBL325",     24,    "hepatic"),

    # ── Other ────────────────────────────────────────────────────────────────
    ("sildenafil",       "99278",  "CHEMBL192",     4,     "hepatic"),
]

loaded, skipped = 0, 0

for (inn, rxnorm_cui, chembl_id, half_life, elimination) in MOLECULES:
    try:
        cur.execute("""
            INSERT INTO molecules (inn, rxnorm_cui, chembl_id, half_life_hours, elimination_route)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (inn) DO UPDATE SET
                rxnorm_cui       = EXCLUDED.rxnorm_cui,
                chembl_id        = EXCLUDED.chembl_id,
                half_life_hours  = EXCLUDED.half_life_hours,
                elimination_route = EXCLUDED.elimination_route
        """, (inn, rxnorm_cui, chembl_id, half_life, elimination))
        loaded += 1
        print(f"  OK  {inn:25s}  RxNorm: {rxnorm_cui or 'NULL':10s}  ChEMBL: {chembl_id or 'NULL'}")
    except Exception as e:
        skipped += 1
        print(f"  SKIP {inn}: {e}")

conn.commit()

cur.execute("SELECT COUNT(*) FROM molecules")
total = cur.fetchone()[0]

cur.close()
conn.close()

print(f"\nDone. Loaded/updated: {loaded}, Skipped: {skipped}")
print(f"Total molecules in DB: {total}")
