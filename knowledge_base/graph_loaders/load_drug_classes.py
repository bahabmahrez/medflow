"""
Graph loader 7 — DrugClass nodes, MEMBER_OF edges, CLASS_INTERACTS_WITH edges.

Mirrors knowledge_base/DB_loaders/load_drug_classes.py.
Sources: hardcoded MOLECULE_CLASSES + edges.csv from DrugBank + hardcoded extra edges.
"""
import csv, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, ordered_inns

BASE    = os.path.dirname(os.path.abspath(__file__))
EDGES_CSV = os.path.join(BASE, "../graph/edges.csv")

SEVERITY_MAP = {
    "CONTRAINDICATED": "contre_indique",
    "MAJOR":           "deconseillee",
    "MODERATE":        "precaution_emploi",
    "MINOR":           "a_prendre_en_compte",
}

MOLECULE_CLASSES: dict[str, list[str]] = {
    "warfarin":         ["Vitamin K Antagonist"],
    "heparin":          ["Anticoagulant"],
    "aspirin":          ["Nonsteroidal Anti-Inflammatory Drug", "Platelet Aggregation Inhibitor"],
    "clopidogrel":      ["Platelet Aggregation Inhibitor"],
    "metformin":        ["Biguanide"],
    "glibenclamide":    ["Sulfonylurea"],
    "insulin glargine": ["Insulin"],
    "enalapril":        ["ACE Inhibitor"],
    "ramipril":         ["ACE Inhibitor"],
    "amlodipine":       ["Calcium Channel Blocker"],
    "verapamil":        ["Calcium Channel Blocker"],
    "diltiazem":        ["Calcium Channel Blocker"],
    "furosemide":       ["Loop Diuretic"],
    "spironolactone":   ["Potassium-Sparing Diuretic"],
    "digoxin":          ["Cardiac Glycoside"],
    "atorvastatin":     ["HMG CoA Reductase Inhibitor"],
    "simvastatin":      ["HMG CoA Reductase Inhibitor"],
    "amiodarone":       ["Antiarrhythmic"],
    "losartan":         ["Angiotensin Receptor Blocker"],
    "ibuprofen":        ["Nonsteroidal Anti-Inflammatory Drug"],
    "diclofenac":       ["Nonsteroidal Anti-Inflammatory Drug"],
    "naproxen":         ["Nonsteroidal Anti-Inflammatory Drug"],
    "prednisolone":     ["Corticosteroid"],
    "amoxicillin":      ["Penicillin Antibiotic"],
    "ciprofloxacin":    ["Fluoroquinolone Antibiotic"],
    "metronidazole":    ["Nitroimidazole Antibiotic"],
    "clarithromycin":   ["Macrolide Antibiotic"],
    "fluconazole":      ["Azole Antifungal"],
    "rifampicin":       ["Rifamycin Antibiotic"],
    "isoniazid":        ["Antitubercular Agent"],
    "carbamazepine":    ["Anti-Epileptic Agent"],
    "valproate":        ["Anti-Epileptic Agent", "Mood Stabilizer"],
    "fluoxetine":       ["Selective Serotonin Reuptake Inhibitor"],
    "sertraline":       ["Selective Serotonin Reuptake Inhibitor"],
    "tramadol":         ["Opioid Analgesic"],
    "phenobarbital":    ["Anti-Epileptic Agent", "Barbiturate"],
    "levodopa":         ["Dopamine Precursor"],
    "lithium":          ["Mood Stabilizer"],
    "haloperidol":      ["Typical Antipsychotic"],
    "risperidone":      ["Atypical Antipsychotic"],
    "quetiapine":       ["Atypical Antipsychotic"],
    "omeprazole":       ["Proton Pump Inhibitor"],
    "methotrexate":     ["Antimetabolite"],
    "azathioprine":     ["Immunosuppressant"],
    "tacrolimus":       ["Calcineurin Inhibitor Immunosuppressant"],
    "cyclosporine":     ["Calcineurin Inhibitor Immunosuppressant"],
    "allopurinol":      ["Xanthine Oxidase Inhibitor"],
    "colchicine":       ["Gout Suppressant"],
    "levothyroxine":    ["Thyroid Hormone"],
    "ethinylestradiol": ["Estrogen"],
    "sildenafil":       ["Phosphodiesterase 5 Inhibitor"],
}

CLASS_ATC: dict[str, str] = {
    "Vitamin K Antagonist":                   "B01AA",
    "Anticoagulant":                          "B01AB",
    "Platelet Aggregation Inhibitor":         "B01AC",
    "Biguanide":                              "A10BA",
    "Sulfonylurea":                           "A10BB",
    "Insulin":                                "A10AE",
    "ACE Inhibitor":                          "C09AA",
    "Calcium Channel Blocker":                "C08CA",
    "Loop Diuretic":                          "C03CA",
    "Potassium-Sparing Diuretic":             "C03DA",
    "Cardiac Glycoside":                      "C01AA",
    "HMG CoA Reductase Inhibitor":            "C10AA",
    "Antiarrhythmic":                         "C01BD",
    "Angiotensin Receptor Blocker":           "C09CA",
    "Nonsteroidal Anti-Inflammatory Drug":    "M01AE",
    "Corticosteroid":                         "H02AB",
    "Penicillin Antibiotic":                  "J01CA",
    "Fluoroquinolone Antibiotic":             "J01MA",
    "Nitroimidazole Antibiotic":              "J01XD",
    "Macrolide Antibiotic":                   "J01FA",
    "Azole Antifungal":                       "J02AC",
    "Rifamycin Antibiotic":                   "J04AB",
    "Antitubercular Agent":                   "J04AC",
    "Anti-Epileptic Agent":                   "N03AF",
    "Mood Stabilizer":                        "N05AN",
    "Selective Serotonin Reuptake Inhibitor": "N06AB",
    "Opioid Analgesic":                       "N02AX",
    "Barbiturate":                            "N03AA",
    "Dopamine Precursor":                     "N04BA",
    "Typical Antipsychotic":                  "N05AD",
    "Atypical Antipsychotic":                 "N05AX",
    "Proton Pump Inhibitor":                  "A02BC",
    "Antimetabolite":                         "L01BA",
    "Immunosuppressant":                      "L04AX",
    "Calcineurin Inhibitor Immunosuppressant":"L04AD",
    "Xanthine Oxidase Inhibitor":             "M04AA",
    "Gout Suppressant":                       "M04AC",
    "Thyroid Hormone":                        "H03AA",
    "Estrogen":                               "G03CA",
    "Phosphodiesterase 5 Inhibitor":          "G04BE",
}

