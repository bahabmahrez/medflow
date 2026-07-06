"""
Ambiguity scenario tests (7 cases) — the agent must ask a clarifying question
rather than guess at a missing drug, dose, or patient reference.

Run:
    python -m pytest evaluation/agent_eval/test_ambiguity.py -v -m live
"""
import os
import pytest

from evaluation.agent_eval.cases import AMBIGUITY
from evaluation.agent_eval.runner import score_agent
from agent.trace import new_trace, new_step


def _live_key_available() -> bool:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    return bool(os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _fake_run_result(final_answer: str) -> dict:
    trace = new_trace("q", None)
    trace["steps"].append(new_step(1, final_answer, []))
    trace["final_answer"] = final_answer
    trace["iterations"] = 1
    trace["stopped_reason"] = "final_answer"
    return {"final_answer": final_answer, "trace": trace}


# ── Unit tests — clarifying-question heuristic (mocked) ──────────────────────

def test_clarifying_question_passes():
    case = next(c for c in AMBIGUITY if c["id"] == "AMB-01")
    run_result = _fake_run_result("What unit was that dose given in — milligrams?")
    scored = score_agent(case, run_result)
    assert scored["passed"]


def test_confident_guess_fails_ambiguity_check():
    """A bad agent assumes the unit and answers confidently — must fail."""
    case = next(c for c in AMBIGUITY if c["id"] == "AMB-01")
    run_result = _fake_run_result("500mg metformin twice daily is contraindicated given her renal labs.")
    scored = score_agent(case, run_result)
    assert not scored["passed"]
    assert any("clarifying question" in f for f in scored["failures"])


def test_question_mark_alone_is_not_enough_if_severity_asserted():
    """A rhetorical '?' tacked onto an asserted finding should not count as asking."""
    case = next(c for c in AMBIGUITY if c["id"] == "AMB-01")
    run_result = _fake_run_result("This combination is contraindicated, don't you agree?")
    scored = score_agent(case, run_result)
    assert not scored["passed"]


def test_all_seven_cases_marked_as_clarifying():
    assert len(AMBIGUITY) == 7
    assert all(c["is_clarifying_question"] for c in AMBIGUITY)


# ── Live tests ────────────────────────────────────────────────────────────────

@pytest.mark.live
@pytest.mark.parametrize("case", AMBIGUITY, ids=[c["id"] for c in AMBIGUITY])
def test_ambiguity_live(case):
    if not _live_key_available():
        pytest.skip("no LLM API key configured for the active provider")

    from agent import run_agent
    from agent.trace import pretty_print

    result = run_agent(case["question"], patient_context=case.get("patient_context"))
    scored = score_agent(case, result)

    assert scored["passed"], (
        f"[{case['id']}] {case['description']}\n"
        + "\n".join(f"  X {f}" for f in scored["failures"])
        + "\n\n" + pretty_print(result["trace"])
    )
