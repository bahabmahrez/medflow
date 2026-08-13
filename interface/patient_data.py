"""
Reading patient context out of PostgreSQL for the scan screen.

The reactive engine takes plain lists (drug names, conditions, allergies, a labs
dict). This module turns a patient row and its related tables into exactly that
shape, so the interface never builds SQL and the engine never learns about the
database.

Connection settings come from the same environment variables the rest of the
project uses (POSTGRES_DB / USER / PASSWORD / HOST / PORT), defaulting to the
docker-compose values.
"""
from __future__ import annotations

import os
from datetime import date

import psycopg2
import psycopg2.extras

#: Lab test name in the database -> the key check_dose_appropriateness expects.
#: Anything not listed is still shown to the pharmacist, just not fed to the
#: dose check (INR, for example, is clinically important context but the graph
#: has no INR-based dose rule).
_LAB_KEYS = {
    "creatinine": "creatinine_umol_L",
    "egfr":       "egfr",
    "alt":        "alt_iu_L",
    "ast":        "ast_iu_L",
}


def _connect():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "medflow"),
        user=os.getenv("POSTGRES_USER", "medflow"),
        password=os.getenv("POSTGRES_PASSWORD", "medflow"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        connect_timeout=int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "3")),
    )


def _age(dob: date | None) -> int | None:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _lab_key(test_name: str | None) -> str | None:
    name = (test_name or "").strip().lower()
    for token, key in _LAB_KEYS.items():
        if token in name:
            return key
    return None


def list_patients() -> list[dict]:
    """Every patient, for the selector. Trap patients are flagged for demos."""
    with _connect() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            """
            SELECT p.id, p.name, p.dob, p.sex, p.is_trap, p.trap_scenario,
                   (SELECT count(*) FROM active_medications am
                     WHERE am.patient_id = p.id) AS active_med_count
              FROM patients p
             ORDER BY p.is_trap DESC, p.id
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        row["age"] = _age(row.get("dob"))
    return rows


def load_patient(patient_id: int) -> dict | None:
    """
    Full clinical context for one patient.

    Returns ``None`` if the patient does not exist. Active medications are
    returned as canonical INNs (with the brand shown alongside) because that is
    what the knowledge graph resolves against.
    """
    with _connect() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            "SELECT id, name, dob, sex, weight_kg, is_trap, trap_scenario "
            "FROM patients WHERE id = %s",
            (patient_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        patient = dict(row)

        cur.execute(
            """
            SELECT m.inn, d.brand_name, am.dose_mg, am.frequency, am.start_date
              FROM active_medications am
              JOIN drugs d     ON d.id = am.drug_id
              JOIN molecules m ON m.id = d.molecule_id
             WHERE am.patient_id = %s
             ORDER BY m.inn
            """,
            (patient_id,),
        )
        patient["active_meds"] = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT condition_name, icd11_code, onset_date FROM conditions "
            "WHERE patient_id = %s ORDER BY condition_name",
            (patient_id,),
        )
        patient["conditions"] = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT ag.name AS allergy, a.reaction_type, a.documented_at
              FROM allergies a
              JOIN allergy_groups ag ON ag.id = a.allergy_group_id
             WHERE a.patient_id = %s
             ORDER BY ag.name
            """,
            (patient_id,),
        )
        patient["allergies"] = [dict(r) for r in cur.fetchall()]

        # Most recent value per test.
        cur.execute(
            """
            SELECT DISTINCT ON (test_name)
                   test_name, value, unit, collected_at
              FROM lab_results
             WHERE patient_id = %s
             ORDER BY test_name, collected_at DESC NULLS LAST
            """,
            (patient_id,),
        )
        patient["lab_results"] = [dict(r) for r in cur.fetchall()]

    patient["age"] = _age(patient.get("dob"))
    patient["labs"] = {}
    for lab in patient["lab_results"]:
        key = _lab_key(lab.get("test_name"))
        if key is not None and lab.get("value") is not None:
            patient["labs"][key] = float(lab["value"])

    return patient


def to_scan_kwargs(patient: dict) -> dict:
    """
    Map a loaded patient onto ``scan_prescription`` keyword arguments.

    Kept separate from :func:`load_patient` so the interface can let the
    pharmacist amend the context (add an allergy the record is missing, say)
    before scanning.
    """
    return {
        "patient_meds": [m["inn"] for m in patient.get("active_meds", []) if m.get("inn")],
        "conditions":   [c["condition_name"] for c in patient.get("conditions", [])
                         if c.get("condition_name")],
        "allergies":    [a["allergy"] for a in patient.get("allergies", []) if a.get("allergy")],
        "age":          patient.get("age"),
        "weight":       float(patient["weight_kg"]) if patient.get("weight_kg") else None,
        "labs":         patient.get("labs") or {},
    }


def parse_prescription(text: str) -> list[dict]:
    """
    Turn free-typed prescription lines into engine entries.

    One medicine per line, dose optional after a comma or whitespace::

        clarithromycin 500mg
        ibuprofen, 400mg
        Tahor

    Deliberately forgiving: a pharmacist typing at the counter should not have
    to think about syntax, and an unrecognised name is reported by the scan
    itself rather than rejected here.
    """
    entries: list[dict] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip().strip("-•*").strip()
        if not line:
            continue
        if "," in line:
            drug, _, dose = line.partition(",")
        else:
            parts = line.split()
            # A dose is the trailing token only if it carries a digit.
            if len(parts) > 1 and any(ch.isdigit() for ch in parts[-1]):
                drug, dose = " ".join(parts[:-1]), parts[-1]
            else:
                drug, dose = line, ""
        drug = drug.strip()
        dose = dose.strip()
        if drug:
            entries.append({"drug": drug, "dose": dose or None})
    return entries
