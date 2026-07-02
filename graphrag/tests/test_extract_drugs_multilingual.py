import pytest
from unittest.mock import patch


def _fake_resolve_factory(mapping):
    def _fake_resolve(name: str):
        # emulate query.resolve.resolve_drug_name envelope
        if name in mapping:
            inn = mapping[name]
            return {"status": "found", "data": {"canonical": inn, "rxnorm_cui": None, "match_type": "mock"}, "message": ""}
        return {"status": "not_found", "data": {}, "message": "not found"}

    return _fake_resolve


@patch("graphrag._drug_extraction.resolve_drug_name")
def test_extract_drugs_fuzzy_typo(mock_resolve):
    # We simulate fuzzy behaviour by expecting our fuzzy pass to generate an alt token
    # then resolve_drug_name succeeds for that alt.
    # For determinism, we map the alternates we expect to be tried.
    mapping = {
        # exact failed
        "paracetamol": "paracetamol",
        "doliprane": "paracetamol",  # brand mapping should be handled by resolve_drug_name normally;
        # here we just make it work through our final strict resolve.
        "dolipran": "paracetamol",  # fuzzy candidate alt
    }
    mock_resolve.side_effect = _fake_resolve_factory(mapping)

    from graphrag.pipeline import extract_drugs

    # misspelling variant ("Dolipran" -> "dolipran" alt in our fuzzer-ish logic)
    drugs = extract_drugs("Puis-je prendre Dolipran pour la douleur ?")
    assert "paracetamol" in drugs


@patch("graphrag._drug_extraction.resolve_drug_name")
def test_extract_drugs_brand_name_mapping(mock_resolve):
    mapping = {
        "doliprane": "paracetamol",
        "paracetamol": "paracetamol",
    }
    mock_resolve.side_effect = _fake_resolve_factory(mapping)

    from graphrag.pipeline import extract_drugs

    drugs = extract_drugs("Doliprane est-il compatible ?")
    assert drugs == ["paracetamol"]


@patch("graphrag._drug_extraction.resolve_drug_name")
def test_extract_drugs_arabic_normalization(mock_resolve):
    # Arabic normalization should allow variants like أدوية/اسم with hamza.
    mapping = {
        # Input token after normalization should match here
        "باراسيتامول": "paracetamol",
    }
    mock_resolve.side_effect = _fake_resolve_factory(mapping)

    from graphrag.pipeline import extract_drugs

    # Arabic token with hamza form and diacritics removed in normalization.
    drugs = extract_drugs("هل يمكنني تناول باراسيتامول؟")
    assert drugs == ["paracetamol"]

