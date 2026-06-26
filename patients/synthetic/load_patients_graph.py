"""
Graph patient loader — 20 trap patients + 30 regular patients = 50 total.

Creates Patient nodes and:
  (:Patient)-[:TAKES {dose_mg, frequency, start_date}]->(:Drug)
  (:Patient)-[:HAS_CONDITION {onset_date}]->(:DiseaseConcept)
  (:Patient)-[:ALLERGIC_TO {reaction_type, documented_at}]->(:AllergyGroup)
  (:Patient)-[:HAS_LAB {loinc_code, test_name, value, unit, collected_at}]->(:LabResult)

Key labs also stored as Patient properties (creatinine_umol_L, inr) so Cypher
contraindication queries can filter without traversing LabResult nodes.

Re-runnable: deletes all synthetic patients before re-inserting.
"""
import os, sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../knowledge_base/graph_loaders"))
from _neo4j import connect

LOINC_CREATININE = "2160-0"
LOINC_INR        = "6301-6"

PREFERRED_BRANDS = {
    "warfarin":        "Coumadin",    "aspirin":        "Aspégic",
    "metformin":       "Glucophage",  "atorvastatin":   "Tahor",
    "simvastatin":     "Zocor",       "amoxicillin":    "Clamoxyl",
    "ciprofloxacin":   "Ciflox",      "clarithromycin": "Zeclar",
    "fluconazole":     "Triflucan",   "fluoxetine":     "Prozac",
    "tramadol":        "Topalgic",    "ramipril":       "Triatec",
    "amlodipine":      "Amlor",       "furosemide":     "Lasilix",
    "spironolactone":  "Aldactone",   "digoxin":        "Digoxine",
    "clopidogrel":     "Plavix",      "sertraline":     "Zoloft",
    "omeprazole":      "Mopral",      "ibuprofen":      "Brufen",
    "prednisolone":    "Solupred",
    # Extra drugs needed for new trap scenarios
    "amiodarone":      "Cordarone",
    "rifampicin":      "Rifadine",
    "allopurinol":     "Zyloric",
    "azathioprine":    "Imurel",
    "tacrolimus":      "Prograf",
}

RXNORM = {
    "warfarin": "11289",      "aspirin": "1191",         "metformin": "235743",
    "atorvastatin": "83367",  "simvastatin": "36567",    "amoxicillin": "133008",
    "ciprofloxacin": "235851","clarithromycin": "21212", "fluconazole": "4450",
    "fluoxetine": "227224",   "tramadol": "10689",       "ramipril": "35296",
    "amlodipine": "104416",   "furosemide": "4603",      "spironolactone": "9997",
    "digoxin": "3407",        "clopidogrel": "236991",   "sertraline": "155137",
    "omeprazole": "283742",   "ibuprofen": "5640",       "prednisolone": "34372",
    "amiodarone": "703",      "rifampicin": "9384",      "allopurinol": "519",
    "azathioprine": "1223",   "tacrolimus": "48921",
}

# Drug nodes needed for new trap scenarios; not present in load_drugs_contraindications.py
EXTRA_DRUG_NODES = [
    # (inn, brand_name, brand_name_tn, atc_code, dosage_form)
    ("amiodarone",   "Cordarone",  "Cordarone",  "C01BD01", "tablet"),
    ("rifampicin",   "Rifadine",   "Rifadine",   "J04AB02", "capsule"),
    ("allopurinol",  "Zyloric",    "Zyloric",    "M04AA01", "tablet"),
    ("azathioprine", "Imurel",     "Imurel",     "L04AX01", "tablet"),
    ("tacrolimus",   "Prograf",    "Prograf",    "L04AD02", "capsule"),
]

TRAP_NAMES = [
    # Original 8
    "Karim Ben Salah", "Fatma Trabelsi", "Nabil Chaabane", "Amira Khelifi",
    "Sonia Mansouri",  "Hedi Boughanmi", "Mariem Ayari",   "Riadh Jebali",
    # New 12 (traps 9-20)
    "Yassine Gharbi",  "Hajer Belhaj",   "Kamel Zouari",   "Sarra Fennira",
    "Ons Haddad",      "Zied Barka",     "Mounira Selmi",  "Tahar Khiari",
    "Soumaya Hamdi",   "Bechir Hajji",   "Ines Chaouech",  "Walid Tounsi",
]

