"""
Graph loader 13 - DiseaseConcept names and the IS_A concept hierarchy.

Fixes three data defects that between them made contraindication checking fail
for every patient (found during Week 6 Milestone 4 sensitivity testing):

1. **Concepts named with their own code.** Around 30 DiseaseConcept nodes were
   created from patient records that carried only an ICD-11 code, so
   `condition_name` ended up as "BA00" rather than "Hypertension". Nothing can
   match those by name.

2. **Concepts named with a reason sentence.** The contraindication source wrote
   the *reason* into the name field, leaving concepts called
   "Anticoagulation worsens active bleeding." instead of "Active bleeding".

3. **No hierarchy.** CONTRAINDICATED_FOR edges point at general concepts
   ("Renal impairment", N18) while patients carry specific ones
   ("Chronic kidney disease stage 4", GB61). With no link between them, a
   metformin prescription for a CKD-4 patient raised no contraindication - a
   false negative on a lactic-acidosis risk.

The IS_A edges are deliberately conservative: only relationships that are
unambiguously true (a subtype, or the same disease under a second code).
Reading them is `(specific)-[:IS_A]->(general)`.

Run:  python knowledge_base/graph_loaders/load_disease_hierarchy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect

# ---------------------------------------------------------------------------
# Proper names for concepts that arrived carrying only an ICD-11 code.
# Sourced from the PostgreSQL disease_concepts table, which holds the curated
# clinical names for these codes.
# ---------------------------------------------------------------------------
CONCEPT_NAMES = [
    ("1A00",  "Bacterial infection"),
    ("1B10",  "Tuberculosis"),
    ("1F20",  "Fungal infection"),
    ("1F23",  "Candidiasis"),
    ("4A40",  "Autoimmune disease"),
    ("5A00",  "Hypothyroidism"),
    ("5A10",  "Type 1 diabetes mellitus"),
    ("5A11",  "Type 2 diabetes mellitus"),
    ("5C58",  "Hyperuricaemia"),
    ("5C80",  "Hypercholesterolaemia"),
    ("6A20",  "Schizophrenia"),
    ("6A60",  "Bipolar disorder"),
    ("6A70",  "Major depressive disorder"),
    ("6B00",  "Anxiety disorder"),
    ("6B20",  "Obsessive-compulsive disorder"),
    ("8A00",  "Parkinson disease"),
    ("BA00",  "Hypertension"),
    ("BA41",  "Myocardial infarction"),
    ("BA80",  "Ischaemic heart disease"),
    ("BB01",  "Pulmonary arterial hypertension"),
    ("BC80",  "Atrial fibrillation"),
    ("BC81",  "Supraventricular tachycardia"),
    ("BC82",  "Ventricular tachycardia"),
    ("BD71",  "Venous thromboembolism"),
    ("CA40",  "Community-acquired pneumonia"),
    ("DA41",  "Peptic ulcer disease"),
    ("DA42",  "Helicobacter pylori infection"),
    ("DA43",  "Gastro-oesophageal reflux disease"),
    ("EA90",  "Psoriasis"),
    ("FA20",  "Rheumatoid arthritis"),
    ("FA92",  "Gout"),
    ("GC08",  "Urinary tract infection"),
    ("HA00",  "Erectile dysfunction"),
    ("MG30",  "Pain"),
    ("QA01",  "Transplantation procedure"),
    ("QA21",  "Oral contraception"),

    # Concepts whose name held a reason sentence rather than a condition.
    ("DB94",  "Active bleeding"),
    ("5C77",  "Hyperkalaemia"),
    ("N18.9", "Chronic kidney disease"),
]

# ---------------------------------------------------------------------------
# (specific_code, general_code, note)
#
# Only unambiguous relationships. Each one is either a clinical subtype or the
# same disease recorded under a second code.
# ---------------------------------------------------------------------------
CONCEPT_HIERARCHY = [
    ("GB61",  "N18", "CKD stage 4 is severe renal impairment"),
    ("N18.9", "N18", "chronic kidney disease is renal impairment"),
    ("DA41",  "K27", "same disease, recorded under two codes"),
]


def load():
    driver = connect()
    renamed = skipped = 0
    linked = missing = 0

    try:
        # --- 1. Backfill names, only where the name is still the bare code ---
        for icd, name in CONCEPT_NAMES:
            result = driver.execute_query(
                """
                MATCH (dc:DiseaseConcept {icd11_code: $icd})
                WHERE dc.condition_name = $icd
                   OR dc.condition_name IS NULL
                   OR dc.condition_name ENDS WITH '.'   // a reason sentence, not a name
                SET dc.condition_name = $name
                RETURN dc.icd11_code AS icd
                """,
                icd=icd, name=name,
            )
            if result.records:
                renamed += 1
                print(f"  renamed {icd:<8} -> {name}")
            else:
                skipped += 1

        # --- 2. Concept hierarchy -------------------------------------------
        for specific, general, note in CONCEPT_HIERARCHY:
            result = driver.execute_query(
                """
                MATCH (s:DiseaseConcept {icd11_code: $specific})
                MATCH (g:DiseaseConcept {icd11_code: $general})
                MERGE (s)-[r:IS_A]->(g)
                SET r.note = $note
                RETURN s.condition_name AS s_name, g.condition_name AS g_name
                """,
                specific=specific, general=general, note=note,
            )
            if result.records:
                rec = result.records[0]
                linked += 1
                print(f"  IS_A    {rec['s_name']} -> {rec['g_name']}  ({note})")
            else:
                missing += 1
                print(f"  SKIP    {specific} -> {general}: concept(s) not in graph")

        # --- 3. Normalise dashes in reason text ------------------------------
        # The reasons carry em/en dashes (U+2014, U+2013). They are valid text,
        # but this project's console output is cp1252 and renders them as "?".
        # Reason text is shown to the pharmacist inside reasoning chains, so it
        # follows the same ASCII rule as the rest of the user-facing strings.
        result = driver.execute_query(
            """
            MATCH (:Molecule)-[r:CONTRAINDICATED_FOR]->(:DiseaseConcept)
            WHERE r.reason CONTAINS '—' OR r.reason CONTAINS '–'
            SET r.reason = replace(replace(r.reason, '—', '-'), '–', '-')
            RETURN count(r) AS n
            """
        )
        dashes = result.records[0]["n"] if result.records else 0

    finally:
        driver.close()

    print()
    print(f"  names:     {renamed} set, {skipped} already correct")
    print(f"  hierarchy: {linked} IS_A edge(s), {missing} skipped")
    print(f"  reasons:   {dashes} dash character(s) normalised to ASCII")
    return renamed, linked


if __name__ == "__main__":
    print("Loading disease concept names + hierarchy...")
    load()
