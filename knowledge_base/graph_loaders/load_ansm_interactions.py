"""
Graph loader 4 — INTERACTS_WITH edges from the ANSM Thesaurus CSV.

Mirrors knowledge_base/DB_loaders/load_ansm_interactions.py.
ANSM is the canonical severity source; this loader always sets severity_ansm
and recomputes severity_active upward (never downgrades an existing value).
severity_rank (int 1-4) is stored on the edge so later loaders can compare
without fetching first.
"""
import csv, glob, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, SEVERITY_RANK, most_conservative, ordered_inns

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
    "amiodarone": "amiodarone", "rifampicin": "rifampicin",
    "allopurinol": "allopurinol", "azathioprine": "azathioprine",
    "tacrolimus": "tacrolimus",
}


def normalize_inn(raw: str) -> str:
    base = raw.split("(")[0].strip().lower()
    for key, canonical in CANONICAL.items():
        if base.startswith(key) or key.startswith(base):
            return canonical
    return base


csv_files = glob.glob(
    os.path.join(os.path.dirname(__file__), "../sources/dataset/ansm_interactions_all.csv")
)

driver = connect()
loaded = skipped = 0

for filepath in csv_files:
    print(f"Loading {os.path.basename(filepath)}...")
    with open(filepath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            inn_a = normalize_inn(row["molecule_a"].strip().lower())
            inn_b = normalize_inn(row["molecule_b"].strip().lower())
            severity_ansm    = row.get("severity_ansm", "").strip()
            severity_openfda = row.get("severity_openfda", "").strip()
            clinical_effect  = row.get("clinical_effect", "").strip() or None
            management       = row.get("management", "").strip() or None

            severity_active = most_conservative(severity_ansm, severity_openfda) if severity_openfda else severity_ansm
            rank = SEVERITY_RANK.get(severity_active, 0)

            # Canonical direction: alphabetically smaller INN first
            inn_a, inn_b = ordered_inns(inn_a, inn_b)

            try:
                driver.execute_query(
                    """
                    MATCH (a:Molecule {inn: $inn_a}), (b:Molecule {inn: $inn_b})
                    MERGE (a)-[r:INTERACTS_WITH]->(b)
                    ON CREATE SET
                        r.severity_ansm    = $severity_ansm,
                        r.severity_active  = $severity_active,
                        r.severity_rank    = $rank,
                        r.clinical_effect  = $clinical_effect,
                        r.management       = $management,
                        r.source_confidence = 'ANSM'
                    ON MATCH SET
                        r.severity_ansm   = $severity_ansm,
                        r.clinical_effect = coalesce($clinical_effect, r.clinical_effect),
                        r.management      = coalesce($management, r.management),
                        r.severity_active = CASE WHEN coalesce(r.severity_rank, 0) < $rank
                                                 THEN $severity_active ELSE r.severity_active END,
                        r.severity_rank   = CASE WHEN coalesce(r.severity_rank, 0) < $rank
                                                 THEN $rank ELSE r.severity_rank END
                    """,
                    inn_a=inn_a, inn_b=inn_b,
                    severity_ansm=severity_ansm, severity_active=severity_active,
                    rank=rank, clinical_effect=clinical_effect, management=management,
                )
                loaded += 1
            except Exception as e:
                print(f"  SKIP {inn_a} + {inn_b}: {e}")
                skipped += 1

driver.close()
print(f"\nDone. Loaded: {loaded}, Skipped: {skipped}")