REGULAR_NAMES = [
    # Original 22
    "Imen Baccar",      "Mohamed Ferchichi", "Najet Bouzid",      "Tarek Hammami",
    "Leila Saidani",    "Youssef Laabidi",   "Khaoula Meddeb",    "Slim Belhadj",
    "Asma Dridi",       "Hassen Oueslati",   "Wafa Ben Romdhane", "Bilel Nouri",
    "Sihem Achour",     "Mondher Ghazali",   "Rim Zaghbani",      "Fares Cherif",
    "Hana Khalfallah",  "Adel Ouerghi",      "Salwa Benhassen",   "Ramzi Baccouche",
    "Dorra Mejri",      "Lotfi Brahmi",
    # New 8
    "Amira Hosni",      "Sami Lakhal",       "Nadia Belhassan",   "Taoufik Maaouia",
    "Yasmine Dridi",    "Khalil Bensalah",   "Farida Ouali",      "Mehdi Touati",
]
ALL_SYNTHETIC_NAMES = TRAP_NAMES + REGULAR_NAMES

driver = connect()


def reset_synthetic_patients() -> int:
    result = driver.execute_query(
        "MATCH (p:Patient) WHERE p.name IN $names OR p.is_trap = true RETURN p.patient_id AS pid",
        names=ALL_SYNTHETIC_NAMES,
    )
    if not result.records:
        return 0
    driver.execute_query(
        "MATCH (p:Patient) WHERE p.name IN $names OR p.is_trap = true DETACH DELETE p",
        names=ALL_SYNTHETIC_NAMES,
    )
    return len(result.records)


removed = reset_synthetic_patients()
if removed:
    print(f"Removed existing synthetic patients: {removed}")

# ── AllergyGroup + cross-reactivity setup ─────────────────────────────────────
ALLERGY_GROUPS = [
    ("penicillin",    "Penicillin-class antibiotics"),
    ("cephalosporin", "Cephalosporin-class antibiotics"),
    ("sulfonamide",   "Sulfonamide antibiotics"),
    ("nsaid",         "Non-steroidal anti-inflammatory drugs"),
    ("ssri",          "Selective serotonin reuptake inhibitors"),
]
for name, desc in ALLERGY_GROUPS:
    driver.execute_query(
        "MERGE (ag:AllergyGroup {name: $name}) SET ag.description = $desc",
        name=name, desc=desc,
    )

driver.execute_query(
    """
    MATCH (pen:AllergyGroup {name: 'penicillin'}), (ceph:AllergyGroup {name: 'cephalosporin'})
    MERGE (pen)-[:CROSS_REACTS_WITH]->(ceph)
    MERGE (ceph)-[:CROSS_REACTS_WITH]->(pen)
    """
)
driver.execute_query(
    """
    MATCH (m:Molecule {inn: 'amoxicillin'})<-[:BRAND_OF]-(d:Drug)
    MATCH (ag:AllergyGroup {name: 'penicillin'})
    MERGE (d)-[:BELONGS_TO_ALLERGY_GROUP]->(ag)
    """
)

# ── Create Drug nodes for extra trap drugs ─────────────────────────────────────
for inn, brand, brand_tn, atc, form in EXTRA_DRUG_NODES:
    drug_id = f"{inn}::{brand}"
    driver.execute_query(
        """
        MERGE (m:Molecule {inn: $inn})
        MERGE (d:Drug {drug_id: $drug_id})
        ON CREATE SET d.brand_name    = $brand,
                      d.brand_name_tn = $brand_tn,
                      d.atc_code      = $atc,
                      d.dosage_form   = $form
        MERGE (d)-[:BRAND_OF]->(m)
        """,
        inn=inn, drug_id=drug_id, brand=brand, brand_tn=brand_tn, atc=atc, form=form,
    )


