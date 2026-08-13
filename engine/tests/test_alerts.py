"""
Tests for engine.alerts — severity mapping, action mapping, reasoning chains.
No database or LLM involved.
"""
from __future__ import annotations

from engine import alerts as A


# ── Severity + action mapping ─────────────────────────────────────────────────

def test_ansm_grades_map_to_canonical_severities():
    assert A.severity_from_ansm("contre_indique") == A.CONTRAINDICATED
    assert A.severity_from_ansm("major") == A.MAJOR
    assert A.severity_from_ansm("deconseillee") == A.MAJOR
    assert A.severity_from_ansm("moderate") == A.MODERATE
    assert A.severity_from_ansm("a_prendre_en_compte") == A.MINOR


def test_unknown_grade_falls_back_to_moderate_not_silent_pass():
    assert A.severity_from_ansm(None) == A.MODERATE
    assert A.severity_from_ansm("something_new") == A.MODERATE


def test_severity_drives_recommended_action():
    assert A.SEVERITY_TO_ACTION[A.CONTRAINDICATED] == A.DO_NOT_DISPENSE
    assert A.SEVERITY_TO_ACTION[A.MAJOR] == A.CONTACT_PRESCRIBER
    assert A.SEVERITY_TO_ACTION[A.MODERATE] == A.DISPENSE_WITH_NOTE


# ── Interaction alerts ────────────────────────────────────────────────────────

def test_interaction_alert_is_contraindicated_and_explains_mechanism():
    item = {
        "drug_a": "warfarin", "drug_b": "amiodarone",
        "severity": "contre_indique",
        "effect": "Elevated INR and major bleeding risk.",
        "mechanism": "Amiodarone inhibits warfarin metabolism.",
        "source": "ANSM",
    }
    alert = A.build_interaction_alert(item, 1, {"amiodarone"}, {"warfarin"})

    assert alert["severity"] == A.CONTRAINDICATED
    assert alert["recommended_action"] == A.DO_NOT_DISPENSE
    assert alert["drugs_involved"] == ["warfarin", "amiodarone"]

    chain = " ".join(alert["reasoning_chain"])
    assert "Amiodarone inhibits warfarin metabolism." in chain
    assert "Elevated INR" in chain
    assert "CONTRAINDICATED" in chain
    # the chain must say where each drug came from
    assert "newly prescribed" in chain and "active medication" in chain


def test_interaction_chain_omits_absent_fields_rather_than_inventing():
    item = {"drug_a": "drug_x", "drug_b": "drug_y", "severity": "moderate"}
    alert = A.build_interaction_alert(item, 1, set(), set())
    chain = " ".join(alert["reasoning_chain"])
    assert "None" not in chain
    assert "Mechanism" not in chain
    assert "Expected clinical effect" not in chain


# ── CYP alerts ────────────────────────────────────────────────────────────────

def test_cyp_alert_explains_the_pathway_and_absence_of_direct_edge():
    item = {
        "substrate": "simvastatin", "modulator": "clarithromycin",
        "enzyme": "CYP3A4", "effect": "INHIBITS", "strength": "strong",
        "risk": "simvastatin accumulation risk",
    }
    alert = A.build_cyp_alert(item, 1, {"clarithromycin"}, {"simvastatin"})

    assert alert["severity"] == A.MAJOR
    assert alert["recommended_action"] == A.CONTACT_PRESCRIBER

    chain = " ".join(alert["reasoning_chain"])
    assert "strong inhibitor of CYP3A4" in chain
    assert "metabolised by CYP3A4" in chain
    assert "no direct interaction edge" in chain.lower()
    assert "cleared more slowly" in chain


def test_cyp_inducer_explains_loss_of_effect_not_accumulation():
    item = {
        "substrate": "warfarin", "modulator": "rifampicin",
        "enzyme": "CYP2C9", "effect": "INDUCES", "strength": "strong",
        "risk": "warfarin subtherapeutic risk",
    }
    alert = A.build_cyp_alert(item, 1, {"rifampicin"}, {"warfarin"})
    chain = " ".join(alert["reasoning_chain"])
    assert "cleared faster" in chain
    assert "below" in chain
    assert "accumulation" not in chain


def test_weak_cyp_competition_is_minor():
    item = {"substrate": "a", "modulator": "b", "enzyme": "CYP2D6",
            "effect": "INHIBITS", "strength": "weak"}
    assert A.build_cyp_alert(item, 1, set(), set())["severity"] == A.MINOR


# ── Allergy, contraindication, duplication, dose ──────────────────────────────

