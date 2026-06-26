"""
Graph loader 1 — Molecule nodes.

Mirrors knowledge_base/DB_loaders/load_rxnorm_chembl.py.
Fetches RxNorm CUIs and ChEMBL IDs from their respective APIs and
creates/merges Molecule nodes in Neo4j.
CYP metabolite edges from ChEMBL are written as SUBSTRATE_OF relationships
(best-effort; the Flockhart loader is the authoritative CYP source).
"""
import os, sys, time, json, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect

DRUGS = [
    "warfarin", "heparin", "aspirin", "clopidogrel", "metformin", "glibenclamide",
    "insulin glargine", "enalapril", "ramipril", "amlodipine", "furosemide",
    "spironolactone", "digoxin", "atorvastatin", "simvastatin", "ibuprofen",
    "diclofenac", "naproxen", "prednisolone", "amoxicillin", "ciprofloxacin",
    "metronidazole", "clarithromycin", "fluconazole", "carbamazepine", "valproate",
    "fluoxetine", "sertraline", "omeprazole", "tramadol",
    "lithium", "haloperidol", "risperidone", "methotrexate", "azathioprine",
    "tacrolimus", "cyclosporine", "rifampicin", "isoniazid", "phenobarbital",
    "levodopa", "amiodarone", "verapamil", "diltiazem", "losartan",
    "allopurinol", "colchicine", "levothyroxine", "ethinylestradiol", "sildenafil",
    "quetiapine",
]


def get_rxnorm_cui(name: str) -> str | None:
    url = f"https://rxnav.nlm.nih.gov/REST/rxcui.json?name={urllib.parse.quote(name)}"
    with urllib.request.urlopen(url, timeout=8) as r:
        ids = json.load(r).get("idGroup", {}).get("rxnormId", [])
        return ids[0] if ids else None


def get_chembl_id(name: str) -> str | None:
    url = (
        "https://www.ebi.ac.uk/chembl/api/data/molecule"
        f"?pref_name__iexact={urllib.parse.quote(name)}&format=json"
    )
    with urllib.request.urlopen(url, timeout=8) as r:
        mols = json.load(r).get("molecules", [])
        return mols[0]["molecule_chembl_id"] if mols else None


def get_chembl_cyp(chembl_id: str) -> list:
    url = (
        f"https://www.ebi.ac.uk/chembl/api/data/metabolism"
        f"?substrate_chembl_id={chembl_id}&format=json"
    )
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.load(r).get("metabolisms", [])


driver = connect()
loaded = skipped = 0

for drug in DRUGS:
    print(f"Processing {drug}...")
    try:
        rxnorm_cui = get_rxnorm_cui(drug)
        time.sleep(0.2)
        chembl_id = get_chembl_id(drug)
        time.sleep(0.2)

        chembl_id_safe = chembl_id[:50] if chembl_id else None

        driver.execute_query(
            """
            MERGE (m:Molecule {inn: $inn})
            SET m.rxnorm_cui = $rxnorm_cui,
                m.chembl_id  = $chembl_id
            """,
            inn=drug, rxnorm_cui=rxnorm_cui, chembl_id=chembl_id_safe,
        )
        loaded += 1
        print(f"  OK — RxNorm: {rxnorm_cui}, ChEMBL: {chembl_id}")

        if chembl_id:
            try:
                cyp_data = get_chembl_cyp(chembl_id)
                time.sleep(0.2)
                for entry in cyp_data:
                    enzyme = entry.get("enzyme_name")
                    if not enzyme:
                        continue
                    driver.execute_query(
                        """
                        MATCH (m:Molecule {inn: $inn})
                        MERGE (cyp:CYPEnzyme {name: $enzyme})
                        MERGE (m)-[:SUBSTRATE_OF]->(cyp)
                        """,
                        inn=drug, enzyme=enzyme,
                    )
            except Exception as cyp_err:
                print(f"  WARN {drug}: CYP fetch failed (molecule saved): {cyp_err}")

    except Exception as e:
        print(f"  SKIP {drug}: {e}")
        skipped += 1

driver.close()
print(f"\nDone. Loaded: {loaded}, Skipped: {skipped}")
