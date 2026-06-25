"""
Load drug class hierarchy, molecule memberships, and class-level interactions.

Sources:
  - Drug class names: DrugBank Established Pharmacological Class (EPC) taxonomy
    as used in knowledge_base/graph/nodes.csv and edges.csv
  - Molecule → class mapping: WHO ATC codes (already in drugs table) + hardcoded
    for molecules without a drug record
  - Class interactions: knowledge_base/graph/edges.csv (2,174 edges from DrugBank)

Tables populated:
  drug_classes          — EPC class nodes with pseudo-ATC codes
  drug_class_members    — which of our 50 molecules belong to which class
  class_interactions    — severity edges between classes (filtered to relevant classes)
"""

import csv
import os
import re
import psycopg2

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)
cur = conn.cursor()

BASE = os.path.dirname(os.path.abspath(__file__))
NODES_CSV = os.path.join(BASE, "../graph/nodes.csv")
EDGES_CSV = os.path.join(BASE, "../graph/edges.csv")

# ── Severity normalisation ───────────────────────────────────────────────────
# edges.csv uses DrugBank severity names; map to our ANSM-style values
SEVERITY_MAP = {
    "CONTRAINDICATED": "contre_indique",
    "MAJOR":           "deconseillee",
    "MODERATE":        "precaution_emploi",
    "MINOR":           "a_prendre_en_compte",
}

# ── Molecule → EPC class name(s) ─────────────────────────────────────────────
# Derived from WHO ATC + DrugBank EPC taxonomy. Molecules may belong to
# multiple classes (e.g. aspirin is both an NSAID and a platelet inhibitor).
MOLECULE_CLASSES: dict[str, list[str]] = {
    # Anticoagulants / antiplatelets
    "warfarin":         ["Vitamin K Antagonist"],
    "heparin":          ["Anticoagulant"],
    "aspirin":          ["Nonsteroidal Anti-Inflammatory Drug",
                         "Platelet Aggregation Inhibitor"],
    "clopidogrel":      ["Platelet Aggregation Inhibitor"],

    # Antidiabetics
    "metformin":        ["Biguanide"],
    "glibenclamide":    ["Sulfonylurea"],
    "insulin glargine": ["Insulin"],

    # Cardiovascular
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

    # Anti-inflammatory
    "ibuprofen":        ["Nonsteroidal Anti-Inflammatory Drug"],
    "diclofenac":       ["Nonsteroidal Anti-Inflammatory Drug"],
    "naproxen":         ["Nonsteroidal Anti-Inflammatory Drug"],
    "prednisolone":     ["Corticosteroid"],

    # Antibiotics / antifungals / antimycobacterials
    "amoxicillin":      ["Penicillin Antibiotic"],
    "ciprofloxacin":    ["Fluoroquinolone Antibiotic"],
    "metronidazole":    ["Nitroimidazole Antibiotic"],
    "clarithromycin":   ["Macrolide Antibiotic"],
    "fluconazole":      ["Azole Antifungal"],
    "rifampicin":       ["Rifamycin Antibiotic"],
    "isoniazid":        ["Antitubercular Agent"],

    # Neurological / psychiatric
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

    # Gastric
    "omeprazole":       ["Proton Pump Inhibitor"],

    # Immunosuppressants / oncology
    "methotrexate":     ["Antimetabolite"],
    "azathioprine":     ["Immunosuppressant"],
    "tacrolimus":       ["Calcineurin Inhibitor Immunosuppressant"],
    "cyclosporine":     ["Calcineurin Inhibitor Immunosuppressant"],

    # Rheumatology
    "allopurinol":      ["Xanthine Oxidase Inhibitor"],
    "colchicine":       ["Gout Suppressant"],

    # Endocrinology
    "levothyroxine":    ["Thyroid Hormone"],
    "ethinylestradiol": ["Estrogen"],

    # Other
    "sildenafil":       ["Phosphodiesterase 5 Inhibitor"],
}

# ATC-style code for each EPC class (used as unique key in drug_classes.atc_code)
# Real WHO ATC codes where available, otherwise a readable slug
CLASS_ATC: dict[str, str] = {
    "Vitamin K Antagonist":                  "B01AA",
    "Anticoagulant":                         "B01AB",
    "Platelet Aggregation Inhibitor":        "B01AC",
    "Biguanide":                             "A10BA",
    "Sulfonylurea":                          "A10BB",
    "Insulin":                               "A10AE",
    "ACE Inhibitor":                         "C09AA",
    "Calcium Channel Blocker":               "C08CA",
    "Loop Diuretic":                         "C03CA",
    "Potassium-Sparing Diuretic":            "C03DA",
    "Cardiac Glycoside":                     "C01AA",
    "HMG CoA Reductase Inhibitor":           "C10AA",
    "Antiarrhythmic":                        "C01BD",
    "Angiotensin Receptor Blocker":          "C09CA",
    "Nonsteroidal Anti-Inflammatory Drug":   "M01AE",
    "Corticosteroid":                        "H02AB",
    "Penicillin Antibiotic":                 "J01CA",
    "Fluoroquinolone Antibiotic":            "J01MA",
    "Nitroimidazole Antibiotic":             "J01XD",
    "Macrolide Antibiotic":                  "J01FA",
    "Azole Antifungal":                      "J02AC",
    "Rifamycin Antibiotic":                  "J04AB",
    "Antitubercular Agent":                  "J04AC",
    "Anti-Epileptic Agent":                  "N03AF",
    "Mood Stabilizer":                       "N05AN",
    "Selective Serotonin Reuptake Inhibitor":"N06AB",
    "Opioid Analgesic":                      "N02AX",
    "Barbiturate":                           "N03AA",
    "Dopamine Precursor":                    "N04BA",
    "Typical Antipsychotic":                 "N05AD",
    "Atypical Antipsychotic":                "N05AX",
    "Proton Pump Inhibitor":                 "A02BC",
    "Antimetabolite":                        "L01BA",
    "Immunosuppressant":                     "L04AX",
    "Calcineurin Inhibitor Immunosuppressant":"L04AD",
    "Xanthine Oxidase Inhibitor":            "M04AA",
    "Gout Suppressant":                      "M04AC",
    "Thyroid Hormone":                       "H03AA",
    "Estrogen":                              "G03CA",
    "Phosphodiesterase 5 Inhibitor":         "G04BE",
}

