"""
Load molecular targets and molecule-target links.

Sources (in priority order):
  1. ChEMBL mechanism endpoint — for each molecule with a chembl_id
     GET https://www.ebi.ac.uk/chembl/api/data/mechanism?molecule_chembl_id=<id>&format=json
  2. Hardcoded critical targets — ensures key targets are present even if ChEMBL
     doesn't return them (sparse coverage for some mechanisms)

Tables populated:
  molecular_targets         — target_name, uniprot_id
  molecule_molecular_targets — (molecule_id, target_id, action_type)
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

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"

# ── Hardcoded critical targets ────────────────────────────────────────────────
# These are the pharmacologically important targets that must be present.
# Format: (inn, target_name, uniprot_id, action_type)
# action_type values: INHIBITOR | AGONIST | ANTAGONIST | SUBSTRATE | INDUCER | OTHER
CRITICAL_TARGETS: list[tuple[str, str, str | None, str]] = [
    # Warfarin mechanism
    ("warfarin",         "Vitamin K epoxide reductase subunit 1",    "Q9BQB6", "INHIBITOR"),
    # Aspirin / NSAIDs
    ("aspirin",          "Cyclooxygenase-1 (COX-1)",                 "P23219", "INHIBITOR"),
    ("aspirin",          "Cyclooxygenase-2 (COX-2)",                 "P35354", "INHIBITOR"),
    ("ibuprofen",        "Cyclooxygenase-1 (COX-1)",                 "P23219", "INHIBITOR"),
    ("ibuprofen",        "Cyclooxygenase-2 (COX-2)",                 "P35354", "INHIBITOR"),
    ("diclofenac",       "Cyclooxygenase-1 (COX-1)",                 "P23219", "INHIBITOR"),
    ("diclofenac",       "Cyclooxygenase-2 (COX-2)",                 "P35354", "INHIBITOR"),
    ("naproxen",         "Cyclooxygenase-1 (COX-1)",                 "P23219", "INHIBITOR"),
    ("naproxen",         "Cyclooxygenase-2 (COX-2)",                 "P35354", "INHIBITOR"),
    # SSRIs
    ("fluoxetine",       "Serotonin transporter (SERT)",             "P31645", "INHIBITOR"),
    ("sertraline",       "Serotonin transporter (SERT)",             "P31645", "INHIBITOR"),
    # Tramadol (dual mechanism)
    ("tramadol",         "Serotonin transporter (SERT)",             "P31645", "INHIBITOR"),
    ("tramadol",         "Mu-type opioid receptor (MOR)",            "P35372", "AGONIST"),
    # Statins
    ("atorvastatin",     "HMG-CoA reductase",                        "P04035", "INHIBITOR"),
    ("simvastatin",      "HMG-CoA reductase",                        "P04035", "INHIBITOR"),
    # Immunosuppressants
    ("tacrolimus",       "Calcineurin (PPP3CA)",                     "Q08209", "INHIBITOR"),
    ("cyclosporine",     "Calcineurin (PPP3CA)",                     "Q08209", "INHIBITOR"),
    # Digoxin
    ("digoxin",          "Na+/K+-ATPase alpha-1 subunit",            "P05023", "INHIBITOR"),
    # Allopurinol
    ("allopurinol",      "Xanthine oxidase",                         "P47989", "INHIBITOR"),
    # Azathioprine
    ("azathioprine",     "Hypoxanthine-guanine phosphoribosyltransferase", "P00492", "INHIBITOR"),
    # Metformin
    ("metformin",        "AMP-activated protein kinase (AMPK)",      "Q13131", "ACTIVATOR"),
    # Clopidogrel
    ("clopidogrel",      "P2Y12 purinoceptor",                       "Q9H244", "ANTAGONIST"),
    # Levodopa
    ("levodopa",         "Aromatic-L-amino-acid decarboxylase",      "P20711", "SUBSTRATE"),
    # Sildenafil
    ("sildenafil",       "cGMP-specific phosphodiesterase type 5",   "O76074", "INHIBITOR"),
    # Methotrexate
    ("methotrexate",     "Dihydrofolate reductase (DHFR)",           "P00374", "INHIBITOR"),
    # Omeprazole
    ("omeprazole",       "Gastric H+/K+-ATPase",                     "P20648", "INHIBITOR"),
    # Prednisolone
    ("prednisolone",     "Glucocorticoid receptor (NR3C1)",          "P04150", "AGONIST"),
    # Lithium
    ("lithium",          "Inositol monophosphatase (IMPA1)",         "P29218", "INHIBITOR"),
    # Haloperidol / Risperidone
    ("haloperidol",      "Dopamine D2 receptor",                     "P14416", "ANTAGONIST"),
    ("risperidone",      "Dopamine D2 receptor",                     "P14416", "ANTAGONIST"),
    ("risperidone",      "Serotonin 5-HT2A receptor",                "P28223", "ANTAGONIST"),
    # Carbamazepine
    ("carbamazepine",    "Sodium channel protein type 1 subunit alpha", "P35498", "INHIBITOR"),
    # Valproate
    ("valproate",        "GABA transaminase",                        "P80404", "INHIBITOR"),
    # Fluconazole
    ("fluconazole",      "Lanosterol 14-alpha demethylase (CYP51)",  "O76074", "INHIBITOR"),
    # Rifampicin
    ("rifampicin",       "Pregnane X receptor (PXR/NR1I2)",         "O75469", "AGONIST"),
    # Isoniazid
    ("isoniazid",        "Enoyl-[acyl-carrier-protein] reductase",   "P9WGR1", "INHIBITOR"),
    # Amiodarone
    ("amiodarone",       "Cardiac potassium channel KCNH2 (hERG)",   "Q12809", "INHIBITOR"),
    # Colchicine
    ("colchicine",       "Tubulin alpha chain",                      "P68363", "INHIBITOR"),
    # Levothyroxine
    ("levothyroxine",    "Thyroid hormone receptor alpha (THR-alpha)","P10827", "AGONIST"),
    # Ethinylestradiol
    ("ethinylestradiol", "Estrogen receptor alpha (ESR1)",           "P03372", "AGONIST"),
]


def upsert_target(target_name: str, uniprot_id: str | None) -> int:
    """Insert or find a target; return its id."""
    cur.execute("""
        INSERT INTO molecular_targets (target_name, uniprot_id)
        VALUES (%s, %s)
        ON CONFLICT (target_name) DO UPDATE SET
            uniprot_id = COALESCE(EXCLUDED.uniprot_id, molecular_targets.uniprot_id)
        RETURNING id
    """, (target_name, uniprot_id))
    return cur.fetchone()[0]


def upsert_link(mol_id: int, target_id: int, action_type: str) -> None:
    cur.execute("""
        INSERT INTO molecule_molecular_targets (molecule_id, molecular_target_id, action_type)
        VALUES (%s, %s, %s)
        ON CONFLICT (molecule_id, molecular_target_id) DO UPDATE SET
            action_type = EXCLUDED.action_type
    """, (mol_id, target_id, action_type.upper()))


# ── Step 1: load hardcoded critical targets ───────────────────────────────────
hardcoded_loaded = 0
for (inn, target_name, uniprot_id, action_type) in CRITICAL_TARGETS:
    cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
    mol = cur.fetchone()
    if not mol:
        continue
    t_id = upsert_target(target_name, uniprot_id)
    upsert_link(mol[0], t_id, action_type)
    hardcoded_loaded += 1

print(f"Hardcoded targets loaded: {hardcoded_loaded}")

# ── Step 2: ChEMBL mechanism endpoint ─────────────────────────────────────────
cur.execute("SELECT m.id, m.inn, m.chembl_id FROM molecules m WHERE m.chembl_id IS NOT NULL")
molecules = cur.fetchall()

chembl_loaded = 0
chembl_skipped = 0

for mol_id, inn, chembl_id in molecules:
    try:
        resp = requests.get(
            f"{CHEMBL_BASE}/mechanism",
            params={"molecule_chembl_id": chembl_id, "format": "json", "limit": 20},
            timeout=10,
        )
        if resp.status_code != 200:
            chembl_skipped += 1
            time.sleep(0.3)
            continue

        data = resp.json()
        mechanisms = data.get("mechanisms", [])
        for mech in mechanisms:
            action_type = (mech.get("action_type") or "OTHER").upper()
            target_chembl = mech.get("target_chembl_id")
            if not target_chembl:
                continue

            # Fetch target details
            t_resp = requests.get(
                f"{CHEMBL_BASE}/target/{target_chembl}",
                params={"format": "json"},
                timeout=10,
            )
            if t_resp.status_code != 200:
                time.sleep(0.3)
                continue

            t_data = t_resp.json()
            target_name = t_data.get("pref_name", target_chembl)

            # Try to get UniProt ID from target components
            uniprot_id = None
            for comp in t_data.get("target_components", []):
                for xref in comp.get("target_component_xrefs", []):
                    if xref.get("xref_src_db") == "UniProt":
                        uniprot_id = xref.get("xref_id")
                        break
                if uniprot_id:
                    break

            t_id = upsert_target(target_name, uniprot_id)
            upsert_link(mol_id, t_id, action_type)
            chembl_loaded += 1
            time.sleep(0.1)

    except Exception as e:
        print(f"  ChEMBL error for {inn} ({chembl_id}): {e}")
        chembl_skipped += 1

    time.sleep(0.3)

print(f"ChEMBL targets loaded:    {chembl_loaded}  (skipped: {chembl_skipped})")

conn.commit()

# ── Summary ───────────────────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM molecular_targets")
print(f"\nTotal molecular_targets:         {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM molecule_molecular_targets")
print(f"Total molecule-target links:     {cur.fetchone()[0]}")

cur.close()
conn.close()
