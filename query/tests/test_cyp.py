"""
Tests for detect_cyp_competition — covers 2-hop CYP paths that have no
direct DDI edge.  These are the cases that prove the graph's worth.
"""
import pytest
from query.interactions import detect_cyp_competition


def test_simvastatin_clarithromycin_cyp3a4():
    """
    Core trap03 case: clarithromycin strongly inhibits CYP3A4, simvastatin
    is a substrate.  No direct DDI edge — only detectable via the graph.
    """
    r = detect_cyp_competition(["simvastatin", "clarithromycin"])
    assert r["status"] == "found"
    comps = r["data"]["competitions"]
    cyp3a4 = [c for c in comps if c["enzyme"] == "CYP3A4"]
    assert len(cyp3a4) >= 1
    assert cyp3a4[0]["substrate"] == "simvastatin"
    assert cyp3a4[0]["modulator"] == "clarithromycin"
    assert cyp3a4[0]["effect"] == "INHIBITS"


def test_warfarin_fluconazole_cyp2c9():
    """Fluconazole strongly inhibits CYP2C9; warfarin is CYP2C9 substrate (trap07)."""
    r = detect_cyp_competition(["warfarin", "fluconazole"])
    assert r["status"] == "found"
    comps = r["data"]["competitions"]
    cyp2c9 = [c for c in comps if c["enzyme"] == "CYP2C9"]
    assert len(cyp2c9) >= 1
    assert cyp2c9[0]["substrate"] == "warfarin"
    assert cyp2c9[0]["modulator"] == "fluconazole"
    assert cyp2c9[0]["strength"] == "strong"


def test_rifampicin_warfarin_induction():
    """Rifampicin induces CYP2C9 — warfarin substrate (trap10, subtherapeutic risk)."""
    r = detect_cyp_competition(["warfarin", "rifampicin"])
    assert r["status"] == "found"
    comps = r["data"]["competitions"]
    induces = [c for c in comps if c["effect"] == "INDUCES"]
    assert len(induces) >= 1
    assert any(c["substrate"] == "warfarin" for c in induces)


def test_tramadol_fluoxetine_cyp2d6():
    """Fluoxetine inhibits CYP2D6; tramadol is a CYP2D6 substrate (trap14)."""
    r = detect_cyp_competition(["tramadol", "fluoxetine"])
    assert r["status"] == "found"
    comps = r["data"]["competitions"]
    cyp2d6 = [c for c in comps if c["enzyme"] == "CYP2D6"]
    assert len(cyp2d6) >= 1


def test_clopidogrel_omeprazole_cyp2c19():
    """Omeprazole inhibits CYP2C19; clopidogrel is CYP2C19 substrate (trap13)."""
    r = detect_cyp_competition(["clopidogrel", "omeprazole"])
    assert r["status"] == "found"
    comps = r["data"]["competitions"]
    cyp2c19 = [c for c in comps if c["enzyme"] == "CYP2C19"]
    assert len(cyp2c19) >= 1
    assert any(c["substrate"] == "clopidogrel" for c in cyp2c19)


def test_no_cyp_competition_unrelated():
    """Two drugs with no CYP overlap return not_found, not an invented result."""
    r = detect_cyp_competition(["metformin", "amoxicillin"])
    assert r["status"] == "not_found"
    assert r["data"]["competitions_found"] == 0


def test_single_drug_returns_error():
    r = detect_cyp_competition(["warfarin"])
    assert r["status"] == "error"