def _drug_id(inn: str) -> str:
    return f"{inn}::{PREFERRED_BRANDS[inn]}"


patient_counter = [0]


def add_patient(name: str, dob: date, sex: str, weight_kg: float,
                is_trap: bool = False, trap_scenario: str | None = None) -> str:
    patient_counter[0] += 1
    pid = patient_counter[0]
    driver.execute_query(
        """
        MERGE (p:Patient {patient_id: $pid})
        SET p.name          = $name,
            p.dob           = $dob,
            p.sex           = $sex,
            p.weight_kg     = $weight,
            p.is_trap       = $is_trap,
            p.trap_scenario = $scenario
        """,
        pid=pid, name=name, dob=str(dob), sex=sex, weight=weight_kg,
        is_trap=is_trap, scenario=trap_scenario,
    )
    return name


def add_med(patient_name: str, inn: str, dose_mg: float, frequency: str,
            start_date: date, prescriber_id: int = 1) -> None:
    driver.execute_query(
        """
        MATCH (p:Patient {name: $name})
        MATCH (d:Drug {drug_id: $drug_id})
        MERGE (p)-[r:TAKES]->(d)
        SET r.dose_mg       = $dose,
            r.frequency     = $freq,
            r.start_date    = $start,
            r.prescriber_id = $prescriber,
            r.rxnorm_cui    = $rxnorm
        """,
        name=patient_name, drug_id=_drug_id(inn), dose=dose_mg,
        freq=frequency, start=str(start_date), prescriber=prescriber_id,
        rxnorm=RXNORM.get(inn),
    )


def add_condition(patient_name: str, icd11: str, condition_name: str,
                  onset: date = date(2023, 1, 1)) -> None:
    driver.execute_query(
        "MERGE (dc:DiseaseConcept {icd11_code: $icd}) ON CREATE SET dc.condition_name = $cname",
        icd=icd11, cname=condition_name,
    )
    driver.execute_query(
        """
        MATCH (p:Patient {name: $name}), (dc:DiseaseConcept {icd11_code: $icd})
        MERGE (p)-[r:HAS_CONDITION]->(dc)
        SET r.onset_date = $onset, r.status = 'active'
        """,
        name=patient_name, icd=icd11, onset=str(onset),
    )


def add_lab(patient_name: str, loinc: str, test_name: str, value: float,
            unit: str, ts: datetime | None = None) -> None:
    collected_at = str(ts or datetime(2026, 6, 1))
    driver.execute_query(
        """
        MATCH (p:Patient {name: $name})
        CREATE (l:LabResult {loinc_code: $loinc, test_name: $test,
                             value: $value, unit: $unit, collected_at: $ts})
        CREATE (p)-[:HAS_LAB]->(l)
        """,
        name=patient_name, loinc=loinc, test=test_name, value=value,
        unit=unit, ts=collected_at,
    )
    if loinc == LOINC_CREATININE:
        driver.execute_query(
            "MATCH (p:Patient {name: $name}) SET p.creatinine_umol_L = $val",
            name=patient_name, val=value,
        )
    elif loinc == LOINC_INR:
        driver.execute_query(
            "MATCH (p:Patient {name: $name}) SET p.inr = $val",
            name=patient_name, val=value,
        )


