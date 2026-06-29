"""
Tests for detect_pairwise_interactions — covers known major interactions,
known non-interactions, brand name inputs, and edge cases.
"""
import pytest
from query.interactions import detect_pairwise_interactions


def test_warfarin_aspirin_major():
    """Warfarin + aspirin is a verified major DDI (trap01)."""
    r = detect_pairwise_interactions(["warfarin", "aspirin"])
    assert r["status"] == "found"
    interactions = r["data"]["interactions"]
    assert len(interactions) >= 1
    sevs = [i["severity"] for i in interactions]
    assert any(s in ("major", "contre_indique", "deconseillee") for s in sevs)


def test_warfarin_amiodarone_contre_indique():
    """Warfarin + amiodarone is contre_indique (trap09)."""
    r = detect_pairwise_interactions(["warfarin", "amiodarone"])
    assert r["status"] == "found"
    sevs = [i["severity"] for i in r["data"]["interactions"]]
    assert "contre_indique" in sevs


def test_digoxin_amiodarone_interaction():
    """Digoxin + amiodarone interaction exists (trap20)."""
    r = detect_pairwise_interactions(["digoxin", "amiodarone"])
    assert r["status"] == "found"
    assert r["data"]["interactions_found"] >= 1


def test_three_drug_list_pairs_checked():
    """With 3 drugs, exactly 3 pairs must be checked."""
    r = detect_pairwise_interactions(["warfarin", "aspirin", "metformin"])
    assert r["data"]["pairs_checked"] == 3


def test_brand_name_inputs():
    """Brand names should resolve correctly before checking interactions."""
    r = detect_pairwise_interactions(["Coumadin", "Aspégic"])
    assert r["status"] == "found"
    assert set(r["data"]["drugs_resolved"]) == {"warfarin", "aspirin"}


def test_no_interaction_unrelated_drugs():
    """Two unrelated drugs with no known interaction return not_found."""
    r = detect_pairwise_interactions(["metformin", "amoxicillin"])
    assert r["status"] == "not_found"
    assert r["data"]["interactions_found"] == 0


def test_single_drug_returns_error():
    r = detect_pairwise_interactions(["warfarin"])
    assert r["status"] == "error"


def test_unknown_drug_skipped_gracefully():
    """An unknown drug is reported as unresolved, others still checked."""
    r = detect_pairwise_interactions(["warfarin", "aspirin", "zyboxithol"])
    assert "zyboxithol" in r["data"]["drugs_unresolved"]
    assert r["data"]["pairs_checked"] == 1  # only warfarin+aspirin pair