relevant_classes: set[str] = {c for classes in MOLECULE_CLASSES.values() for c in classes}

driver = connect()

# ── Step 1: DrugClass nodes ───────────────────────────────────────────────────
for class_name in sorted(relevant_classes):
    atc_code = CLASS_ATC.get(class_name) or (
        "EPC_" + re.sub(r"[^A-Z0-9]", "_", class_name.upper())[:20]
    )
    driver.execute_query(
        """
        MERGE (c:DrugClass {atc_code: $atc})
        SET c.class_name = $name
        """,
        atc=atc_code, name=class_name,
    )

print(f"DrugClass nodes: {len(relevant_classes)}")

# ── Step 2: MEMBER_OF edges ───────────────────────────────────────────────────
members_loaded = 0
for inn, classes in MOLECULE_CLASSES.items():
    for class_name in classes:
        atc_code = CLASS_ATC.get(class_name) or (
            "EPC_" + re.sub(r"[^A-Z0-9]", "_", class_name.upper())[:20]
        )
        result = driver.execute_query(
            """
            MATCH (m:Molecule {inn: $inn}), (c:DrugClass {atc_code: $atc})
            MERGE (m)-[:MEMBER_OF]->(c)
            RETURN 1
            """,
            inn=inn, atc=atc_code,
        )
        if result.records:
            members_loaded += 1
        else:
            print(f"  SKIP {inn} -> {class_name}: molecule or class not found")

print(f"MEMBER_OF edges: {members_loaded}")

# ── Step 3: CLASS_INTERACTS_WITH edges from edges.csv ─────────────────────────
edges_loaded = edges_skipped = 0

with open(EDGES_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        src = row["source"].strip()
        tgt = row["target"].strip()

        if src not in relevant_classes or tgt not in relevant_classes:
            edges_skipped += 1
            continue

        atc_a = CLASS_ATC.get(src) or ("EPC_" + re.sub(r"[^A-Z0-9]", "_", src.upper())[:20])
        atc_b = CLASS_ATC.get(tgt) or ("EPC_" + re.sub(r"[^A-Z0-9]", "_", tgt.upper())[:20])
        severity = SEVERITY_MAP.get(row["severity"].strip().upper(), "a_prendre_en_compte")
        shared   = row.get("shared_drugs", "").strip()[:500] or None

        # Canonical direction: alphabetically smaller ATC first
        if atc_a > atc_b:
            atc_a, atc_b = atc_b, atc_a

        driver.execute_query(
            """
            MATCH (a:DrugClass {atc_code: $atc_a}), (b:DrugClass {atc_code: $atc_b})
            MERGE (a)-[r:CLASS_INTERACTS_WITH]->(b)
            ON CREATE SET r.severity = $severity, r.clinical_effect = $shared
            ON MATCH SET
                r.severity = CASE WHEN r.severity < $severity THEN $severity ELSE r.severity END
            """,
            atc_a=atc_a, atc_b=atc_b, severity=severity, shared=shared,
        )
        edges_loaded += 1

print(f"CLASS_INTERACTS_WITH from edges.csv: {edges_loaded}  (skipped: {edges_skipped})")

# ── Step 4: hardcoded extra edges ─────────────────────────────────────────────
EXTRA_EDGES = [
    ("Nonsteroidal Anti-Inflammatory Drug", "Vitamin K Antagonist",
     "contre_indique", "pharmacodynamic",
     "NSAIDs inhibit COX-1 impairing platelet function; additive bleeding risk with anticoagulants.",
     "Avoid combination. If necessary, add gastroprotection and monitor INR closely."),
]

for class_a, class_b, severity, mechanism, clinical_effect, management in EXTRA_EDGES:
    atc_a = CLASS_ATC.get(class_a)
    atc_b = CLASS_ATC.get(class_b)
    if not atc_a or not atc_b:
        print(f"  SKIP extra edge {class_a} <-> {class_b}: class not found")
        continue
    if atc_a > atc_b:
        atc_a, atc_b = atc_b, atc_a
    result = driver.execute_query(
        """
        MATCH (a:DrugClass {atc_code: $atc_a}), (b:DrugClass {atc_code: $atc_b})
        MERGE (a)-[r:CLASS_INTERACTS_WITH]->(b)
        ON CREATE SET
            r.severity = $severity, r.mechanism_type = $mechanism,
            r.clinical_effect = $effect, r.management = $mgmt
        ON MATCH SET
            r.severity = $severity, r.clinical_effect = $effect, r.management = $mgmt
        RETURN 1
        """,
        atc_a=atc_a, atc_b=atc_b, severity=severity, mechanism=mechanism,
        effect=clinical_effect, mgmt=management,
    )
    if result.records:
        print(f"  EXTRA  {class_a} <-> {class_b} -> {severity}")

driver.close()
print(f"\nTotal DrugClass nodes: {len(relevant_classes)}")