def test_direct_allergy_is_contraindicated_cross_reactive_is_major():
    direct = A.build_allergy_alert(
        {"type": "direct", "patient_allergy": "penicillin", "drug_group": "penicillins"},
        "amoxicillin", 1,
    )
    cross = A.build_allergy_alert(
        {"type": "cross_reactive", "patient_allergy": "penicillin",
         "drug_group": "cephalosporins"},
        "cephalexin", 2,
    )

    assert direct["severity"] == A.CONTRAINDICATED
    assert direct["recommended_action"] == A.DO_NOT_DISPENSE
    assert "anaphylaxis" in " ".join(direct["reasoning_chain"])

    assert cross["severity"] == A.MAJOR
    assert "cross-react" in " ".join(cross["reasoning_chain"]).lower()


def test_contraindication_alert_cites_condition_and_icd_code():
    item = {
        "input_condition": "CKD stage 4", "matched_concept": "chronic kidney disease",
        "icd_code": "N18", "severity": "contraindicated",
        "reason": "Risk of lactic acidosis.", "source": "ANSM",
    }
    alert = A.build_contraindication_alert(item, "metformin", 1)
    chain = " ".join(alert["reasoning_chain"])

    assert alert["severity"] == A.CONTRAINDICATED
    assert "CKD stage 4" in chain
    assert "N18" in chain
    assert "lactic acidosis" in chain


def test_duplication_alert_names_both_forms():
    alert = A.build_duplication_alert(
        {"input_name": "Tahor", "resolved_inn": "atorvastatin", "same_as": "atorvastatin"}, 1
    )
    chain = " ".join(alert["reasoning_chain"])
    assert alert["severity"] == A.MAJOR
    assert alert["recommended_action"] == A.CONTACT_PRESCRIBER
    assert "Tahor" in chain and "atorvastatin" in chain
    assert "double" in chain


def test_dose_alert_is_review_prompt_not_a_calculated_dose():
    rec = {"flag": "renal_impairment", "reason": "creatinine=210 umol/L",
           "guidance": "Reduce to 250mg every 24h."}
    alert = A.build_dose_alert(
        rec, "ciprofloxacin",
        {"prescribed_dose": "500mg", "standard_dose": "500mg every 12h"}, 1,
    )
    chain = " ".join(alert["reasoning_chain"])

    assert alert["severity"] == A.MODERATE
    assert "reduced renal function" in chain
    assert "Reduce to 250mg every 24h." in chain
    assert "not a calculated dose" in chain


# ── Report-level roll-up ──────────────────────────────────────────────────────

def _alert(severity, action):
    return {"severity": severity, "severity_rank": A.SEVERITY_RANK[severity],
            "recommended_action": action, "type": "interaction", "id": "X"}


def test_alerts_sort_most_dangerous_first():
    unsorted = [
        _alert(A.MODERATE, A.DISPENSE_WITH_NOTE),
        _alert(A.CONTRAINDICATED, A.DO_NOT_DISPENSE),
        _alert(A.MINOR, A.DISPENSE_WITH_NOTE),
        _alert(A.MAJOR, A.CONTACT_PRESCRIBER),
    ]
    ordered = A.sort_alerts(unsorted)
    assert [a["severity"] for a in ordered] == [
        A.CONTRAINDICATED, A.MAJOR, A.MODERATE, A.MINOR
    ]


def test_overall_action_takes_the_most_cautious_finding():
    assert A.overall_action([]) == A.DISPENSE
    assert A.overall_action([
        _alert(A.MODERATE, A.DISPENSE_WITH_NOTE),
        _alert(A.CONTRAINDICATED, A.DO_NOT_DISPENSE),
    ]) == A.DO_NOT_DISPENSE
    assert A.overall_action([
        _alert(A.MODERATE, A.DISPENSE_WITH_NOTE),
        _alert(A.MAJOR, A.CONTACT_PRESCRIBER),
    ]) == A.CONTACT_PRESCRIBER


def test_overall_risk_levels():
    assert A.overall_risk([]) == "NONE"
    assert A.overall_risk([_alert(A.MINOR, A.DISPENSE_WITH_NOTE)]) == "LOW"
    assert A.overall_risk([_alert(A.MODERATE, A.DISPENSE_WITH_NOTE)]) == "MEDIUM"
    assert A.overall_risk([_alert(A.MAJOR, A.CONTACT_PRESCRIBER)]) == "HIGH"
    assert A.overall_risk([_alert(A.CONTRAINDICATED, A.DO_NOT_DISPENSE)]) == "HIGH"


def test_every_severity_has_a_colour_for_the_interface():
    for severity in (A.CONTRAINDICATED, A.MAJOR, A.MODERATE, A.MINOR):
        assert A.SEVERITY_COLOR[severity]
    assert A.SEVERITY_COLOR[A.CONTRAINDICATED] == "red"
    assert A.SEVERITY_COLOR[A.MAJOR] == "orange"
    assert A.SEVERITY_COLOR[A.MODERATE] == "yellow"
