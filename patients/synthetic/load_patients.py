"""
MedFlow synthetic patient loader.

Creates allergy reference rows, then loads 8 trap patients and 22 regular
patients. The script is rerunnable: it removes only this synthetic cohort
before inserting fresh rows.
"""

import os
from datetime import date, datetime

import psycopg2


DB = dict(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
)

LOINC_CREATININE = "2160-0"
LOINC_INR = "6301-6"

RXNORM = {
    "warfarin": "11289",
    "aspirin": "1191",
    "metformin": "235743",
    "atorvastatin": "83367",
    "simvastatin": "36567",
    "amoxicillin": "133008",
    "ciprofloxacin": "235851",
    "clarithromycin": "21212",
    "fluconazole": "4450",
    "fluoxetine": "227224",
    "tramadol": "10689",
    "ramipril": "35296",
    "amlodipine": "104416",
    "furosemide": "4603",
    "spironolactone": "9997",
    "digoxin": "3407",
    "clopidogrel": "236991",
    "sertraline": "155137",
    "omeprazole": "283742",
    "ibuprofen": "5640",
    "prednisolone": "34372",
}

PREFERRED_BRANDS = {
    "warfarin": "Coumadin",
    "aspirin": "Aspegic",
    "metformin": "Glucophage",
    "atorvastatin": "Tahor",
    "simvastatin": "Zocor",
    "amoxicillin": "Clamoxyl",
    "ciprofloxacin": "Ciflox",
    "clarithromycin": "Zeclar",
    "fluconazole": "Triflucan",
    "fluoxetine": "Prozac",
    "tramadol": "Topalgic",
    "ramipril": "Triatec",
    "amlodipine": "Amlor",
    "furosemide": "Lasilix",
    "spironolactone": "Aldactone",
    "digoxin": "Digoxine",
    "clopidogrel": "Plavix",
    "sertraline": "Zoloft",
    "omeprazole": "Mopral",
    "ibuprofen": "Brufen",
    "prednisolone": "Solupred",
}

TRAP_PATIENTS = [
    "Karim Ben Salah",
    "Fatma Trabelsi",
    "Nabil Chaabane",
    "Amira Khelifi",
    "Sonia Mansouri",
    "Hedi Boughanmi",
    "Mariem Ayari",
    "Riadh Jebali",
]

REGULAR_PATIENTS = [
    "Imen Baccar",
    "Mohamed Ferchichi",
    "Najet Bouzid",
    "Tarek Hammami",
    "Leila Saidani",
    "Youssef Laabidi",
    "Khaoula Meddeb",
    "Slim Belhadj",
    "Asma Dridi",
    "Hassen Oueslati",
    "Wafa Ben Romdhane",
    "Bilel Nouri",
    "Sihem Achour",
    "Mondher Ghazali",
    "Rim Zaghbani",
    "Fares Cherif",
    "Hana Khalfallah",
    "Adel Ouerghi",
    "Salwa Benhassen",
    "Ramzi Baccouche",
    "Dorra Mejri",
    "Lotfi Brahmi",
]

ALL_SYNTHETIC_NAMES = TRAP_PATIENTS + REGULAR_PATIENTS


