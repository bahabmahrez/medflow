"""
Tests for safety checks: contraindications, allergy conflicts,
therapeutic duplication, and dose appropriateness.
"""
import pytest
from query.safety import (
    check_contraindications,
    check_allergy_conflict,
    check_therapeutic_duplication,
    check_dose_appropriateness,
)


# ── check_contraindications ────────────────────────────────────────────────────

def test_metformin_ckd_contraindicated():
    """Metformin is contraindicated in renal impairment (lactic acidosis)."""
    r = check_contraindications("metformin", ["renal impairment"])
    assert r["status"] == "found"
    ci = r["data"]["contraindications"]
    assert len(ci) >= 1
    assert ci[0]["severity"] == "contraindicated"


def test_warfarin_pregnancy_contraindicated():
    """Warfarin is contraindicated in pregnancy (teratogenic)."""
    r = check_contraindications("warfarin", ["pregnancy"])
    assert r["status"] == "found"
    assert any("Z34" in c.get("icd_code", "") for c in r["data"]["contraindications"])


def test_ibuprofen_peptic_ulcer():
    """Ibuprofen is contraindicated in peptic ulcer disease (K27)."""
    r = check_contraindications("ibuprofen", ["K27"])
    assert r["status"] == "found"


def test_no_contraindication_safe_pair():
    """Amoxicillin has no contraindication for hypertension."""
    r = check_contraindications("amoxicillin", ["hypertension"])
    assert r["status"] == "not_found"
    assert r["data"]["contraindications"] == []


def test_empty_conditions_returns_ok():
    r = check_contraindications("metformin", [])
    assert r["status"] == "found"
    assert r["data"]["contraindications"] == []


# ── check_allergy_conflict ─────────────────────────────────────────────────────

def test_amoxicillin_penicillin_direct():
    """Amoxicillin is a penicillin — direct conflict."""
    r = check_allergy_conflict("amoxicillin", ["penicillin"])
    assert r["status"] == "found"
    conflicts = r["data"]["conflicts"]
    assert len(conflicts) >= 1
    assert conflicts[0]["type"] == "direct"


def test_no_allergy_conflict_different_class():
    """Metformin is not in a penicillin allergy group."""
    r = check_allergy_conflict("metformin", ["penicillin"])
    assert r["status"] == "not_found"
    assert r["data"]["conflicts"] == []


def test_empty_allergies_no_conflict():
    r = check_allergy_conflict("amoxicillin", [])
    assert r["status"] == "found"
    assert r["data"]["conflicts"] == []


# ── check_therapeutic_duplication ─────────────────────────────────────────────

def test_atorvastatin_tahor_duplication():
    """Prescribing atorvastatin when Tahor is already active = duplication."""
    r = check_therapeutic_duplication("atorvastatin", ["Tahor", "metformin"])
    assert r["status"] == "found"
    dups = r["data"]["duplicates"]
    assert len(dups) >= 1
    assert dups[0]["same_as"] == "atorvastatin"


def test_warfarin_coumadin_duplication():
    """Warfarin and Coumadin are the same molecule."""
    r = check_therapeutic_duplication("warfarin", ["Coumadin"])
    assert r["status"] == "found"


def test_no_duplication_different_drugs():
    r = check_therapeutic_duplication("metformin", ["warfarin", "aspirin"])
    assert r["status"] == "not_found"
    assert r["data"]["duplicates"] == []


def test_empty_active_meds_no_duplication():
    r = check_therapeutic_duplication("warfarin", [])
    assert r["status"] == "not_found"


# ── check_dose_appropriateness ─────────────────────────────────────────────────

def test_elderly_ciprofloxacin_flagged():
    """78-year-old should trigger elderly dose flag for ciprofloxacin."""
    r = check_dose_appropriateness("ciprofloxacin", dose="500mg", age=78)
    assert r["status"] == "found"
    assert "elderly" in r["data"]["flags"]


def test_high_creatinine_metformin_flagged():
    """Creatinine > 150 umol/L should flag renal dose adjustment."""
    r = check_dose_appropriateness(
        "metformin", labs={"creatinine_umol_L": 210}
    )
    assert r["status"] == "found"
    assert "renal_impairment" in r["data"]["flags"]


def test_normal_patient_no_flags():
    """Young healthy patient — no dose flags expected."""
    r = check_dose_appropriateness(
        "metformin", age=45, labs={"creatinine_umol_L": 80, "egfr": 90}
    )
    assert r["status"] == "not_found"
    assert r["data"]["flags"] == []