# ── Step 1: collect relevant class names ──────────────────────────────────────
relevant_classes: set[str] = set()
for classes in MOLECULE_CLASSES.values():
    relevant_classes.update(classes)

# ── Step 2: insert drug_classes ───────────────────────────────────────────────
class_id_map: dict[str, int] = {}

for class_name in sorted(relevant_classes):
    atc_code = CLASS_ATC.get(class_name)
    if not atc_code:
        # Generate a stable slug for classes without a WHO ATC code
        atc_code = "EPC_" + re.sub(r"[^A-Z0-9]", "_", class_name.upper())[:20]

    cur.execute("""
        INSERT INTO drug_classes (atc_code, class_name)
        VALUES (%s, %s)
        ON CONFLICT (atc_code) DO UPDATE SET class_name = EXCLUDED.class_name
        RETURNING id
    """, (atc_code, class_name))
    class_id_map[class_name] = cur.fetchone()[0]

print(f"drug_classes inserted/updated: {len(class_id_map)}")

# ── Step 3: insert drug_class_members ─────────────────────────────────────────
members_loaded = 0
for inn, classes in MOLECULE_CLASSES.items():
    cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
    mol = cur.fetchone()
    if not mol:
        print(f"  SKIP {inn}: molecule not in DB")
        continue
    mol_id = mol[0]
    for class_name in classes:
        class_id = class_id_map.get(class_name)
        if not class_id:
            continue
        cur.execute("""
            INSERT INTO drug_class_members (molecule_id, drug_class_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (mol_id, class_id))
        members_loaded += 1

print(f"drug_class_members inserted: {members_loaded}")

# ── Step 4: insert class_interactions from edges.csv ─────────────────────────
edges_loaded = 0
edges_skipped = 0

with open(EDGES_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        src = row["source"].strip()
        tgt = row["target"].strip()

        # Only load edges where BOTH classes are relevant to our 50 drugs
        if src not in class_id_map or tgt not in class_id_map:
            edges_skipped += 1
            continue

        severity = SEVERITY_MAP.get(row["severity"].strip().upper(), "a_prendre_en_compte")
        shared   = row.get("shared_drugs", "").strip()[:500]

        cur.execute("""
            INSERT INTO class_interactions
                (class_a_id, class_b_id, severity, clinical_effect)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (class_id_map[src], class_id_map[tgt], severity, shared or None))
        edges_loaded += 1

print(f"class_interactions inserted: {edges_loaded}  (skipped: {edges_skipped})")

# ── Hardcoded edges missing from edges.csv ────────────────────────────────────
# NSAID ↔ Vitamin K Antagonist: not in DrugBank edges.csv but well-established
# (additive bleeding risk, ANSM contre_indique). Required for stress test 1.
EXTRA_EDGES = [
    ("Nonsteroidal Anti-Inflammatory Drug", "Vitamin K Antagonist",
     "contre_indique", "pharmacodynamic",
     "NSAIDs inhibit COX-1 impairing platelet function; additive bleeding risk with anticoagulants.",
     "Avoid combination. If necessary, add gastroprotection and monitor INR closely."),
]

for (class_a, class_b, severity, mechanism, clinical_effect, management) in EXTRA_EDGES:
    a_id = class_id_map.get(class_a)
    b_id = class_id_map.get(class_b)
    if not a_id or not b_id:
        print(f"  SKIP extra edge {class_a} <-> {class_b}: class not found")
        continue
    cur.execute("""
        INSERT INTO class_interactions
            (class_a_id, class_b_id, severity, mechanism_type, clinical_effect, management)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (min(a_id, b_id), max(a_id, b_id), severity, mechanism, clinical_effect, management))
    if cur.rowcount:
        print(f"  EXTRA  {class_a} <-> {class_b} -> {severity}")

conn.commit()

# ── Summary ───────────────────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM drug_classes")
print(f"\nTotal drug_classes:       {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM drug_class_members")
print(f"Total drug_class_members: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM class_interactions")
print(f"Total class_interactions: {cur.fetchone()[0]}")

cur.close()
conn.close()
