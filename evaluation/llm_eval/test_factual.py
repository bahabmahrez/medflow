"""
Tier 1 — Factual evaluation tests (10 cases).
All marked @pytest.mark.live: require ANTHROPIC_API_KEY + running Neo4j.

Run:
    python -m pytest evaluation/llm_eval/test_factual.py -v -m live
"""
import os
import pytest
from unittest.mock import patch

from evaluation.llm_eval.cases import TIER1
from evaluation.llm_eval.runner import score


# ── Unit tests — score() logic only (no API, no graph) ────────────────────────

def test_score_pass_when_all_conditions_met():
    case = {
        "expected_drugs": ["warfarin"],
        "expected_risk": "HIGH",
        "answer_must_contain": ["contraindicated"],
        "answer_must_not_contain": ["safe"],
    }
    result = {
        "drugs_detected": ["warfarin"],
        "risk_level": "HIGH",
        "answer": "This combination is CONTRAINDICATED.",
    }
    s = score(case, result)
    assert s["passed"]
    assert s["failures"] == []


def test_score_fail_missing_drug():
    case = {
        "expected_drugs": ["warfarin", "amiodarone"],
        "expected_risk": None,
        "answer_must_contain": [],
        "answer_must_not_contain": [],
    }
    result = {
        "drugs_detected": ["warfarin"],
        "risk_level": None,
        "answer": "some answer",
    }
    s = score(case, result)
    assert not s["passed"]
    assert any("amiodarone" in f for f in s["failures"])


def test_score_fail_wrong_risk():
    case = {
        "expected_drugs": [],
        "expected_risk": "HIGH",
        "answer_must_contain": [],
        "answer_must_not_contain": [],
    }
    result = {"drugs_detected": [], "risk_level": "MEDIUM", "answer": ""}
    s = score(case, result)
    assert not s["passed"]
    assert any("risk_level" in f for f in s["failures"])


def test_score_fail_answer_missing_required_phrase():
    case = {
        "expected_drugs": [],
        "expected_risk": None,
        "answer_must_contain": ["contraindicated", "contre-indiqué"],
        "answer_must_not_contain": [],
    }
    result = {"drugs_detected": [], "risk_level": None, "answer": "Please use with caution."}
    s = score(case, result)
    assert not s["passed"]


def test_score_fail_answer_contains_forbidden_phrase():
    case = {
        "expected_drugs": [],
        "expected_risk": None,
        "answer_must_contain": [],
        "answer_must_not_contain": ["safe to combine"],
    }
    result = {
        "drugs_detected": [], "risk_level": None,
        "answer": "This combination is safe to combine without concern.",
    }
    s = score(case, result)
    assert not s["passed"]


def test_score_or_logic_for_must_contain():
    """answer_must_contain uses OR: any one phrase is enough."""
    case = {
        "expected_drugs": [],
        "expected_risk": None,
        "answer_must_contain": ["phrase_a", "phrase_b", "phrase_c"],
        "answer_must_not_contain": [],
    }
    result = {"drugs_detected": [], "risk_level": None, "answer": "phrase_b is here"}
    s = score(case, result)
    assert s["passed"]


# ── Live tests — real pipeline (10 Tier 1 cases) ──────────────────────────────

@pytest.mark.live
@pytest.mark.parametrize("case", TIER1, ids=[c["id"] for c in TIER1])
def test_tier1_live(case):
    """Run each Tier 1 case through the real pipeline and score it."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    from graphrag import ask
    result = ask(case["question"], **case["ask_kwargs"])
    scored = score(case, result)

    assert scored["passed"], (
        f"[{case['id']}] {case['description']}\n"
        + "\n".join(f"  ✗ {f}" for f in scored["failures"])
    )