def run():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    def get_drug_id(inn):
        preferred_brand = PREFERRED_BRANDS[inn]
        cur.execute(
            """
            SELECT d.id
            FROM drugs d
            JOIN molecules m ON m.id = d.molecule_id
            WHERE m.inn = %s
            ORDER BY
                CASE
                    WHEN lower(coalesce(d.brand_name_tn, '')) = lower(%s) THEN 0
                    WHEN lower(coalesce(d.brand_name, '')) = lower(%s) THEN 1
                    WHEN lower(coalesce(d.brand_name_fr, '')) = lower(%s) THEN 2
                    ELSE 3
                END,
                d.id
            LIMIT 1
            """,
            (inn, preferred_brand, preferred_brand, preferred_brand),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(
                f"Drug '{inn}' not found. Run the knowledge-base loaders before patients."
            )
        return row[0]

    drug_ids = {inn: get_drug_id(inn) for inn in PREFERRED_BRANDS}

    def reset_synthetic_patients():
        cur.execute(
            "SELECT id FROM patients WHERE name = ANY(%s) OR is_trap IS TRUE",
            (ALL_SYNTHETIC_NAMES,),
        )
        patient_ids = [row[0] for row in cur.fetchall()]
        if not patient_ids:
            return 0

        for table in (
            "alert_reviews",
            "prescription_scans",
            "refill_records",
            "prescription_history",
            "allergies",
            "lab_results",
            "active_medications",
            "conditions",
        ):
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                (table,)
            )
            if cur.fetchone()[0]:
                cur.execute(f"DELETE FROM {table} WHERE patient_id = ANY(%s)", (patient_ids,))
        cur.execute("DELETE FROM patients WHERE id = ANY(%s)", (patient_ids,))
        return len(patient_ids)

    removed = reset_synthetic_patients()
    if removed:
        print(f"Removed existing synthetic patients: {removed}")

    allergy_groups = [
        ("penicillin", "Penicillin-class antibiotics"),
        ("cephalosporin", "Cephalosporin-class antibiotics"),
        ("sulfonamide", "Sulfonamide antibiotics"),
        ("nsaid", "Non-steroidal anti-inflammatory drugs"),
    ]
    ag_ids = {}
    for name, desc in allergy_groups:
        cur.execute(
            """
            INSERT INTO allergy_groups (name, description)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
            RETURNING id
            """,
            (name, desc),
        )
        ag_ids[name] = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO allergy_cross_reactivities (group_a_id, group_b_id)
        VALUES (%s, %s), (%s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            ag_ids["penicillin"],
            ag_ids["cephalosporin"],
            ag_ids["cephalosporin"],
            ag_ids["penicillin"],
        ),
    )
    cur.execute(
        """
        INSERT INTO drug_allergy_groups (drug_id, allergy_group_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        """,
        (drug_ids["amoxicillin"], ag_ids["penicillin"]),
    )

    def add_patient(name, dob, sex, weight_kg, is_trap=False, trap_scenario=None):
        cur.execute(
            """
            INSERT INTO patients (name, dob, sex, weight_kg, is_trap, trap_scenario)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, dob, sex, weight_kg, is_trap, trap_scenario),
        )
        return cur.fetchone()[0]

    def add_med(patient_id, inn, dose_mg, frequency, start_date, prescriber_id=1):
        cur.execute(
            """
            INSERT INTO active_medications
                (patient_id, drug_id, rxnorm_cui, dose_mg, frequency, start_date, prescriber_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                patient_id,
                drug_ids[inn],
                RXNORM[inn],
                dose_mg,
                frequency,
                start_date,
                prescriber_id,
            ),
        )

    def add_lab(patient_id, loinc, name, value, unit, ts=None):
        cur.execute(
            """
            INSERT INTO lab_results (patient_id, loinc_code, test_name, value, unit, collected_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (patient_id, loinc, name, value, unit, ts or datetime(2026, 6, 1)),
        )

    def add_condition(patient_id, icd11, name, onset=date(2023, 1, 1)):
        cur.execute(
            """
            INSERT INTO conditions (patient_id, icd11_code, condition_name, onset_date)
            VALUES (%s, %s, %s, %s)
            """,
            (patient_id, icd11, name, onset),
        )

    def add_allergy(patient_id, group_name, reaction_type, documented_at=date(2022, 1, 1)):
        cur.execute(
            """
            INSERT INTO allergies (patient_id, allergy_group_id, reaction_type, documented_at)
            VALUES (%s, %s, %s, %s)
            """,
            (patient_id, ag_ids[group_name], reaction_type, documented_at),
        )

    p = add_patient("Karim Ben Salah", date(1958, 4, 12), "M", 74, True, "warfarin_aspirin")
    add_condition(p, "BA80", "Atrial fibrillation")
    add_med(p, "warfarin", 5, "once daily", date(2025, 3, 1), 101)
    add_lab(p, LOINC_INR, "INR", 2.4, "ratio")
    add_lab(p, LOINC_CREATININE, "Creatinine", 88, "umol/L")

    p = add_patient("Fatma Trabelsi", date(1963, 9, 5), "F", 68, True, "metformin_ckd")
    add_condition(p, "5A10", "Type 2 diabetes mellitus")
    add_condition(p, "GB61", "Chronic kidney disease stage 4")
    add_lab(p, LOINC_CREATININE, "Creatinine", 180, "umol/L")

    p = add_patient("Nabil Chaabane", date(1970, 6, 20), "M", 82, True, "simvastatin_clarity")
    add_condition(p, "BA80.1", "Hyperlipidaemia")
    add_med(p, "simvastatin", 40, "once daily at night", date(2024, 6, 1), 102)
    add_lab(p, LOINC_CREATININE, "Creatinine", 78, "umol/L")

    p = add_patient("Amira Khelifi", date(1990, 2, 14), "F", 58, True, "penicillin_allergy")
    add_allergy(p, "penicillin", "anaphylaxis", date(2015, 5, 20))
    add_lab(p, LOINC_CREATININE, "Creatinine", 72, "umol/L")

    p = add_patient("Sonia Mansouri", date(1985, 11, 3), "F", 63, True, "serotonin_syndrome")
    add_condition(p, "6A70", "Depressive disorder")
    add_med(p, "fluoxetine", 20, "once daily", date(2025, 1, 15), 103)
    add_lab(p, LOINC_CREATININE, "Creatinine", 74, "umol/L")

    p = add_patient("Hedi Boughanmi", date(1948, 3, 7), "M", 52, True, "elderly_dose")
    add_condition(p, "MG31", "Urinary tract infection")
    add_lab(p, LOINC_CREATININE, "Creatinine", 105, "umol/L")

    p = add_patient("Mariem Ayari", date(1966, 7, 19), "F", 70, True, "cyp2c9_overload")
    add_condition(p, "BA80", "Atrial fibrillation")
    add_med(p, "warfarin", 5, "once daily", date(2025, 2, 1), 104)
    add_med(p, "fluconazole", 150, "once weekly", date(2026, 5, 10), 105)
    add_lab(p, LOINC_INR, "INR", 2.1, "ratio")
    add_lab(p, LOINC_CREATININE, "Creatinine", 82, "umol/L")

    p = add_patient("Riadh Jebali", date(1972, 8, 25), "M", 88, True, "therapeutic_dup")
    add_condition(p, "BA80.1", "Hyperlipidaemia")
    add_med(p, "atorvastatin", 20, "once daily", date(2025, 9, 1), 106)
    add_lab(p, LOINC_CREATININE, "Creatinine", 85, "umol/L")

    regular = [
        ("Imen Baccar", date(1995, 3, 15), "F", 60, [("6A70", "Depressive disorder")], [("fluoxetine", 20, "once daily")], 70),
        ("Mohamed Ferchichi", date(1955, 7, 4), "M", 78, [("BA00", "Essential hypertension")], [("ramipril", 5, "once daily"), ("amlodipine", 5, "once daily"), ("aspirin", 100, "once daily")], 90),
        ("Najet Bouzid", date(1968, 12, 20), "F", 65, [("5A10", "Type 2 diabetes"), ("BA00", "Hypertension")], [("metformin", 500, "twice daily"), ("ramipril", 2.5, "once daily"), ("atorvastatin", 10, "once daily")], 82),
        ("Tarek Hammami", date(1980, 5, 10), "M", 90, [("BA80.1", "Hyperlipidaemia")], [("atorvastatin", 10, "once daily")], 88),
        ("Leila Saidani", date(1943, 1, 28), "F", 54, [("BA00", "Hypertension"), ("5A10", "Type 2 diabetes")], [("metformin", 500, "once daily"), ("amlodipine", 5, "once daily"), ("furosemide", 20, "once daily")], 98),
        ("Youssef Laabidi", date(1988, 9, 9), "M", 76, [], [], 76),
        ("Khaoula Meddeb", date(1975, 4, 6), "F", 67, [("CA22", "Asthma")], [("prednisolone", 5, "once daily")], 78),
        ("Slim Belhadj", date(1960, 11, 14), "M", 83, [("BA00", "Hypertension"), ("BA80", "Atrial fibrillation")], [("warfarin", 3, "once daily"), ("aspirin", 100, "once daily"), ("digoxin", 0.125, "once daily")], 92),
        ("Asma Dridi", date(1992, 6, 30), "F", 55, [("6A70", "Depressive disorder")], [("sertraline", 50, "once daily")], 68),
        ("Hassen Oueslati", date(1950, 2, 17), "M", 72, [("BA00", "Hypertension"), ("5A10", "Diabetes"), ("BA80.1", "Hyperlipidaemia")], [("simvastatin", 20, "once daily"), ("metformin", 1000, "twice daily"), ("ramipril", 5, "once daily")], 102),
        ("Wafa Ben Romdhane", date(1983, 8, 22), "F", 61, [("CA22", "Asthma")], [], 73),
        ("Bilel Nouri", date(1965, 3, 3), "M", 80, [("BA00", "Hypertension")], [("amlodipine", 10, "once daily"), ("furosemide", 20, "once daily"), ("spironolactone", 25, "once daily")], 86),
        ("Sihem Achour", date(1970, 10, 11), "F", 69, [("5A10", "Diabetes"), ("BA80.1", "Hyperlipidaemia")], [("atorvastatin", 20, "once daily"), ("metformin", 500, "once daily")], 80),
        ("Mondher Ghazali", date(1945, 5, 19), "M", 68, [("BA00", "Hypertension"), ("5A10", "Diabetes"), ("CA22", "Asthma")], [("metformin", 500, "twice daily"), ("ciprofloxacin", 500, "twice daily"), ("ramipril", 2.5, "once daily")], 110),
        ("Rim Zaghbani", date(1998, 1, 5), "F", 57, [], [], 65),
        ("Fares Cherif", date(1987, 12, 12), "M", 77, [("BA80.1", "Hyperlipidaemia")], [("simvastatin", 20, "once daily")], 79),
        ("Hana Khalfallah", date(1955, 9, 25), "F", 62, [("BA00", "Hypertension"), ("5A10", "Diabetes"), ("BA80", "Atrial fibrillation")], [("warfarin", 4, "once daily"), ("metformin", 500, "once daily"), ("digoxin", 0.125, "once daily")], 95),
        ("Adel Ouerghi", date(1978, 7, 7), "M", 85, [("BA00", "Hypertension")], [], 84),
        ("Salwa Benhassen", date(1962, 4, 16), "F", 73, [("5A10", "Diabetes"), ("BA80.1", "Hyperlipidaemia"), ("BA00", "Hypertension")], [("atorvastatin", 40, "once daily"), ("metformin", 1000, "twice daily"), ("amlodipine", 5, "once daily")], 97),
        ("Ramzi Baccouche", date(1940, 6, 8), "M", 65, [("BA00", "Hypertension"), ("BA80", "Atrial fibrillation")], [("warfarin", 2.5, "once daily")], 112),
        ("Dorra Mejri", date(2000, 11, 30), "F", 52, [], [], 66),
        ("Lotfi Brahmi", date(1968, 8, 1), "M", 79, [("5A10", "Diabetes"), ("BA80.1", "Hyperlipidaemia"), ("CA22", "Asthma")], [("metformin", 850, "twice daily"), ("simvastatin", 40, "once daily"), ("ciprofloxacin", 250, "once daily")], 91),
    ]

    for name, dob, sex, weight, conds, meds, creatinine in regular:
        p = add_patient(name, dob, sex, weight)
        for icd, condition in conds:
            add_condition(p, icd, condition)
        for inn, dose, frequency in meds:
            add_med(p, inn, dose, frequency, date(2025, 1, 1), 200)
        add_lab(p, LOINC_CREATININE, "Creatinine", creatinine, "umol/L")

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM patients WHERE name = ANY(%s)", (ALL_SYNTHETIC_NAMES,))
    total = cur.fetchone()[0]
    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT p.id
            FROM patients p
            JOIN active_medications am ON am.patient_id = p.id
            WHERE p.name = ANY(%s) AND p.is_trap IS FALSE
            GROUP BY p.id
            HAVING COUNT(*) >= 3
        ) multi_med
        """,
        (ALL_SYNTHETIC_NAMES,),
    )
    regular_multi_med = cur.fetchone()[0]

    print("Allergy groups populated:", ", ".join(sorted(ag_ids)))
    print("Trap patients inserted: 8")
    print("Regular patients inserted: 22")
    print(f"Synthetic patient count: {total}")
    print(f"Regular patients with 3+ active meds: {regular_multi_med}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
