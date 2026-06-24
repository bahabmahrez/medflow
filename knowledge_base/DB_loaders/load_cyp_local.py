"""
Load CYP enzyme relationships from curated pharmacology data.

Sources (verify and update from these):
  1. Flockhart P450 Drug Interaction Table — Indiana University
     https://drug-interactions.medicine.iu.edu/MainTable.aspx
     Primary reference for substrate/inhibitor/inducer classifications with strength.

  2. FDA Drug Development and Drug Interactions Table
     https://www.fda.gov/drugs/drug-interactions-labeling/drug-development-and-drug-interactions-table-substrates-inhibitors-and-inducers
     Regulatory reference; used to write drug labels.

  3. ANSM Thesaurus des Interactions Médicamenteuses
     Corroborates mechanism type for interactions flagged as pharmacokinetic/CYP.

Strength definitions (Flockhart / FDA):
  strong   — increases AUC of index substrate ≥ 5-fold (inhibitor) or decreases ≥ 80% (inducer)
  moderate — 2–5-fold AUC increase (inhibitor) or 50–80% decrease (inducer)
  weak     — 1.25–2-fold AUC increase (inhibitor) or 20–50% decrease (inducer)

ChEMBL metabolism endpoint was evaluated and found structurally incomplete for substrate
relationships — most entries return empty. These values are sourced from the references above.
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

# (inn, enzyme, relationship, strength)
# relationship: SUBSTRATE | INHIBITOR | INDUCER
# strength: strong | moderate | weak | None (for substrates — strength not applicable)
CYP_DATA = [
    # ── Warfarin ─────────────────────────────────────────────────────────────
    # S-warfarin (active) primarily metabolized by CYP2C9; R-warfarin by CYP3A4
    ("warfarin",       "CYP2C9",  "SUBSTRATE",  None),
    ("warfarin",       "CYP3A4",  "SUBSTRATE",  None),

    # ── Antiplatelet ─────────────────────────────────────────────────────────
    # Clopidogrel needs CYP2C19 to form its active metabolite
    ("clopidogrel",    "CYP2C19", "SUBSTRATE",  None),

    # ── Statins ──────────────────────────────────────────────────────────────
    ("simvastatin",    "CYP3A4",  "SUBSTRATE",  None),
    ("atorvastatin",   "CYP3A4",  "SUBSTRATE",  None),
    ("lovastatin",     "CYP3A4",  "SUBSTRATE",  None),

    # ── ACE Inhibitors ───────────────────────────────────────────────────────
    # Enalapril and ramipril are prodrugs; not primarily CYP-mediated
    # (included for completeness, minor pathway)
    ("enalapril",      "CYP3A4",  "SUBSTRATE",  None),

    # ── Calcium Channel Blockers ─────────────────────────────────────────────
    ("amlodipine",     "CYP3A4",  "SUBSTRATE",  None),
    ("verapamil",      "CYP3A4",  "SUBSTRATE",  None),
    ("verapamil",      "CYP3A4",  "INHIBITOR",  "moderate"),
    ("diltiazem",      "CYP3A4",  "SUBSTRATE",  None),
    ("diltiazem",      "CYP3A4",  "INHIBITOR",  "moderate"),

    # ── Anti-inflammatory ────────────────────────────────────────────────────
    ("ibuprofen",      "CYP2C9",  "SUBSTRATE",  None),
    ("diclofenac",     "CYP2C9",  "SUBSTRATE",  None),
    ("naproxen",       "CYP2C9",  "SUBSTRATE",  None),

    # ── Prednisolone / Corticosteroids ───────────────────────────────────────
    ("prednisolone",   "CYP3A4",  "SUBSTRATE",  None),

    # ── Macrolide Antibiotic ─────────────────────────────────────────────────
    # Clarithromycin is one of the most potent CYP3A4 inhibitors in clinical use
    ("clarithromycin", "CYP3A4",  "INHIBITOR",  "strong"),
    ("clarithromycin", "CYP3A4",  "SUBSTRATE",  None),

    # ── Antifungal ───────────────────────────────────────────────────────────
    # Fluconazole: strong CYP2C9, moderate CYP3A4, moderate CYP2C19 inhibitor
    ("fluconazole",    "CYP2C9",  "INHIBITOR",  "strong"),
    ("fluconazole",    "CYP3A4",  "INHIBITOR",  "moderate"),
    ("fluconazole",    "CYP2C19", "INHIBITOR",  "moderate"),

    # ── Nitroimidazole ───────────────────────────────────────────────────────
    # Metronidazole inhibits CYP2C9 (warfarin interaction)
    ("metronidazole",  "CYP2C9",  "INHIBITOR",  "moderate"),

    # ── Anticonvulsants ───────────────────────────────────────────────────────
    # Carbamazepine: strong CYP3A4 inducer, also induces CYP2C9 and its own metabolism
    ("carbamazepine",  "CYP3A4",  "INDUCER",    "strong"),
    ("carbamazepine",  "CYP2C9",  "INDUCER",    "moderate"),
    ("carbamazepine",  "CYP1A2",  "INDUCER",    "moderate"),
    ("carbamazepine",  "CYP3A4",  "SUBSTRATE",  None),

    ("valproate",      "CYP2C9",  "INHIBITOR",  "weak"),
    ("valproate",      "CYP2C19", "INHIBITOR",  "weak"),

    ("phenobarbital",  "CYP3A4",  "INDUCER",    "strong"),
    ("phenobarbital",  "CYP2C9",  "INDUCER",    "strong"),
    ("phenobarbital",  "CYP1A2",  "INDUCER",    "moderate"),

    # ── SSRIs ────────────────────────────────────────────────────────────────
    # Fluoxetine + norfluoxetine: potent CYP2D6 inhibitor, moderate CYP2C19, weak CYP2C9
    ("fluoxetine",     "CYP2D6",  "INHIBITOR",  "strong"),
    ("fluoxetine",     "CYP2C19", "INHIBITOR",  "moderate"),
    ("fluoxetine",     "CYP2C9",  "INHIBITOR",  "weak"),

    ("sertraline",     "CYP2D6",  "INHIBITOR",  "moderate"),
    ("sertraline",     "CYP2C19", "INHIBITOR",  "weak"),
    ("sertraline",     "CYP3A4",  "SUBSTRATE",  None),
    ("sertraline",     "CYP2D6",  "SUBSTRATE",  None),

    # ── Opioid ───────────────────────────────────────────────────────────────
    # Tramadol requires CYP2D6 for conversion to active O-desmethyltramadol
    ("tramadol",       "CYP2D6",  "SUBSTRATE",  None),
    ("tramadol",       "CYP3A4",  "SUBSTRATE",  None),

    # ── PPI ──────────────────────────────────────────────────────────────────
    ("omeprazole",     "CYP2C19", "SUBSTRATE",  None),
    ("omeprazole",     "CYP2C19", "INHIBITOR",  "moderate"),
    ("omeprazole",     "CYP3A4",  "SUBSTRATE",  None),

    # ── Antifungal / Antimycobacterial ───────────────────────────────────────
    # Rifampicin: the most potent CYP inducer in clinical use — affects nearly all CYPs
    ("rifampicin",     "CYP3A4",  "INDUCER",    "strong"),
    ("rifampicin",     "CYP2C9",  "INDUCER",    "strong"),
    ("rifampicin",     "CYP2C19", "INDUCER",    "strong"),
    ("rifampicin",     "CYP1A2",  "INDUCER",    "strong"),
    ("rifampicin",     "CYP2B6",  "INDUCER",    "strong"),

    # Isoniazid: CYP2E1 inhibitor, weak CYP3A4 inhibitor
    ("isoniazid",      "CYP2E1",  "INHIBITOR",  "strong"),
    ("isoniazid",      "CYP3A4",  "INHIBITOR",  "weak"),

    # ── Antiarrhythmic ───────────────────────────────────────────────────────
    # Amiodarone: potent CYP2C9 inhibitor (warfarin accumulation), also CYP3A4
    ("amiodarone",     "CYP2C9",  "INHIBITOR",  "strong"),
    ("amiodarone",     "CYP3A4",  "INHIBITOR",  "moderate"),
    ("amiodarone",     "CYP2D6",  "INHIBITOR",  "moderate"),

    # ── Immunosuppressants ───────────────────────────────────────────────────
    # Tacrolimus and cyclosporine are CYP3A4 substrates — major CYP3A4 inhibitors cause toxicity
    ("tacrolimus",     "CYP3A4",  "SUBSTRATE",  None),
    ("cyclosporine",   "CYP3A4",  "SUBSTRATE",  None),
    ("cyclosporine",   "CYP3A4",  "INHIBITOR",  "weak"),

    # ── Psychiatric ──────────────────────────────────────────────────────────
    ("haloperidol",    "CYP2D6",  "SUBSTRATE",  None),
    ("haloperidol",    "CYP3A4",  "SUBSTRATE",  None),
    ("risperidone",    "CYP2D6",  "SUBSTRATE",  None),
    ("risperidone",    "CYP3A4",  "SUBSTRATE",  None),

    # ── ARB ──────────────────────────────────────────────────────────────────
    ("losartan",       "CYP2C9",  "SUBSTRATE",  None),
    ("losartan",       "CYP3A4",  "SUBSTRATE",  None),

    # ── Other ────────────────────────────────────────────────────────────────
    ("sildenafil",     "CYP3A4",  "SUBSTRATE",  None),
    ("sildenafil",     "CYP2C9",  "SUBSTRATE",  None),

    ("levothyroxine",  "CYP1A2",  "SUBSTRATE",  None),

    ("glibenclamide",  "CYP2C9",  "SUBSTRATE",  None),
    ("glibenclamide",  "CYP3A4",  "SUBSTRATE",  None),

    ("omeprazole",     "CYP2C19", "SUBSTRATE",  None),

    ("furosemide",     "CYP2C9",  "SUBSTRATE",  None),

    ("methotrexate",   "CYP3A4",  "SUBSTRATE",  None),  # minor; primarily renal

    ("allopurinol",    "CYP2C9",  "INHIBITOR",  "weak"),
]

loaded, skipped = 0, 0

for (inn, enzyme, relationship, strength) in CYP_DATA:
    cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
    mol = cur.fetchone()
    if not mol:
        print(f"  SKIP {inn}: molecule not found in DB")
        skipped += 1
        continue

    try:
        cur.execute("""
            INSERT INTO cyp_relationships (molecule_id, enzyme, relationship, strength)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (molecule_id, enzyme, relationship) DO UPDATE SET
                strength = EXCLUDED.strength
        """, (mol[0], enzyme, relationship, strength))
        loaded += 1
    except Exception as e:
        print(f"  SKIP {inn} {enzyme} {relationship}: {e}")
        skipped += 1

conn.commit()

cur.execute("SELECT COUNT(*) FROM cyp_relationships")
total = cur.fetchone()[0]

cur.close()
conn.close()

print(f"\nDone. Loaded/updated: {loaded}, Skipped: {skipped}")
print(f"Total CYP relationships in DB: {total}")
