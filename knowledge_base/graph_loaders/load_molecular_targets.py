"""
Graph loader 10 — MolecularTarget nodes and TARGETS edges.

Mirrors knowledge_base/DB_loaders/load_molecular_targets.py.
Sources: hardcoded critical targets + ChEMBL mechanism endpoint.
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect

CRITICAL_TARGETS: list[tuple[str, str, str | None, str]] = [
    ("warfarin",         "Vitamin K epoxide reductase subunit 1",            "Q9BQB6",  "INHIBITOR"),
    ("aspirin",          "Cyclooxygenase-1 (COX-1)",                         "P23219",  "INHIBITOR"),
    ("aspirin",          "Cyclooxygenase-2 (COX-2)",                         "P35354",  "INHIBITOR"),
    ("ibuprofen",        "Cyclooxygenase-1 (COX-1)",                         "P23219",  "INHIBITOR"),
    ("ibuprofen",        "Cyclooxygenase-2 (COX-2)",                         "P35354",  "INHIBITOR"),
    ("diclofenac",       "Cyclooxygenase-1 (COX-1)",                         "P23219",  "INHIBITOR"),
    ("diclofenac",       "Cyclooxygenase-2 (COX-2)",                         "P35354",  "INHIBITOR"),
    ("naproxen",         "Cyclooxygenase-1 (COX-1)",                         "P23219",  "INHIBITOR"),
    ("naproxen",         "Cyclooxygenase-2 (COX-2)",                         "P35354",  "INHIBITOR"),
    ("fluoxetine",       "Serotonin transporter (SERT)",                     "P31645",  "INHIBITOR"),
    ("sertraline",       "Serotonin transporter (SERT)",                     "P31645",  "INHIBITOR"),
    ("tramadol",         "Serotonin transporter (SERT)",                     "P31645",  "INHIBITOR"),
    ("tramadol",         "Mu-type opioid receptor (MOR)",                    "P35372",  "AGONIST"),
    ("atorvastatin",     "HMG-CoA reductase",                                "P04035",  "INHIBITOR"),
    ("simvastatin",      "HMG-CoA reductase",                                "P04035",  "INHIBITOR"),
    ("tacrolimus",       "Calcineurin (PPP3CA)",                             "Q08209",  "INHIBITOR"),
    ("cyclosporine",     "Calcineurin (PPP3CA)",                             "Q08209",  "INHIBITOR"),
    ("digoxin",          "Na+/K+-ATPase alpha-1 subunit",                    "P05023",  "INHIBITOR"),
    ("allopurinol",      "Xanthine oxidase",                                 "P47989",  "INHIBITOR"),
    ("azathioprine",     "Hypoxanthine-guanine phosphoribosyltransferase",   "P00492",  "INHIBITOR"),
    ("metformin",        "AMP-activated protein kinase (AMPK)",              "Q13131",  "ACTIVATOR"),
    ("clopidogrel",      "P2Y12 purinoceptor",                               "Q9H244",  "ANTAGONIST"),
    ("levodopa",         "Aromatic-L-amino-acid decarboxylase",              "P20711",  "SUBSTRATE"),
    ("sildenafil",       "cGMP-specific phosphodiesterase type 5",           "O76074",  "INHIBITOR"),
    ("methotrexate",     "Dihydrofolate reductase (DHFR)",                   "P00374",  "INHIBITOR"),
    ("omeprazole",       "Gastric H+/K+-ATPase",                             "P20648",  "INHIBITOR"),
    ("prednisolone",     "Glucocorticoid receptor (NR3C1)",                  "P04150",  "AGONIST"),
    ("lithium",          "Inositol monophosphatase (IMPA1)",                 "P29218",  "INHIBITOR"),
    ("haloperidol",      "Dopamine D2 receptor",                             "P14416",  "ANTAGONIST"),
    ("risperidone",      "Dopamine D2 receptor",                             "P14416",  "ANTAGONIST"),
    ("risperidone",      "Serotonin 5-HT2A receptor",                       "P28223",  "ANTAGONIST"),
    ("carbamazepine",    "Sodium channel protein type 1 subunit alpha",      "P35498",  "INHIBITOR"),
    ("valproate",        "GABA transaminase",                                "P80404",  "INHIBITOR"),
    ("fluconazole",      "Lanosterol 14-alpha demethylase (CYP51)",          "O76074",  "INHIBITOR"),
    ("rifampicin",       "Pregnane X receptor (PXR/NR1I2)",                 "O75469",  "AGONIST"),
    ("isoniazid",        "Enoyl-[acyl-carrier-protein] reductase",           "P9WGR1",  "INHIBITOR"),
    ("amiodarone",       "Cardiac potassium channel KCNH2 (hERG)",           "Q12809",  "INHIBITOR"),
    ("colchicine",       "Tubulin alpha chain",                              "P68363",  "INHIBITOR"),
    ("levothyroxine",    "Thyroid hormone receptor alpha (THR-alpha)",       "P10827",  "AGONIST"),
    ("ethinylestradiol", "Estrogen receptor alpha (ESR1)",                   "P03372",  "AGONIST"),
]

driver = connect()
hardcoded_loaded = 0

for inn, target_name, uniprot_id, action_type in CRITICAL_TARGETS:
    driver.execute_query(
        """
        MATCH (m:Molecule {inn: $inn})
        MERGE (t:MolecularTarget {target_name: $target})
        SET t.uniprot_id = coalesce($uniprot, t.uniprot_id)
        MERGE (m)-[r:TARGETS]->(t)
        SET r.action_type = $action
        """,
        inn=inn, target=target_name, uniprot=uniprot_id, action=action_type,
    )
    hardcoded_loaded += 1

print(f"Hardcoded targets loaded: {hardcoded_loaded}")

# ── ChEMBL mechanism endpoint ─────────────────────────────────────────────────
try:
    import requests
    CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"

    mols = driver.execute_query(
        "MATCH (m:Molecule) WHERE m.chembl_id IS NOT NULL RETURN m.inn AS inn, m.chembl_id AS cid"
    )
    chembl_loaded = chembl_skipped = 0

    for rec in mols.records:
        inn, chembl_id = rec["inn"], rec["cid"]
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
            for mech in resp.json().get("mechanisms", []):
                action_type  = (mech.get("action_type") or "OTHER").upper()
                target_chembl = mech.get("target_chembl_id")
                if not target_chembl:
                    continue
                t_resp = requests.get(f"{CHEMBL_BASE}/target/{target_chembl}", params={"format": "json"}, timeout=10)
                if t_resp.status_code != 200:
                    continue
                t_data      = t_resp.json()
                target_name = t_data.get("pref_name", target_chembl)
                uniprot_id  = None
                for comp in t_data.get("target_components", []):
                    for xref in comp.get("target_component_xrefs", []):
                        if xref.get("xref_src_db") == "UniProt":
                            uniprot_id = xref.get("xref_id")
                            break
                    if uniprot_id:
                        break
                driver.execute_query(
                    """
                    MATCH (m:Molecule {inn: $inn})
                    MERGE (t:MolecularTarget {target_name: $target})
                    SET t.uniprot_id = coalesce($uniprot, t.uniprot_id)
                    MERGE (m)-[r:TARGETS]->(t)
                    ON CREATE SET r.action_type = $action
                    """,
                    inn=inn, target=target_name, uniprot=uniprot_id, action=action_type,
                )
                chembl_loaded += 1
                time.sleep(0.1)
        except Exception as e:
            print(f"  ChEMBL error for {inn}: {e}")
            chembl_skipped += 1
        time.sleep(0.3)

    print(f"ChEMBL targets loaded: {chembl_loaded}  (skipped: {chembl_skipped})")

except ImportError:
    print("requests not installed — skipping ChEMBL target enrichment")

driver.close()
print("Molecular targets done.")
