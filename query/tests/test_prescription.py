"""
Tests for full_prescription_check — integration tests combining all checks.
"""
import pytest
from query.prescription import full_prescription_check


def test_simvastatin_clarithromycin_high_risk():
    """
    Core GraphRAG demo case: no direct DDI edge, but CYP3A4 competition
    makes this HIGH risk.  The system must not return LOW risk.
    """
    r = full_prescription_check(
        prescription=[{"drug": "simvastatin"}],
        patient_meds=["clarithromycin"],
    )
    assert r["status"] == "found"
    assert r["data"]["summary"]["overall_risk"] in ("HIGH", "MEDIUM")
    comps = r["data"]["cyp_competition"]
    assert len(comps) >= 1
    cyp3a4 = [c for c in comps if c["enzyme"] == "CYP3A4"]
    assert len(cyp3a4) >= 1


def test_warfarin_aspirin_critical():
    """Warfarin + aspirin must surface as a critical/major interaction."""
    r = full_prescription_check(
        prescription=[{"drug": "warfarin"}],
        patient_meds=["aspirin"],
    )
    assert r["status"] == "found"
    assert r["data"]["summary"]["critical_issues"] >= 1


def test_metformin_with_ckd_contraindicated():
    """Metformin prescribed to a CKD patient must trigger contraindication."""
    r = full_prescription_check(
        prescription=[{"drug": "metformin"}],
        conditions=["renal impairment"],
    )
    per = r["data"]["per_drug"].get("metformin", {})
    ci = per.get("contraindications", {}).get("data", {}).get("contraindications", [])
    assert len(ci) >= 1


def test_allergy_conflict_included():
    """Amoxicillin for a penicillin-allergic patient must flag conflict."""
    r = full_prescription_check(
        prescription=[{"drug": "amoxicillin"}],
        allergies=["penicillin"],
    )
    per = r["data"]["per_drug"].get("amoxicillin", {})
    conflicts = per.get("allergy_conflict", {}).get("data", {}).get("conflicts", [])
    assert len(conflicts) >= 1


def test_therapeutic_duplication_included():
    """Prescribing atorvastatin when Tahor already active must flag duplication."""
    r = full_prescription_check(
        prescription=[{"drug": "atorvastatin"}],
        patient_meds=["Tahor"],
    )
    per = r["data"]["per_drug"].get("atorvastatin", {})
    dups = per.get("duplication", {}).get("data", {}).get("duplicates", [])
    assert len(dups) >= 1


def test_safe_prescription_low_risk():
    """An unrelated new drug with no interactions returns LOW risk."""
    r = full_prescription_check(
        prescription=[{"drug": "amoxicillin"}],
        patient_meds=["metformin"],
        conditions=[],
        allergies=[],
    )
    assert r["data"]["summary"]["overall_risk"] == "LOW"


def test_empty_prescription_returns_error():
    r = full_prescription_check(prescription=[])
    assert r["status"] == "error"


def test_summary_envelope_structure():
    """Verify the return envelope has all required summary keys."""
    r = full_prescription_check(
        prescription=[{"drug": "warfarin"}],
        patient_meds=["aspirin"],
    )
    summary = r["data"]["summary"]
    for key in ("new_drugs", "interactions_found", "cyp_competitions",
                "contraindications", "allergy_conflicts", "duplications",
                "dose_flags", "critical_issues", "overall_risk"):
        assert key in summary, f"Missing summary key: {key}"
