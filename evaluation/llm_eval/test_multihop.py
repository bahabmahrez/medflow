"""
Tier 2 — Multi-hop evaluation tests (10 cases).
These cases require graph traversal: CYP 2-hop paths, 3-drug sets,
patient context flags, brand→INN resolution chains.

All marked @pytest.mark.live: require ANTHROPIC_API_KEY + running Neo4j.

Run:
    python -m pytest evaluation/llm_eval/test_multihop.py -v -m live
"""
import os
import pytest

from evaluation.llm_eval.cases import TIER2
from evaluation.llm_eval.runner import score


# ── Unit tests — context assembly (mocked graph + LLM) ────────────────────────

def test_three_drug_question_check_all_pairs():
    """
    For a 3-drug question (warfarin + aspirin + amiodarone), the pipeline must
    detect all three drugs and check pairwise interactions.
    We verify this by inspecting the context, not the LLM answer.
    """
    from unittest.mock import patch

    def fake_resolve(name):
        mapping = {"warfarin": "warfarin", "aspirin": "aspirin", "amiodarone": "amiodarone"}
        inn = mapping.get(name)
        if inn:
            return {"status": "found", "data": {"canonical": inn, "inn": inn}, "message": ""}
        return {"status": "not_found", "data": {}, "message": ""}

    ix_result = {
        "status": "found",
        "data": {
            "drugs_resolved": ["warfarin", "aspirin", "amiodarone"],
            "drugs_unresolved": [],
            "pairs_checked": 3,
            "interactions_found": 2,
            "interactions": [
                {"drug_a": "warfarin", "drug_b": "amiodarone",
                 "severity": "contre_indique", "effect": "INR elevation",
                 "mechanism": "CYP", "source": "ANSM"},
                {"drug_a": "warfarin", "drug_b": "aspirin",
                 "severity": "major", "effect": "bleeding",
                 "mechanism": "additive", "source": "ANSM"},
            ],
        },
        "message": "",
    }
    cyp_result = {
        "status": "not_found",
        "data": {"drugs_resolved": [], "drugs_unresolved": [], "competitions_found": 0, "competitions": []},
        "message": "",
    }

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve), \
         patch("graphrag.pipeline.detect_pairwise_interactions", return_value=ix_result), \
         patch("graphrag.pipeline.detect_cyp_competition", return_value=cyp_result), \
         patch("graphrag.pipeline.generate", return_value="Multiple dangerous interactions detected."):
        from graphrag import ask
        r = ask("Patient is on warfarin and aspirin. I want to add amiodarone.")

    assert set(r["drugs_detected"]) == {"warfarin", "aspirin", "amiodarone"}
    assert r["risk_level"] == "HIGH"
    assert "PAIRWISE INTERACTIONS" in r["context"]
    assert "contre_indique" in r["context"]
    assert "major" in r["context"]


def test_brand_resolution_reflected_in_detected_drugs():
    """Brand name 'Coumadin' must resolve to INN 'warfarin' in drugs_detected."""
    from unittest.mock import patch

    def fake_resolve(name):
        if name in ("coumadin", "warfarin"):
            return {"status": "found", "data": {"canonical": "warfarin", "inn": "warfarin"}, "message": ""}
        if name == "aspirin":
            return {"status": "found", "data": {"canonical": "aspirin", "inn": "aspirin"}, "message": ""}
        return {"status": "not_found", "data": {}, "message": ""}

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve), \
         patch("graphrag.pipeline.detect_pairwise_interactions",
               return_value={"status": "not_found", "data": {"drugs_resolved": ["warfarin", "aspirin"],
               "drugs_unresolved": [], "pairs_checked": 1, "interactions_found": 0, "interactions": []}, "message": ""}), \
         patch("graphrag.pipeline.detect_cyp_competition",
               return_value={"status": "not_found", "data": {"drugs_resolved": [], "drugs_unresolved": [],
               "competitions_found": 0, "competitions": []}, "message": ""}), \
         patch("graphrag.pipeline.generate", return_value="answer"):
        from graphrag import ask
        r = ask("Can Coumadin be taken with aspirin?")

    assert "warfarin" in r["drugs_detected"]
    assert "aspirin" in r["drugs_detected"]
    assert "coumadin" not in r["drugs_detected"]  # brand resolved to INN


def test_cyp_competition_context_included_for_two_drug_question():
    """CYP context section must appear even if competitions_found=0."""
    from unittest.mock import patch

    def fake_resolve(name):
        if name in ("simvastatin", "clarithromycin"):
            return {"status": "found", "data": {"canonical": name, "inn": name}, "message": ""}
        return {"status": "not_found", "data": {}, "message": ""}

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve), \
         patch("graphrag.pipeline.detect_pairwise_interactions",
               return_value={"status": "not_found", "data": {"drugs_resolved": ["simvastatin", "clarithromycin"],
               "drugs_unresolved": [], "pairs_checked": 1, "interactions_found": 0, "interactions": []}, "message": ""}), \
         patch("graphrag.pipeline.detect_cyp_competition",
               return_value={"status": "found", "data": {"drugs_resolved": ["simvastatin", "clarithromycin"],
               "drugs_unresolved": [], "competitions_found": 1, "competitions": [
                   {"substrate": "simvastatin", "modulator": "clarithromycin",
                    "enzyme": "CYP3A4", "effect": "INHIBITS", "strength": "strong",
                    "risk": "simvastatin accumulation risk"}
               ]}, "message": ""}), \
         patch("graphrag.pipeline.generate", return_value="HIGH risk via CYP3A4."):
        from graphrag import ask
        r = ask("Is simvastatin safe with clarithromycin?")

    assert "CYP ENZYME COMPETITION" in r["context"]
    assert "CYP3A4" in r["context"]
    assert r["risk_level"] == "HIGH"


# ── Live tests — real pipeline (10 Tier 2 cases) ──────────────────────────────

@pytest.mark.live
@pytest.mark.parametrize("case", TIER2, ids=[c["id"] for c in TIER2])
def test_tier2_live(case):
    """Run each Tier 2 case through the real pipeline and score it."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    from graphrag import ask
    result = ask(case["question"], **case["ask_kwargs"])
    scored = score(case, result)

    assert scored["passed"], (
        f"[{case['id']}] {case['description']}\n"
        + "\n".join(f"  ✗ {f}" for f in scored["failures"])
    )
