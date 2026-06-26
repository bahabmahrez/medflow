"""
Graph loader 2 — Drug nodes, DiseaseConcept nodes, CONTRAINDICATED_FOR edges,
AllergyGroup nodes, CROSS_REACTS_WITH edges, BELONGS_TO_ALLERGY_GROUP edges.

Mirrors knowledge_base/DB_loaders/load_drugs_contraindications.py.
Drug unique key: drug_id = "<inn>::<brand_name>" (stable across reloads).
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR = os.path.join(BASE_DIR, "../sources/clean")

DRUGS = [
    # (inn, brand_name, brand_name_tn, brand_name_fr, atc, category, form, dose_adult, dose_elderly, dose_renal, dose_hepatic)
    ("warfarin",        "Coumadin",    None,        "Coumadine",  "B01AA03", "Anticoagulant",            "tablet",    "2-10mg/day titrated to INR",          "Start low, monitor INR closely",       "Contraindicated if CrCl<10",               "Caution, monitor INR"),
    ("heparin",         "Heparin",     None,        "Héparine",   "B01AB01", "Anticoagulant",            "injection","weight-based",                         "Reduce dose",                          "Reduce dose, monitor anti-Xa",             "Use with caution"),
    ("aspirin",         "Aspégic",     "Aspégic",   "Aspégic",    "B01AC06", "Antiplatelet",             "tablet",    "75-325mg/day",                        "75mg/day",                             "Avoid if CrCl<10",                         "Avoid in severe hepatic failure"),
    ("clopidogrel",     "Plavix",      "Plavix",    "Plavix",     "B01AC04", "Antiplatelet",             "tablet",    "75mg/day",                            "75mg/day",                             "No dose adjustment",                       "Caution in severe hepatic impairment"),
    ("metformin",       "Glucophage",  "Glucophage","Glucophage", "A10BA02", "Antidiabetic",             "tablet",    "500-2000mg/day",                      "Start 500mg, titrate slowly",          "Contraindicated if eGFR<30",               "Contraindicated in hepatic failure"),
    ("glibenclamide",   "Daonil",      "Daonil",    "Daonil",     "A10BB01", "Antidiabetic",             "tablet",    "2.5-15mg/day",                        "Start 2.5mg, risk of hypoglycemia",    "Avoid if CrCl<30",                         "Avoid in hepatic failure"),
    ("insulin glargine","Lantus",      "Lantus",    "Lantus",     "A10AE04", "Antidiabetic",             "injection","individualized",                        "Start low, titrate",                   "Monitor glucose closely",                  "Monitor glucose closely"),
    ("enalapril",       "Renitec",     None,        "Renitec",    "C09AA02", "ACE inhibitor",            "tablet",    "5-40mg/day",                          "Start 2.5mg",                          "Start 2.5mg if CrCl<30",                   "Caution"),
    ("ramipril",        "Triatec",     "Triatec",   "Triatec",    "C09AA05", "ACE inhibitor",            "tablet",    "2.5-10mg/day",                        "Start 1.25mg",                         "Start 1.25mg if CrCl<30",                  "Caution"),
    ("amlodipine",      "Amlor",       "Amlor",     "Amlor",      "C08CA01", "Calcium channel blocker",  "tablet",    "5-10mg/day",                          "5mg/day",                              "No dose adjustment",                       "Start 5mg, titrate slowly"),
    ("furosemide",      "Lasilix",     "Lasilix",   "Lasilix",    "C03CA01", "Loop diuretic",            "tablet",    "20-80mg/day",                         "Start low",                            "Higher doses may be needed",               "Caution"),
    ("spironolactone",  "Aldactone",   "Aldactone", "Aldactone",  "C03DA01", "K-sparing diuretic",       "tablet",    "25-100mg/day",                        "Start 25mg",                           "Avoid if CrCl<30",                         "Caution in severe hepatic failure — monitor electrolytes"),
    ("digoxin",         "Digoxine",    None,        "Digoxine",   "C01AA05", "Cardiac glycoside",        "tablet",    "0.125-0.25mg/day",                    "0.0625-0.125mg/day",                   "Reduce dose — renally cleared",            "Caution"),
    ("atorvastatin",    "Tahor",       "Tahor",     "Tahor",      "C10AA05", "Statin",                   "tablet",    "10-80mg/day",                         "10-20mg/day",                          "No dose adjustment",                       "Contraindicated in active hepatic disease"),
    ("simvastatin",     "Zocor",       "Zocor",     "Zocor",      "C10AA01", "Statin",                   "tablet",    "10-40mg/day",                         "10-20mg/day",                          "Start 5mg if CrCl<30",                     "Contraindicated in active hepatic disease"),
    ("ibuprofen",       "Brufen",      "Brufen",    "Brufen",     "M01AE01", "NSAID",                    "tablet",    "400-800mg TID",                       "Use lowest effective dose",            "Avoid if CrCl<30",                         "Avoid in hepatic failure"),
    ("diclofenac",      "Voltarène",   "Voltarène", "Voltarène",  "M01AB05", "NSAID",                    "tablet",    "50mg TID",                            "Use lowest effective dose",            "Avoid if CrCl<30",                         "Avoid in hepatic failure"),
    ("naproxen",        "Naprosyne",   "Naprosyne", "Naprosyne",  "M01AE02", "NSAID",                    "tablet",    "250-500mg BID",                       "Use lowest effective dose",            "Avoid if CrCl<30",                         "Avoid in hepatic failure"),
    ("prednisolone",    "Solupred",    "Solupred",  "Solupred",   "H02AB06", "Corticosteroid",           "tablet",    "5-60mg/day",                          "5-10mg/day",                           "No dose adjustment",                       "Caution"),
    ("amoxicillin",     "Clamoxyl",    "Clamoxyl",  "Clamoxyl",   "J01CA04", "Penicillin antibiotic",    "capsule",   "500mg TID",                           "500mg TID",                            "Reduce dose if CrCl<30",                   "No dose adjustment"),
    ("ciprofloxacin",   "Ciflox",      "Ciflox",    "Ciflox",     "J01MA02", "Fluoroquinolone",          "tablet",    "500mg BID",                           "250-500mg BID",                        "250-500mg BID if CrCl<30",                 "Caution"),
    ("metronidazole",   "Flagyl",      "Flagyl",    "Flagyl",     "J01XD01", "Nitroimidazole",           "tablet",    "400-500mg TID",                       "400mg TID",                            "No dose adjustment",                       "Reduce dose in severe hepatic failure"),
    ("clarithromycin",  "Zeclar",      "Zeclar",    "Zeclar",     "J01FA09", "Macrolide antibiotic",     "tablet",    "500mg BID",                           "500mg BID",                            "250mg BID if CrCl<30",                     "Caution"),
    ("fluconazole",     "Triflucan",   "Triflucan", "Triflucan",  "J02AC01", "Antifungal",               "capsule",   "150-400mg/day",                       "150mg",                                "50% dose reduction if CrCl<50",            "Caution"),
    ("carbamazepine",   "Tégrétol",    "Tégrétol",  "Tégrétol",   "N03AF01", "Anticonvulsant",           "tablet",    "400-1200mg/day",                      "Start low, titrate",                   "Use with caution",                         "Caution"),
    ("valproate",       "Dépakine",    "Dépakine",  "Dépakine",   "N03AG01", "Anticonvulsant",           "tablet",    "500-2000mg/day",                      "Start low",                            "No dose adjustment",                       "Contraindicated in hepatic failure"),
    ("fluoxetine",      "Prozac",      "Prozac",    "Prozac",     "N06AB03", "SSRI",                     "capsule",   "20-60mg/day",                         "20mg/day",                             "No dose adjustment",                       "Reduce dose or increase interval"),
    ("sertraline",      "Zoloft",      "Zoloft",    "Zoloft",     "N06AB06", "SSRI",                     "tablet",    "50-200mg/day",                        "25-100mg/day",                         "No dose adjustment",                       "Start low, titrate slowly"),
    ("omeprazole",      "Mopral",      "Mopral",    "Mopral",     "A02BC01", "PPI",                      "capsule",   "20-40mg/day",                         "20mg/day",                             "No dose adjustment",                       "Max 20mg/day in severe hepatic failure"),
    ("tramadol",        "Topalgic",    "Topalgic",  "Topalgic",   "N02AX02", "Opioid analgesic",         "tablet",    "50-100mg q4-6h, max 400mg/day",       "Max 300mg/day",                        "Extend dosing interval if CrCl<30",        "Reduce dose in hepatic failure"),
    ("quetiapine",      "Seroquel",    "Seroquel",  "Seroquel",   "N05AH04", "Atypical antipsychotic",   "tablet",    "50-800mg/day",                        "25-50mg BID, titrate slowly",          "No dose adjustment",                       "Caution in hepatic impairment"),
]

DISEASE_CONCEPTS = [
    ("N18",   "709044004", "Renal impairment",              "Reduced kidney function (e.g., CKD / impaired renal clearance)."),
    ("K76.9", "235856003", "Hepatic impairment",            "Reduced liver function / hepatic impairment."),
    ("Z34",   "77386006",  "Pregnancy",                     "Pregnancy."),
    ("K27",   "13200003",  "Peptic ulcer disease",          "Peptic ulcer disease."),
    ("Z88.0", "372687004", "Hypersensitivity to penicillin","Hypersensitivity to penicillin."),
    ("8A60",  "84757009",  "Epilepsy",                      "Epilepsy."),
    ("BD10",  "84114007",  "Heart failure",                 "Heart failure."),
]

CONTRAINDICATIONS = [
    ("metformin",      "N18",   "Risk of lactic acidosis — avoid when renal impairment is severe.",                    "ANSM/OpenFDA", "contraindicated"),
    ("warfarin",       "Z34",   "Teratogenic — causes fetal hemorrhage / embryopathy.",                                "OpenFDA",      "contraindicated"),
    ("warfarin",       "DB94",  "Anticoagulation worsens active bleeding.",                                            "OpenFDA",      "contraindicated"),
    ("spironolactone", "5C77",  "Potassium-sparing effect can worsen hyperkalemia.",                                   "OpenFDA",      "monitoring"),
    ("valproate",      "K76.9", "Hepatotoxicity — avoid in severe hepatic impairment.",                                "OpenFDA",      "contraindicated"),
    ("atorvastatin",   "K76.9", "Hepatic risk — avoid in active hepatic impairment.",                                  "OpenFDA",      "contraindicated"),
    ("simvastatin",    "K76.9", "Hepatic risk — avoid in active hepatic impairment.",                                  "OpenFDA",      "contraindicated"),
    ("ibuprofen",      "N18",   "NSAIDs can reduce renal perfusion; increased AKI risk.",                              "OpenFDA",      "dose_adjustment"),
    ("diclofenac",     "N18",   "NSAIDs can reduce renal perfusion; increased AKI risk.",                              "OpenFDA",      "dose_adjustment"),
    ("naproxen",       "N18",   "NSAIDs can reduce renal perfusion; increased AKI risk.",                              "OpenFDA",      "dose_adjustment"),
    ("glibenclamide",  "N18",   "Prolonged hypoglycemia risk with reduced renal clearance.",                           "OpenFDA",      "dose_adjustment"),
    ("ciprofloxacin",  "N18",   "Renal impairment reduces ciprofloxacin clearance; dose interval must be extended.",  "ANSM",         "dose_adjustment"),
    ("aspirin",        "K27",   "NSAIDs worsen peptic ulcer disease and increase risk of GI haemorrhage.",             "ANSM",         "contraindicated"),
    ("ibuprofen",      "K27",   "NSAIDs worsen peptic ulcer disease and increase risk of GI haemorrhage.",             "ANSM",         "contraindicated"),
    ("diclofenac",     "K27",   "NSAIDs worsen peptic ulcer disease and increase risk of GI haemorrhage.",             "ANSM",         "contraindicated"),
    ("naproxen",       "K27",   "NSAIDs worsen peptic ulcer disease and increase risk of GI haemorrhage.",             "ANSM",         "contraindicated"),
]

driver = connect()

# ── Drug nodes ────────────────────────────────────────────────────────────────
drugs_loaded = 0
for (inn, brand, brand_tn, brand_fr, atc, category, form,
     dose_adult, dose_elderly, dose_renal, dose_hepatic) in DRUGS:
    drug_id = f"{inn}::{brand}"
    driver.execute_query(
        """
        MATCH (m:Molecule {inn: $inn})
        MERGE (d:Drug {drug_id: $drug_id})
        SET d.brand_name              = $brand,
            d.brand_name_tn           = $brand_tn,
            d.brand_name_fr           = $brand_fr,
            d.atc_code                = $atc,
            d.therapeutic_category    = $category,
            d.dosage_form             = $form,
            d.dose_adult              = $dose_adult,
            d.dose_elderly            = $dose_elderly,
            d.dose_renal_impairment   = $dose_renal,
            d.dose_hepatic_impairment = $dose_hepatic
        MERGE (d)-[:BRAND_OF]->(m)
        """,
        inn=inn, drug_id=drug_id, brand=brand, brand_tn=brand_tn,
        brand_fr=brand_fr, atc=atc, category=category, form=form,
        dose_adult=dose_adult, dose_elderly=dose_elderly,
        dose_renal=dose_renal, dose_hepatic=dose_hepatic,
    )
    drugs_loaded += 1

print(f"Drug nodes loaded: {drugs_loaded}")

# ── DiseaseConcept nodes ───────────────────────────────────────────────────────
for icd11, snomed, name, desc in DISEASE_CONCEPTS:
    driver.execute_query(
        """
        MERGE (d:DiseaseConcept {icd11_code: $icd11})
        SET d.snomed_code    = $snomed,
            d.condition_name = $name,
            d.description    = $desc
        """,
        icd11=icd11, snomed=snomed, name=name, desc=desc,
    )

# ── CONTRAINDICATED_FOR edges ─────────────────────────────────────────────────
ci_loaded = 0
for inn, icd11, reason, source, severity in CONTRAINDICATIONS:
    driver.execute_query(
        """
        MERGE (dc:DiseaseConcept {icd11_code: $icd11})
        ON CREATE SET dc.condition_name = $reason
        """,
        icd11=icd11, reason=reason[:80],
    )
    driver.execute_query(
        """
        MATCH (m:Molecule {inn: $inn})
        MATCH (dc:DiseaseConcept {icd11_code: $icd11})
        MERGE (m)-[r:CONTRAINDICATED_FOR]->(dc)
        SET r.reason   = $reason,
            r.severity = $severity,
            r.source   = $source
        """,
        inn=inn, icd11=icd11, reason=reason, severity=severity, source=source,
    )
    ci_loaded += 1

print(f"CONTRAINDICATED_FOR edges: {ci_loaded}")

# ── AllergyGroup nodes ────────────────────────────────────────────────────────
allergy_groups_path = os.path.join(CLEAN_DIR, "allergy_groups_clean.csv")
if os.path.exists(allergy_groups_path):
    with open(allergy_groups_path, newline="", encoding="utf-8-sig") as f:
        allergy_groups = [(row["name"], row.get("description", "")) for row in csv.DictReader(f)]
else:
    allergy_groups = [
        ("Penicillins", "Penicillin beta-lactam antibiotics"),
        ("NSAIDs",      "Non-steroidal anti-inflammatory drugs"),
        ("Statins",     "HMG-CoA reductase inhibitors (statins)"),
    ]

for name, desc in allergy_groups:
    driver.execute_query(
        "MERGE (ag:AllergyGroup {name: $name}) SET ag.description = $desc",
        name=name, desc=desc,
    )

# ── CROSS_REACTS_WITH edges ───────────────────────────────────────────────────
cross_path = os.path.join(CLEAN_DIR, "allergy_cross_reactivities_clean.csv")
if os.path.exists(cross_path):
    with open(cross_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            driver.execute_query(
                """
                MATCH (a:AllergyGroup {name: $a}), (b:AllergyGroup {name: $b})
                MERGE (a)-[:CROSS_REACTS_WITH]->(b)
                """,
                a=row["group_a"], b=row["group_b"],
            )
            if row.get("direction") == "bidirectional":
                driver.execute_query(
                    """
                    MATCH (a:AllergyGroup {name: $a}), (b:AllergyGroup {name: $b})
                    MERGE (a)-[:CROSS_REACTS_WITH]->(b)
                    """,
                    a=row["group_b"], b=row["group_a"],
                )

# ── BELONGS_TO_ALLERGY_GROUP edges ────────────────────────────────────────────
drug_allergies_path = os.path.join(CLEAN_DIR, "drug_allergy_groups_clean.csv")
if os.path.exists(drug_allergies_path):
    with open(drug_allergies_path, newline="", encoding="utf-8-sig") as f:
        drug_allergies = [(row["canonical_inn"], row["allergy_group"]) for row in csv.DictReader(f)]
else:
    drug_allergies = [
        ("amoxicillin", "Penicillins"),
        ("aspirin",     "NSAIDs"),
        ("ibuprofen",   "NSAIDs"),
        ("diclofenac",  "NSAIDs"),
        ("naproxen",    "NSAIDs"),
        ("atorvastatin","Statins"),
        ("simvastatin", "Statins"),
    ]

for inn, group_name in drug_allergies:
    driver.execute_query(
        """
        MATCH (m:Molecule {inn: $inn})<-[:BRAND_OF]-(d:Drug)
        MATCH (ag:AllergyGroup {name: $group})
        MERGE (d)-[:BELONGS_TO_ALLERGY_GROUP]->(ag)
        """,
        inn=inn, group=group_name,
    )

driver.close()

print(f"Contraindication edges: {ci_loaded}")
print("AllergyGroup nodes, CROSS_REACTS_WITH and BELONGS_TO_ALLERGY_GROUP edges: done")
