"""
Graph loader 9 — HAS_ADVERSE_EFFECT edges.

Mirrors knowledge_base/DB_loaders/load_adverse_effects.py.
Creates shared AdverseEffect nodes (one per MedDRA term) and connects
Molecule nodes to them with severity/frequency on the relationship.
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect

CRITICAL_AE: list[tuple[str, str, str, str]] = [
    ("warfarin",         "Haemorrhage",                          "life_threatening", "common"),
    ("warfarin",         "International normalised ratio increased", "severe",        "common"),
    ("heparin",          "Heparin-induced thrombocytopenia",     "severe",           "uncommon"),
    ("heparin",          "Haemorrhage",                          "severe",           "common"),
    ("metformin",        "Lactic acidosis",                      "life_threatening", "rare"),
    ("metformin",        "Nausea",                               "mild",             "common"),
    ("simvastatin",      "Rhabdomyolysis",                       "life_threatening", "rare"),
    ("simvastatin",      "Myopathy",                             "severe",           "uncommon"),
    ("atorvastatin",     "Rhabdomyolysis",                       "life_threatening", "rare"),
    ("atorvastatin",     "Myopathy",                             "severe",           "uncommon"),
    ("atorvastatin",     "Elevated liver enzymes",               "moderate",         "uncommon"),
    ("clarithromycin",   "QT interval prolongation",             "severe",           "uncommon"),
    ("clarithromycin",   "Hepatotoxicity",                       "severe",           "rare"),
    ("fluconazole",      "Hepatotoxicity",                       "severe",           "rare"),
    ("fluconazole",      "QT interval prolongation",             "severe",           "rare"),
    ("methotrexate",     "Pancytopenia",                         "life_threatening", "uncommon"),
    ("methotrexate",     "Hepatotoxicity",                       "severe",           "uncommon"),
    ("methotrexate",     "Pulmonary toxicity",                   "severe",           "rare"),
    ("tacrolimus",       "Nephrotoxicity",                       "severe",           "common"),
    ("tacrolimus",       "Neurotoxicity (tremor, seizures)",     "severe",           "uncommon"),
    ("tacrolimus",       "Hyperglycaemia",                       "moderate",         "common"),
    ("cyclosporine",     "Nephrotoxicity",                       "severe",           "common"),
    ("cyclosporine",     "Hypertension",                         "moderate",         "common"),
    ("amiodarone",       "Pulmonary toxicity",                   "severe",           "uncommon"),
    ("amiodarone",       "Thyroid dysfunction",                  "moderate",         "common"),
    ("amiodarone",       "QT interval prolongation",             "severe",           "common"),
    ("amiodarone",       "Hepatotoxicity",                       "severe",           "rare"),
    ("lithium",          "Lithium toxicity",                     "life_threatening", "uncommon"),
    ("lithium",          "Tremor",                               "moderate",         "common"),
    ("lithium",          "Polyuria",                             "moderate",         "common"),
    ("lithium",          "Hypothyroidism",                       "moderate",         "common"),
    ("carbamazepine",    "Stevens-Johnson syndrome",             "life_threatening", "rare"),
    ("carbamazepine",    "Aplastic anaemia",                     "life_threatening", "rare"),
    ("carbamazepine",    "Hyponatraemia",                        "moderate",         "common"),
    ("valproate",        "Hepatotoxicity",                       "life_threatening", "rare"),
    ("valproate",        "Pancreatitis",                         "severe",           "rare"),
    ("valproate",        "Thrombocytopenia",                     "severe",           "uncommon"),
    ("phenobarbital",    "Dependence",                           "severe",           "common"),
    ("phenobarbital",    "Stevens-Johnson syndrome",             "life_threatening", "rare"),
    ("fluoxetine",       "Serotonin syndrome",                   "life_threatening", "rare"),
    ("fluoxetine",       "Suicidal ideation",                    "severe",           "uncommon"),
    ("fluoxetine",       "QT interval prolongation",             "moderate",         "uncommon"),
    ("tramadol",         "Serotonin syndrome",                   "life_threatening", "rare"),
    ("tramadol",         "Seizure",                              "severe",           "uncommon"),
    ("tramadol",         "Respiratory depression",               "severe",           "uncommon"),
    ("ciprofloxacin",    "Tendon rupture",                       "severe",           "uncommon"),
    ("ciprofloxacin",    "QT interval prolongation",             "severe",           "uncommon"),
    ("ibuprofen",        "Gastrointestinal haemorrhage",         "severe",           "uncommon"),
    ("ibuprofen",        "Acute kidney injury",                  "severe",           "uncommon"),
    ("diclofenac",       "Gastrointestinal haemorrhage",         "severe",           "uncommon"),
    ("diclofenac",       "Cardiovascular events",                "severe",           "uncommon"),
    ("naproxen",         "Gastrointestinal haemorrhage",         "severe",           "uncommon"),
    ("digoxin",          "Digoxin toxicity",                     "life_threatening", "uncommon"),
    ("digoxin",          "Arrhythmia",                           "severe",           "common"),
    ("spironolactone",   "Hyperkalaemia",                        "severe",           "common"),
    ("spironolactone",   "Gynaecomastia",                        "moderate",         "common"),
    ("furosemide",       "Hypokalaemia",                         "severe",           "common"),
    ("furosemide",       "Ototoxicity",                          "severe",           "rare"),
    ("azathioprine",     "Myelosuppression",                     "life_threatening", "uncommon"),
    ("azathioprine",     "Lymphoma",                             "severe",           "rare"),
    ("rifampicin",       "Hepatotoxicity",                       "severe",           "uncommon"),
    ("rifampicin",       "Flu-like syndrome",                    "moderate",         "common"),
    ("isoniazid",        "Peripheral neuropathy",                "moderate",         "common"),
    ("isoniazid",        "Hepatotoxicity",                       "severe",           "uncommon"),
    ("allopurinol",      "Stevens-Johnson syndrome",             "life_threatening", "rare"),
    ("allopurinol",      "Toxic epidermal necrolysis",           "life_threatening", "rare"),
    ("colchicine",       "Myopathy",                             "severe",           "uncommon"),
    ("colchicine",       "Myelosuppression",                     "severe",           "rare"),
    ("glibenclamide",    "Hypoglycaemia",                        "severe",           "common"),
    ("clopidogrel",      "Haemorrhage",                          "severe",           "common"),
    ("clopidogrel",      "Thrombotic thrombocytopenic purpura",  "life_threatening", "rare"),
    ("prednisolone",     "Adrenal suppression",                  "severe",           "common"),
    ("prednisolone",     "Osteoporosis",                         "moderate",         "common"),
    ("prednisolone",     "Hyperglycaemia",                       "moderate",         "common"),
]

driver = connect()
hardcoded = 0

for inn, effect, severity, frequency in CRITICAL_AE:
    driver.execute_query(
        """
        MATCH (m:Molecule {inn: $inn})
        MERGE (ae:AdverseEffect {name: $effect})
        MERGE (m)-[r:HAS_ADVERSE_EFFECT]->(ae)
        SET r.severity  = $severity,
            r.frequency = $frequency,
            r.source    = 'curated'
        """,
        inn=inn, effect=effect, severity=severity, frequency=frequency,
    )
    hardcoded += 1

print(f"Hardcoded AEs loaded: {hardcoded}")

# ── OpenFDA adverse event API ─────────────────────────────────────────────────
try:
    import requests
    OPENFDA_BASE = "https://api.fda.gov/drug/event.json"

    all_inns = driver.execute_query("MATCH (m:Molecule) RETURN m.inn AS inn ORDER BY m.inn")
    molecules = [r["inn"] for r in all_inns.records]

    def rank_to_frequency(rank: int) -> str:
        if rank <= 2: return "common"
        if rank <= 5: return "uncommon"
        return "rare"

    api_loaded = api_failed = 0
    for inn in molecules:
        try:
            resp = requests.get(
                OPENFDA_BASE,
                params={
                    "search": f'patient.drug.medicinalproduct:"{inn}"',
                    "count":  "patient.reaction.reactionmeddrapt.exact",
                    "limit":  "10",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                api_failed += 1
                time.sleep(0.5)
                continue
            for rank, item in enumerate(resp.json().get("results", []), start=1):
                effect_name = item.get("term", "").strip().title()
                if not effect_name:
                    continue
                driver.execute_query(
                    """
                    MATCH (m:Molecule {inn: $inn})
                    MERGE (ae:AdverseEffect {name: $effect})
                    MERGE (m)-[r:HAS_ADVERSE_EFFECT]->(ae)
                    ON CREATE SET r.severity = 'moderate', r.frequency = $freq, r.source = 'openfda'
                    """,
                    inn=inn, effect=effect_name, freq=rank_to_frequency(rank),
                )
                api_loaded += 1
        except Exception as e:
            print(f"  OpenFDA error for {inn}: {e}")
            api_failed += 1
        time.sleep(0.4)

    print(f"OpenFDA AEs loaded: {api_loaded}  (failed: {api_failed})")

except ImportError:
    print("requests not installed — skipping OpenFDA AE enrichment")

driver.close()
print("Adverse effects done.")
