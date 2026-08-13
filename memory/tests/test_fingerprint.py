"""Tests for memory.fingerprint — stable identity of a finding across scans."""
from __future__ import annotations

from memory.fingerprint import fingerprint


def _alert(alert_type, drugs, **evidence):
    return {"type": alert_type, "drugs_involved": drugs, "evidence": evidence}


def test_drug_order_does_not_change_identity():
    a = _alert("interaction", ["warfarin", "aspirin"])
    b = _alert("interaction", ["aspirin", "warfarin"])
    assert fingerprint(a) == fingerprint(b)


def test_case_and_whitespace_do_not_change_identity():
    a = _alert("interaction", ["Warfarin", " ASPIRIN "])
    b = _alert("interaction", ["warfarin", "aspirin"])
    assert fingerprint(a) == fingerprint(b)


def test_direct_and_cyp_findings_for_a_pair_share_one_identity():
    """
    The engine merges these into a single alert and which one leads depends on
    severity - so they must not have different memories.
    """
    direct = _alert("interaction", ["clarithromycin", "simvastatin"])
    cyp    = _alert("cyp_competition", ["simvastatin", "clarithromycin"])
    assert fingerprint(direct) == fingerprint(cyp)


def test_different_pairs_are_different_findings():
    assert fingerprint(_alert("interaction", ["warfarin", "aspirin"])) != \
           fingerprint(_alert("interaction", ["warfarin", "amiodarone"]))


def test_contraindication_keyed_on_matched_concept_not_typed_text():
    typed_one_way = _alert("contraindication", ["metformin"],
                           condition="CKD stage 4",
                           matched_concept="chronic kidney disease", icd_code="N18")
    typed_another = _alert("contraindication", ["metformin"],
                           condition="renal failure",
                           matched_concept="chronic kidney disease", icd_code="N18")
    assert fingerprint(typed_one_way) == fingerprint(typed_another)


def test_same_drug_different_condition_is_a_different_finding():
    a = _alert("contraindication", ["metformin"], matched_concept="chronic kidney disease")
    b = _alert("contraindication", ["metformin"], matched_concept="hepatic impairment")
    assert fingerprint(a) != fingerprint(b)


def test_allergy_keyed_on_the_patient_allergy():
    a = _alert("allergy", ["amoxicillin"], patient_allergy="penicillin",
               drug_group="penicillins")
    assert fingerprint(a) == "alg:amoxicillin|penicillin"


def test_duplication_keyed_on_the_molecule_not_the_brand():
    via_brand = _alert("duplication", ["atorvastatin", "Tahor"],
                       resolved_inn="atorvastatin")
    via_other = _alert("duplication", ["atorvastatin", "Lipitor"],
                       resolved_inn="atorvastatin")
    assert fingerprint(via_brand) == fingerprint(via_other) == "dup:atorvastatin"


def test_dose_findings_separate_by_flag():
    renal   = _alert("dose", ["ciprofloxacin"], flag="renal_impairment")
    elderly = _alert("dose", ["ciprofloxacin"], flag="elderly")
    assert fingerprint(renal) != fingerprint(elderly)


def test_unknown_alert_type_is_still_given_a_stable_identity():
    a = {"type": "something_new", "drugs_involved": ["b", "a"], "evidence": {}}
    b = {"type": "something_new", "drugs_involved": ["a", "b"], "evidence": {}}
    assert fingerprint(a) == fingerprint(b) == "something_new:a|b"


def test_fingerprint_is_independent_of_the_per_run_alert_id():
    a = {"type": "interaction", "id": "INT-01",
         "drugs_involved": ["warfarin", "aspirin"], "evidence": {}}
    b = {"type": "interaction", "id": "INT-07",
         "drugs_involved": ["warfarin", "aspirin"], "evidence": {}}
    assert fingerprint(a) == fingerprint(b)
