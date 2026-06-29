"""
Tests for resolve_drug_name — 5 cases covering INN, brand, Tunisian brand,
invented name, and case-insensitivity.
"""
import pytest
from query.resolve import resolve_drug_name


def test_resolve_by_inn():
    r = resolve_drug_name("warfarin")
    assert r["status"] == "found"
    assert r["data"]["canonical"] == "warfarin"
    assert r["data"]["match_type"] == "inn"


def test_resolve_brand_to_inn():
    """Tahor is the brand name for atorvastatin."""
    r = resolve_drug_name("Tahor")
    assert r["status"] == "found"
    assert r["data"]["canonical"] == "atorvastatin"
    assert r["data"]["match_type"] == "brand"


def test_resolve_tunisian_brand():
    """Lasilix is the Tunisian brand for furosemide."""
    r = resolve_drug_name("Lasilix")
    assert r["status"] == "found"
    assert r["data"]["canonical"] == "furosemide"


def test_resolve_case_insensitive():
    r = resolve_drug_name("WARFARIN")
    assert r["status"] == "found"
    assert r["data"]["canonical"] == "warfarin"


def test_resolve_unknown_drug():
    """An invented name must return not_found, never invent a result."""
    r = resolve_drug_name("zyboxithol")
    assert r["status"] == "not_found"
    assert r["data"] == {}


def test_resolve_empty_string():
    r = resolve_drug_name("")
    assert r["status"] == "error"


def test_resolve_coumadin():
    """Coumadin (French brand) resolves to warfarin."""
    r = resolve_drug_name("Coumadin")
    assert r["status"] == "found"
    assert r["data"]["canonical"] == "warfarin"
