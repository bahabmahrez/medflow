"""
Graph loader 11 — INDICATED_FOR edges (drug indications).

Mirrors knowledge_base/DB_loaders/load_treats.py.
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect

INDICATIONS = [
    ("warfarin",        "Venous thromboembolism prevention",              "BD71", "A"),
    ("warfarin",        "Atrial fibrillation stroke prevention",          "BC80", "A"),
    ("warfarin",        "Mechanical heart valve prophylaxis",             "BD10", "A"),
    ("heparin",         "Venous thromboembolism treatment",               "BD71", "A"),
    ("heparin",         "Acute coronary syndrome",                        "BA80", "A"),
    ("aspirin",         "Secondary cardiovascular prevention",            "BA80", "A"),
    ("aspirin",         "Antiplatelet therapy",                           "BA80", "A"),
    ("clopidogrel",     "Antiplatelet therapy",                           "BA80", "A"),
    ("clopidogrel",     "Acute coronary syndrome",                        "BA80", "A"),
    ("atorvastatin",    "Hypercholesterolaemia",                          "5C80", "A"),
    ("atorvastatin",    "Cardiovascular risk reduction",                  "BA80", "A"),
    ("simvastatin",     "Hypercholesterolaemia",                          "5C80", "A"),
    ("simvastatin",     "Cardiovascular risk reduction",                  "BA80", "A"),
    ("metformin",       "Type 2 diabetes mellitus",                       "5A11", "A"),
    ("glibenclamide",   "Type 2 diabetes mellitus",                       "5A11", "A"),
    ("insulin glargine","Type 1 diabetes mellitus",                       "5A10", "A"),
    ("insulin glargine","Type 2 diabetes mellitus",                       "5A11", "A"),
    ("enalapril",       "Hypertension",                                   "BA00", "A"),
    ("enalapril",       "Heart failure",                                  "BD10", "A"),
    ("ramipril",        "Hypertension",                                   "BA00", "A"),
    ("ramipril",        "Post-myocardial infarction",                     "BA41", "A"),
    ("losartan",        "Hypertension",                                   "BA00", "A"),
    ("losartan",        "Diabetic nephropathy",                           "5A11", "A"),
    ("furosemide",      "Heart failure",                                  "BD10", "A"),
    ("furosemide",      "Oedema",                                         "BD10", "A"),
    ("spironolactone",  "Heart failure",                                  "BD10", "A"),
    ("spironolactone",  "Hypertension",                                   "BA00", "B"),
    ("amlodipine",      "Hypertension",                                   "BA00", "A"),
    ("amlodipine",      "Stable angina",                                  "BA80", "A"),
    ("verapamil",       "Hypertension",                                   "BA00", "A"),
    ("verapamil",       "Supraventricular tachycardia",                   "BC81", "A"),
    ("diltiazem",       "Hypertension",                                   "BA00", "A"),
    ("diltiazem",       "Stable angina",                                  "BA80", "A"),
    ("amiodarone",      "Ventricular tachycardia",                        "BC82", "A"),
    ("amiodarone",      "Atrial fibrillation",                            "BC80", "A"),
    ("digoxin",         "Heart failure",                                  "BD10", "A"),
    ("digoxin",         "Atrial fibrillation rate control",               "BC80", "A"),
    ("amoxicillin",     "Bacterial infections",                           "1A00", "A"),
    ("amoxicillin",     "Community-acquired pneumonia",                   "CA40", "A"),
    ("ciprofloxacin",   "Urinary tract infections",                       "GC08", "A"),
    ("ciprofloxacin",   "Respiratory tract infections",                   "CA40", "A"),
    ("clarithromycin",  "Community-acquired pneumonia",                   "CA40", "A"),
    ("clarithromycin",  "H. pylori eradication",                          "DA42", "A"),
    ("metronidazole",   "Anaerobic bacterial infections",                 "1A00", "A"),
    ("metronidazole",   "H. pylori eradication",                          "DA42", "A"),
    ("isoniazid",       "Tuberculosis",                                   "1B10", "A"),
    ("rifampicin",      "Tuberculosis",                                   "1B10", "A"),
    ("omeprazole",      "Gastro-oesophageal reflux disease",              "DA43", "A"),
    ("omeprazole",      "Peptic ulcer disease",                           "DA41", "A"),
    ("omeprazole",      "H. pylori eradication",                          "DA42", "A"),
    ("tacrolimus",      "Solid organ transplant rejection prevention",     "QA01", "A"),
    ("cyclosporine",    "Solid organ transplant rejection prevention",     "QA01", "A"),
    ("cyclosporine",    "Rheumatoid arthritis",                           "FA20", "B"),
    ("azathioprine",    "Autoimmune conditions",                          "4A40", "A"),
    ("azathioprine",    "Solid organ transplant",                         "QA01", "A"),
    ("methotrexate",    "Rheumatoid arthritis",                           "FA20", "A"),
    ("methotrexate",    "Psoriasis",                                      "EA90", "A"),
    ("fluoxetine",      "Major depressive disorder",                      "6A70", "A"),
    ("fluoxetine",      "Obsessive-compulsive disorder",                  "6B20", "A"),
    ("sertraline",      "Major depressive disorder",                      "6A70", "A"),
    ("sertraline",      "Anxiety disorders",                              "6B00", "A"),
    ("haloperidol",     "Schizophrenia",                                  "6A20", "A"),
    ("haloperidol",     "Acute psychosis",                                "6A20", "A"),
    ("risperidone",     "Schizophrenia",                                  "6A20", "A"),
    ("risperidone",     "Bipolar disorder",                               "6A60", "A"),
    ("quetiapine",      "Schizophrenia",                                  "6A20", "A"),
    ("quetiapine",      "Bipolar disorder",                               "6A60", "A"),
    ("lithium",         "Bipolar disorder",                               "6A60", "A"),
    ("lithium",         "Mania prevention",                               "6A60", "A"),
    ("carbamazepine",   "Epilepsy",                                       "8A60", "A"),
    ("carbamazepine",   "Bipolar disorder",                               "6A60", "B"),
    ("valproate",       "Epilepsy",                                       "8A60", "A"),
    ("valproate",       "Bipolar disorder",                               "6A60", "A"),
    ("phenobarbital",   "Epilepsy",                                       "8A60", "A"),
    ("levodopa",        "Parkinson disease",                              "8A00", "A"),
    ("tramadol",        "Moderate to severe pain",                        "MG30", "A"),
    ("ibuprofen",       "Pain and inflammation",                          "MG30", "A"),
    ("ibuprofen",       "Rheumatoid arthritis",                           "FA20", "A"),
    ("diclofenac",      "Pain and inflammation",                          "MG30", "A"),
    ("naproxen",        "Pain and inflammation",                          "MG30", "A"),
    ("allopurinol",     "Gout",                                           "FA92", "A"),
    ("allopurinol",     "Hyperuricaemia",                                 "5C58", "A"),
    ("colchicine",      "Acute gout",                                     "FA92", "A"),
    ("levothyroxine",   "Hypothyroidism",                                 "5A00", "A"),
    ("ethinylestradiol","Contraception",                                  "QA21", "A"),
    ("sildenafil",      "Erectile dysfunction",                           "HA00", "A"),
    ("sildenafil",      "Pulmonary arterial hypertension",                "BB01", "A"),
    ("fluconazole",     "Fungal infections",                              "1F20", "A"),
    ("fluconazole",     "Candidiasis",                                    "1F23", "A"),
]

driver = connect()
inserted = skipped = 0

# Ensure all required ICD-11 codes exist as DiseaseConcept nodes
icd_needed = {row[2] for row in INDICATIONS}
for icd in icd_needed:
    driver.execute_query(
        "MERGE (dc:DiseaseConcept {icd11_code: $icd}) ON CREATE SET dc.condition_name = $icd",
        icd=icd,
    )

for inn, indication, icd, evidence in INDICATIONS:
    result = driver.execute_query(
        """
        MATCH (m:Molecule {inn: $inn}), (dc:DiseaseConcept {icd11_code: $icd})
        MERGE (m)-[r:INDICATED_FOR]->(dc)
        ON CREATE SET r.indication_name = $indication, r.evidence_level = $evidence, r.source = 'drugbank'
        RETURN 1
        """,
        inn=inn, icd=icd, indication=indication, evidence=evidence,
    )
    if result.records:
        inserted += 1
    else:
        skipped += 1

driver.close()
print(f"INDICATED_FOR edges: {inserted} inserted, {skipped} skipped")
