"""
Tests for interface.patient_data.

The parsing and mapping helpers are pure and always run. The database readers
are exercised against real PostgreSQL and skip cleanly when it is not running.
"""
from __future__ import annotations

from datetime import date

import pytest

from interface.patient_data import (
    _age,
    _lab_key,
    list_patients,
    load_patient,
    parse_prescription,
    to_scan_kwargs,
)


# ── Prescription parsing ──────────────────────────────────────────────────────

def test_one_medicine_per_line_with_optional_dose():
    assert parse_prescription("clarithromycin 500mg\nibuprofen, 400mg\nTahor") == [
        {"drug": "clarithromycin", "dose": "500mg"},
        {"drug": "ibuprofen", "dose": "400mg"},
        {"drug": "Tahor", "dose": None},
    ]


def test_blank_lines_and_bullets_are_tolerated():
    assert parse_prescription("\n- warfarin 5mg\n\n* aspirin\n") == [
        {"drug": "warfarin", "dose": "5mg"},
        {"drug": "aspirin", "dose": None},
    ]


def test_multi_word_drug_names_survive():
    assert parse_prescription("amoxicillin clavulanate 1g") == [
        {"drug": "amoxicillin clavulanate", "dose": "1g"},
    ]


def test_a_trailing_word_without_digits_is_not_treated_as_a_dose():
    assert parse_prescription("insulin glargine") == [
        {"drug": "insulin glargine", "dose": None},
    ]


def test_empty_input_yields_nothing():
    assert parse_prescription("") == []
    assert parse_prescription("   \n\n ") == []
    assert parse_prescription(None) == []


# ── Mapping helpers ───────────────────────────────────────────────────────────

def test_age_is_computed_from_date_of_birth():
    assert _age(None) is None
    assert _age(date(1990, 1, 1)) >= 35


def test_lab_names_map_onto_the_dose_check_keys():
    assert _lab_key("Creatinine") == "creatinine_umol_L"
    assert _lab_key("eGFR") == "egfr"
    assert _lab_key("ALT") == "alt_iu_L"
    assert _lab_key("INR") is None, "shown to the pharmacist but not a dose-check input"


def test_to_scan_kwargs_flattens_a_patient_for_the_engine():
    patient = {
        "active_meds": [{"inn": "warfarin"}, {"inn": "simvastatin"}],
        "conditions":  [{"condition_name": "Chronic kidney disease stage 4"}],
        "allergies":   [{"allergy": "penicillin"}],
        "age": 68, "weight_kg": 74,
        "labs": {"creatinine_umol_L": 180.0},
    }
    assert to_scan_kwargs(patient) == {
        "patient_meds": ["warfarin", "simvastatin"],
        "conditions":   ["Chronic kidney disease stage 4"],
        "allergies":    ["penicillin"],
        "age": 68, "weight": 74.0,
        "labs": {"creatinine_umol_L": 180.0},
    }


def test_to_scan_kwargs_handles_a_patient_with_no_history():
    assert to_scan_kwargs({}) == {
        "patient_meds": [], "conditions": [], "allergies": [],
        "age": None, "weight": None, "labs": {},
    }


# ── Database readers ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def patients():
    try:
        return list_patients()
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")


def test_patient_list_carries_what_the_selector_shows(patients):
    if not patients:
        pytest.skip("no patients loaded")
    first = patients[0]
    assert {"id", "name", "age", "is_trap", "active_med_count"} <= set(first)


def test_trap_patients_sort_first_for_demos(patients):
    if not any(p["is_trap"] for p in patients):
        pytest.skip("no trap patients loaded")
    assert patients[0]["is_trap"] is True


def test_loading_a_patient_returns_engine_ready_context(patients):
    if not patients:
        pytest.skip("no patients loaded")
    patient = load_patient(patients[0]["id"])

    assert patient is not None
    for key in ("active_meds", "conditions", "allergies", "lab_results", "labs"):
        assert key in patient

    kwargs = to_scan_kwargs(patient)
    assert isinstance(kwargs["patient_meds"], list)
    assert all(isinstance(name, str) for name in kwargs["patient_meds"])


def test_unknown_patient_returns_none(patients):
    assert load_patient(-1) is None