def add_allergy(patient_name: str, group_name: str, reaction_type: str,
                documented_at: date = date(2022, 1, 1)) -> None:
    driver.execute_query(
        """
        MATCH (p:Patient {name: $name}), (ag:AllergyGroup {name: $group})
        MERGE (p)-[r:ALLERGIC_TO]->(ag)
        SET r.reaction_type = $reaction,
            r.documented_at = $doc_at
        """,
        name=patient_name, group=group_name, reaction=reaction_type,
        doc_at=str(documented_at),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TRAP PATIENTS (20)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Trap 1: Direct DDI — warfarin + aspirin bleeding risk ─────────────────────
p = add_patient("Karim Ben Salah", date(1958, 4, 12), "M", 74, True, "warfarin_aspirin")
add_condition(p, "BA80", "Atrial fibrillation")
add_med(p, "warfarin", 5, "once daily", date(2025, 3, 1), 101)
add_lab(p, LOINC_INR,        "INR",        2.4, "ratio")
add_lab(p, LOINC_CREATININE, "Creatinine", 88,  "umol/L")

# ── Trap 2: Contraindication — metformin + CKD stage 4 ───────────────────────
p = add_patient("Fatma Trabelsi", date(1963, 9, 5), "F", 68, True, "metformin_ckd")
add_condition(p, "5A11", "Type 2 diabetes mellitus")
add_condition(p, "GB61", "Chronic kidney disease stage 4")
add_med(p, "metformin", 1000, "twice daily", date(2025, 6, 1), 102)
add_lab(p, LOINC_CREATININE, "Creatinine", 180, "umol/L")

# ── Trap 3: CYP3A4 2-hop — simvastatin substrate + clarithromycin inhibitor ──
p = add_patient("Nabil Chaabane", date(1970, 6, 20), "M", 82, True, "simvastatin_cyp3a4")
add_condition(p, "BA80.1", "Hyperlipidaemia")
add_med(p, "simvastatin",    40,  "once daily at night", date(2024, 6,  1), 103)
add_med(p, "clarithromycin", 500, "twice daily",         date(2026, 5, 15), 104)
add_lab(p, LOINC_CREATININE, "Creatinine", 78, "umol/L")

# ── Trap 4: Allergy cross-reactivity — penicillin allergy, cephalosporin risk ─
p = add_patient("Amira Khelifi", date(1990, 2, 14), "F", 58, True, "penicillin_allergy")
add_allergy(p, "penicillin", "anaphylaxis", date(2015, 5, 20))
add_lab(p, LOINC_CREATININE, "Creatinine", 72, "umol/L")

# ── Trap 5: Serotonin syndrome — fluoxetine + tramadol ────────────────────────
p = add_patient("Sonia Mansouri", date(1985, 11, 3), "F", 63, True, "serotonin_syndrome")
add_condition(p, "6A70", "Depressive disorder")
add_med(p, "fluoxetine", 20, "once daily", date(2025, 1, 15), 105)
add_lab(p, LOINC_CREATININE, "Creatinine", 74, "umol/L")

# ── Trap 6: Dose context — elderly patient, ciprofloxacin requires dose adj ───
p = add_patient("Hedi Boughanmi", date(1948, 3, 7), "M", 52, True, "elderly_dose")
add_condition(p, "GC08", "Urinary tract infection")
add_med(p, "ciprofloxacin", 500, "twice daily", date(2026, 6, 1), 106)
add_lab(p, LOINC_CREATININE, "Creatinine", 105, "umol/L")

# ── Trap 7: CYP2C9 overload — warfarin substrate + fluconazole strong inhibitor
p = add_patient("Mariem Ayari", date(1966, 7, 19), "F", 70, True, "cyp2c9_overload")
add_condition(p, "BA80", "Atrial fibrillation")
add_med(p, "warfarin",    5,   "once daily",  date(2025, 2,  1), 107)
add_med(p, "fluconazole", 150, "once weekly", date(2026, 5, 10), 108)
add_lab(p, LOINC_INR,        "INR",        2.1, "ratio")
add_lab(p, LOINC_CREATININE, "Creatinine", 82,  "umol/L")

# ── Trap 8: Brand resolution — Tahor is atorvastatin (same molecule) ──────────
p = add_patient("Riadh Jebali", date(1972, 8, 25), "M", 88, True, "brand_resolution")
add_condition(p, "BA80.1", "Hyperlipidaemia")
add_med(p, "atorvastatin", 20, "once daily", date(2025, 9, 1), 109)
add_lab(p, LOINC_CREATININE, "Creatinine", 85, "umol/L")

# ── Trap 9: Direct DDI contre_indique — warfarin + amiodarone ─────────────────
p = add_patient("Yassine Gharbi", date(1961, 3, 18), "M", 78, True, "warfarin_amiodarone")
add_condition(p, "BA80", "Atrial fibrillation")
add_med(p, "warfarin",   5,   "once daily", date(2025, 1, 10), 110)
add_med(p, "amiodarone", 200, "once daily", date(2026, 6,  1), 111)
add_lab(p, LOINC_INR,        "INR",        3.8, "ratio")
add_lab(p, LOINC_CREATININE, "Creatinine", 88,  "umol/L")

# ── Trap 10: CYP inducer — rifampicin induces CYP2C9, reduces warfarin effect ─
p = add_patient("Hajer Belhaj", date(1955, 8, 11), "F", 64, True, "rifampicin_inducer")
add_condition(p, "1B10", "Tuberculosis")
add_condition(p, "BA80", "Atrial fibrillation")
add_med(p, "warfarin",   4,   "once daily", date(2025, 4, 1), 112)
add_med(p, "rifampicin", 600, "once daily", date(2026, 5, 1), 113)
add_lab(p, LOINC_INR,        "INR",        1.3, "ratio")
add_lab(p, LOINC_CREATININE, "Creatinine", 75,  "umol/L")

# ── Trap 11: Xanthine oxidase — allopurinol + azathioprine contre_indique ─────
p = add_patient("Kamel Zouari", date(1968, 5, 25), "M", 82, True, "allopurinol_azathioprine")
add_condition(p, "FA92", "Gout")
add_condition(p, "QA01", "Post-transplant immunosuppression")
add_med(p, "allopurinol",  300, "once daily", date(2025, 9,  1), 114)
add_med(p, "azathioprine",  50, "once daily", date(2025, 6,  1), 115)
add_lab(p, LOINC_CREATININE, "Creatinine", 90, "umol/L")

# ── Trap 12: Narrow TI drug — tacrolimus + fluconazole (CYP3A4, contre_indique)
p = add_patient("Sarra Fennira", date(1975, 12, 2), "F", 60, True, "tacrolimus_fluconazole")
add_condition(p, "QA01", "Solid organ transplant")
add_med(p, "tacrolimus",  3,   "twice daily", date(2025, 10, 1), 116)
add_med(p, "fluconazole", 150, "once weekly", date(2026, 5, 20), 117)
add_lab(p, LOINC_CREATININE, "Creatinine", 82, "umol/L")

# ── Trap 13: CYP2C19 loss-of-effect — clopidogrel + omeprazole ───────────────
p = add_patient("Ons Haddad", date(1982, 7, 30), "F", 58, True, "clopidogrel_omeprazole")
add_condition(p, "BA80", "Acute coronary syndrome")
add_med(p, "clopidogrel", 75, "once daily", date(2025, 1, 1), 118)
add_med(p, "omeprazole",  20, "once daily", date(2025, 3, 1), 119)
add_lab(p, LOINC_CREATININE, "Creatinine", 72, "umol/L")

# ── Trap 14: CYP2D6 patient-centric — fluoxetine inhibits tramadol activation ─
p = add_patient("Zied Barka", date(1988, 4, 14), "M", 76, True, "tramadol_fluoxetine_cyp2d6")
add_condition(p, "6A70", "Depressive disorder")
add_condition(p, "MG30", "Chronic pain")
add_med(p, "fluoxetine", 20,  "once daily", date(2025, 2,  1), 120)
add_med(p, "tramadol",   100, "twice daily", date(2026, 3, 15), 121)
add_lab(p, LOINC_CREATININE, "Creatinine", 74, "umol/L")

# ── Trap 15: 3-way interaction — NSAID + VKA + corticosteroid ─────────────────
p = add_patient("Mounira Selmi", date(1958, 9, 6), "F", 72, True, "nsaid_anticoagulant_steroid")
add_condition(p, "BA80", "Atrial fibrillation")
add_condition(p, "FA20", "Rheumatoid arthritis")
add_med(p, "warfarin",     3,   "once daily",  date(2025, 1,  1), 122)
add_med(p, "ibuprofen",    400, "three times daily", date(2026, 4, 1), 123)
add_med(p, "prednisolone",  5,  "once daily",  date(2025, 6,  1), 124)
add_lab(p, LOINC_INR,        "INR",        2.2, "ratio")
add_lab(p, LOINC_CREATININE, "Creatinine", 85,  "umol/L")

# ── Trap 16: Lab-only contraindication — high creatinine, no CKD ICD code ────
p = add_patient("Tahar Khiari", date(1952, 1, 19), "M", 74, True, "metformin_egfr_lab_only")
add_condition(p, "5A11", "Type 2 diabetes mellitus")
# Deliberately NO CKD diagnosis — creatinine alone triggers the risk
add_med(p, "metformin", 1000, "twice daily", date(2025, 1, 1), 125)
add_lab(p, LOINC_CREATININE, "Creatinine", 195, "umol/L")

# ── Trap 17: Therapeutic duplication — two SSRIs simultaneously ───────────────
p = add_patient("Soumaya Hamdi", date(1990, 10, 22), "F", 57, True, "two_ssri")
add_condition(p, "6A70", "Major depressive disorder")
add_med(p, "fluoxetine", 20, "once daily", date(2025, 1,  1), 126)
add_med(p, "sertraline", 50, "once daily", date(2026, 4, 10), 127)
add_lab(p, LOINC_CREATININE, "Creatinine", 72, "umol/L")

# ── Trap 18: Polypharmacy elderly — 6 drugs, age > 75, multiple interactions ──
p = add_patient("Bechir Hajji", date(1946, 2, 14), "M", 65, True, "polypharmacy_elderly")
add_condition(p, "BA00", "Essential hypertension")
add_condition(p, "BA80", "Atrial fibrillation")
add_condition(p, "BD10", "Heart failure")
add_med(p, "warfarin",      2.5,   "once daily", date(2025, 1, 1), 128)
add_med(p, "aspirin",       100,   "once daily", date(2025, 1, 1), 129)
add_med(p, "digoxin",       0.125, "once daily", date(2025, 1, 1), 130)
add_med(p, "furosemide",    20,    "once daily", date(2025, 1, 1), 131)
add_med(p, "omeprazole",    20,    "once daily", date(2025, 1, 1), 132)
add_med(p, "spironolactone",25,    "once daily", date(2025, 1, 1), 133)
add_lab(p, LOINC_INR,        "INR",        2.1,  "ratio")
add_lab(p, LOINC_CREATININE, "Creatinine", 112,  "umol/L")

# ── Trap 19: Contraindication — NSAID + active peptic ulcer (DA41) ────────────
p = add_patient("Ines Chaouech", date(1970, 6, 5), "F", 65, True, "nsaid_peptic_ulcer_ci")
add_condition(p, "K27", "Gastric ulcer (peptic ulcer disease)")
add_condition(p, "BA00", "Essential hypertension")
add_med(p, "ibuprofen", 400, "three times daily", date(2026, 3, 1), 134)
add_med(p, "ramipril",  5,   "once daily",        date(2025, 1, 1), 135)
add_lab(p, LOINC_CREATININE, "Creatinine", 80, "umol/L")

# ── Trap 20: Direct DDI — digoxin + amiodarone (digoxin toxicity) ─────────────
p = add_patient("Walid Tounsi", date(1964, 11, 28), "M", 78, True, "digoxin_amiodarone")
add_condition(p, "BA80", "Atrial fibrillation")
add_condition(p, "BD10", "Heart failure")
add_med(p, "digoxin",   0.125, "once daily", date(2025, 6,  1), 136)
add_med(p, "amiodarone", 200,  "once daily", date(2026, 1, 15), 137)
add_lab(p, LOINC_CREATININE, "Creatinine", 88, "umol/L")

# ═══════════════════════════════════════════════════════════════════════════════
# REGULAR PATIENTS (30)
# ═══════════════════════════════════════════════════════════════════════════════

REGULAR = [
    # ── Original 22 ────────────────────────────────────────────────────────────
    ("Imen Baccar",        date(1995, 3, 15), "F", 60,
     [("6A70", "Depressive disorder")],
     [("fluoxetine", 20, "once daily")], 70),
    ("Mohamed Ferchichi",  date(1955, 7,  4), "M", 78,
     [("BA00", "Essential hypertension")],
     [("ramipril", 5, "once daily"), ("amlodipine", 5, "once daily"), ("aspirin", 100, "once daily")], 90),
    ("Najet Bouzid",       date(1968, 12, 20), "F", 65,
     [("5A11", "Type 2 diabetes"), ("BA00", "Hypertension")],
     [("metformin", 500, "twice daily"), ("ramipril", 2.5, "once daily"), ("atorvastatin", 10, "once daily")], 82),
    ("Tarek Hammami",      date(1980, 5, 10), "M", 90,
     [("BA80.1", "Hyperlipidaemia")],
     [("atorvastatin", 10, "once daily")], 88),
    ("Leila Saidani",      date(1943, 1, 28), "F", 54,
     [("BA00", "Hypertension"), ("5A11", "Type 2 diabetes")],
     [("metformin", 500, "once daily"), ("amlodipine", 5, "once daily"), ("furosemide", 20, "once daily")], 98),
    ("Youssef Laabidi",    date(1988, 9,  9), "M", 76, [], [], 76),
    ("Khaoula Meddeb",     date(1975, 4,  6), "F", 67,
     [("CA22", "Asthma")],
     [("prednisolone", 5, "once daily")], 78),
    ("Slim Belhadj",       date(1960, 11, 14), "M", 83,
     [("BA00", "Hypertension"), ("BA80", "Atrial fibrillation")],
     [("warfarin", 3, "once daily"), ("aspirin", 100, "once daily"), ("digoxin", 0.125, "once daily")], 92),
    ("Asma Dridi",         date(1992, 6, 30), "F", 55,
     [("6A70", "Depressive disorder")],
     [("sertraline", 50, "once daily")], 68),
    ("Hassen Oueslati",    date(1950, 2, 17), "M", 72,
     [("BA00", "Hypertension"), ("5A11", "Diabetes"), ("BA80.1", "Hyperlipidaemia")],
     [("simvastatin", 20, "once daily"), ("metformin", 1000, "twice daily"), ("ramipril", 5, "once daily")], 102),
    ("Wafa Ben Romdhane",  date(1983, 8, 22), "F", 61, [("CA22", "Asthma")], [], 73),
    ("Bilel Nouri",        date(1965, 3,  3), "M", 80,
     [("BA00", "Hypertension")],
     [("amlodipine", 10, "once daily"), ("furosemide", 20, "once daily"), ("spironolactone", 25, "once daily")], 86),
    ("Sihem Achour",       date(1970, 10, 11), "F", 69,
     [("5A11", "Diabetes"), ("BA80.1", "Hyperlipidaemia")],
     [("atorvastatin", 20, "once daily"), ("metformin", 500, "once daily")], 80),
    ("Mondher Ghazali",    date(1945, 5, 19), "M", 68,
     [("BA00", "Hypertension"), ("5A11", "Diabetes"), ("CA22", "Asthma")],
     [("metformin", 500, "twice daily"), ("ciprofloxacin", 500, "twice daily"), ("ramipril", 2.5, "once daily")], 110),
    ("Rim Zaghbani",       date(1998, 1,  5), "F", 57, [], [], 65),
    ("Fares Cherif",       date(1987, 12, 12), "M", 77,
     [("BA80.1", "Hyperlipidaemia")],
     [("simvastatin", 20, "once daily")], 79),
    ("Hana Khalfallah",    date(1955, 9, 25), "F", 62,
     [("BA00", "Hypertension"), ("5A11", "Diabetes"), ("BA80", "Atrial fibrillation")],
     [("warfarin", 4, "once daily"), ("metformin", 500, "once daily"), ("digoxin", 0.125, "once daily")], 95),
    ("Adel Ouerghi",       date(1978, 7,  7), "M", 85, [("BA00", "Hypertension")], [], 84),
    ("Salwa Benhassen",    date(1962, 4, 16), "F", 73,
     [("5A11", "Diabetes"), ("BA80.1", "Hyperlipidaemia"), ("BA00", "Hypertension")],
     [("atorvastatin", 40, "once daily"), ("metformin", 1000, "twice daily"), ("amlodipine", 5, "once daily")], 97),
    ("Ramzi Baccouche",    date(1940, 6,  8), "M", 65,
     [("BA00", "Hypertension"), ("BA80", "Atrial fibrillation")],
     [("warfarin", 2.5, "once daily")], 112),
    ("Dorra Mejri",        date(2000, 11, 30), "F", 52, [], [], 66),
    ("Lotfi Brahmi",       date(1968, 8,  1), "M", 79,
     [("5A11", "Diabetes"), ("BA80.1", "Hyperlipidaemia"), ("CA22", "Asthma")],
     [("metformin", 850, "twice daily"), ("simvastatin", 40, "once daily"), ("ciprofloxacin", 250, "once daily")], 91),
    # ── New 8 ──────────────────────────────────────────────────────────────────
    ("Amira Hosni",        date(1984, 7, 20), "F", 65,
     [("5A11", "Type 2 diabetes"), ("BA00", "Hypertension")],
     [("metformin", 500, "twice daily"), ("amlodipine", 5, "once daily"), ("atorvastatin", 10, "once daily")], 80),
    ("Sami Lakhal",        date(1958, 3, 14), "M", 80,
     [("BA00", "Hypertension"), ("BA80", "Atrial fibrillation")],
     [("ramipril", 5, "once daily"), ("digoxin", 0.125, "once daily")], 95),
    ("Nadia Belhassan",    date(1992, 11, 8), "F", 55,
     [("6B00", "Anxiety disorder")],
     [("sertraline", 50, "once daily")], 70),
    ("Taoufik Maaouia",    date(1949, 9, 3), "M", 70,
     [("BA00", "Hypertension"), ("BD10", "Heart failure")],
     [("furosemide", 20, "once daily"), ("spironolactone", 25, "once daily")], 105),
    ("Yasmine Dridi",      date(1976, 5, 17), "F", 63,
     [("DA43", "Gastro-oesophageal reflux disease")],
     [("omeprazole", 20, "once daily")], 75),
    ("Khalil Bensalah",    date(1966, 2, 22), "M", 84,
     [("BA00", "Essential hypertension")],
     [("ramipril", 5, "once daily"), ("amlodipine", 5, "once daily")], 88),
    ("Farida Ouali",       date(1953, 6, 11), "F", 62,
     [("BA00", "Hypertension"), ("BA80.1", "Hyperlipidaemia")],
     [("atorvastatin", 20, "once daily"), ("amlodipine", 5, "once daily")], 92),
    ("Mehdi Touati",       date(1995, 4,  9), "M", 75,
     [("CA40", "Community-acquired pneumonia")],
     [("amoxicillin", 500, "three times daily"), ("ciprofloxacin", 500, "twice daily")], 70),
]

for name, dob, sex, weight, conds, meds, creatinine in REGULAR:
    p = add_patient(name, dob, sex, weight)
    for icd, cname in conds:
        add_condition(p, icd, cname)
    for inn, dose, freq in meds:
        add_med(p, inn, dose, freq, date(2025, 1, 1), 200)
    add_lab(p, LOINC_CREATININE, "Creatinine", creatinine, "umol/L")

driver.close()

total      = patient_counter[0]
trap_count = len(TRAP_NAMES)
reg_count  = total - trap_count
print(f"Allergy groups populated: {len(ALLERGY_GROUPS)}")
print(f"Extra Drug nodes created: {len(EXTRA_DRUG_NODES)}")
print(f"Trap patients inserted:   {trap_count}")
print(f"Regular patients inserted:{reg_count}")
print(f"Synthetic patient total:  {total}")
