"""Tests for interface.prescriber - drafting the message to the prescriber."""
from __future__ import annotations

from datetime import date

from interface.prescriber import draft_prescriber_message

ALERT = {
    "id": "INT-01",
    "type": "interaction",
    "severity": "contraindicated",
    "title": "Simvastatin + Clarithromycin - contraindicated interaction",
    "explanation": "Clarithromycin blocks simvastatin metabolism; rhabdomyolysis risk.",
    "reasoning_chain": [
        "Simvastatin is an active medication; clarithromycin is newly prescribed.",
        "The knowledge base records a documented interaction, graded CONTRAINDICATED.",
        "Mechanism - CYP3A4 inhibition.",
    ],
    "recommended_action": "do_not_dispense",
    "drugs_involved": ["simvastatin", "clarithromycin"],
}

PATIENT = {
    "id": 181, "name": "Karim Ben Salah", "dob": date(1958, 4, 12), "age": 68,
    "active_meds": [{"inn": "warfarin"}, {"inn": "simvastatin"}],
}

PRESCRIPTION = [{"drug": "clarithromycin", "dose": "500mg"}]


def _draft(**kwargs):
    params = {"patient": PATIENT, "prescription": PRESCRIPTION,
              "pharmacist_name": "A. Ben Salah"}
    params.update(kwargs)
    return draft_prescriber_message(ALERT, **params)


def test_message_identifies_the_patient_and_the_new_drug():
    text = _draft()
    assert "Karim Ben Salah" in text
    assert "12/04/1958" in text
    assert "clarithromycin" in text


def test_message_states_the_finding_and_its_severity():
    text = _draft()
    assert "CONTRAINDICATED" in text
    assert "Simvastatin + Clarithromycin" in text
    assert "rhabdomyolysis" in text


def test_message_includes_the_reasoning_so_the_query_is_answerable():
    text = _draft()
    assert "Why this was flagged:" in text
    for step in ALERT["reasoning_chain"]:
        assert step in text


def test_message_lists_current_medications():
    text = _draft()
    assert "warfarin" in text and "simvastatin" in text


def test_ask_matches_the_recommended_action():
    holding = _draft()
    assert "holding the dispensation" in holding

    softer = draft_prescriber_message(
        {**ALERT, "recommended_action": "dispense_with_note"},
        patient=PATIENT, prescription=PRESCRIPTION,
    )
    assert "counselling" in softer
    assert "holding the dispensation" not in softer


def test_message_is_signed():
    assert _draft().rstrip().endswith("A. Ben Salah")
    assert draft_prescriber_message(ALERT, patient=PATIENT).rstrip().endswith("[Pharmacist]")


def test_previous_review_is_mentioned_as_context():
    alert = {**ALERT, "memory": {
        "reviewed_ago": "3 days ago", "decision": "overridden",
        "decision_label": "overridden", "note": "Prescriber aware.",
    }}
    text = draft_prescriber_message(alert, patient=PATIENT)
    assert "3 days ago" in text
    assert "Prescriber aware." in text


def test_draft_survives_a_sparse_alert_without_inventing_content():
    text = draft_prescriber_message({"title": "Something", "severity": "minor"})
    assert "Something" in text
    assert "None" not in text
    assert "Why this was flagged:" not in text


def test_message_is_console_safe():
    """The demo prints these; the project's console is cp1252."""
    _draft().encode("cp1252")
