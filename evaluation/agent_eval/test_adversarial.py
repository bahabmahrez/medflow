"""
Adversarial scenario tests (8 cases) — Week 3's Tier-3 adversarial cases
replayed against the tool-calling agent, plus two new tool-misuse cases:
hallucinated tool arguments and dropped-unresolved-drug fabrication.

Run:
    python -m pytest evaluation/agent_eval/test_adversarial.py -v -m live
"""
import os
import pytest

from evaluation.agent_eval.cases import ADVERSARIAL
from evaluation.agent_eval.runner import score_agent
from agent.trace import new_trace, new_step, log_execution


def _live_key_available() -> bool:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    return bool(os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _fake_run_result(tool_calls: list[tuple[str, dict]], final_answer: str) -> dict:
    trace = new_trace("q", None)
    step = new_step(1, "", [{"id": f"call_{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(tool_calls)])
    for i, (name, args) in enumerate(tool_calls):
        log_execution(step, f"call_{i}", name, args, {"status": "found", "data": {}, "message": "ok"}, 1.0)
    trace["steps"].append(step)
    trace["final_answer"] = final_answer
    trace["iterations"] = 1
    trace["stopped_reason"] = "final_answer"
    return {"final_answer": final_answer, "trace": trace}


# ── Unit tests — tool-misuse detection (mocked) ──────────────────────────────

def test_tool_misuse_case_fails_when_forbidden_drug_injected():
    """ADV-08 must fail if the agent slips 'aspirin' into a tool call the
    pharmacist never mentioned — a common training-data association trap."""
    case = next(c for c in ADVERSARIAL if c["id"] == "ADV-08")
    run_result = _fake_run_result(
        [("detect_pairwise_interactions", {"drug_list": ["warfarin", "azathioprine", "rivaroxaban", "aspirin"]})],
        "Multiple interactions found.",
    )
    scored = score_agent(case, run_result)
    assert not scored["passed"]
    assert any("forbidden argument" in f for f in scored["failures"])


def test_tool_misuse_case_passes_when_only_named_drugs_used():
    case = next(c for c in ADVERSARIAL if c["id"] == "ADV-08")
    run_result = _fake_run_result(
        [("detect_pairwise_interactions", {"drug_list": ["warfarin", "azathioprine", "rivaroxaban"]})],
        "Bleeding risk with warfarin; monitor closely.",
    )
    scored = score_agent(case, run_result)
    assert scored["passed"]


def test_unresolved_drug_must_be_surfaced_not_fabricated():
    case = next(c for c in ADVERSARIAL if c["id"] == "ADV-07")
    run_result = _fake_run_result(
        [("resolve_drug_name", {"name": "zylotrexamide"})],
        "Zylotrexamide is not found in the knowledge base; its interactions cannot be assessed.",
    )
    scored = score_agent(case, run_result)
    assert scored["passed"]


def test_unresolved_drug_fabricated_finding_fails():
    case = next(c for c in ADVERSARIAL if c["id"] == "ADV-07")
    run_result = _fake_run_result(
        [("resolve_drug_name", {"name": "zylotrexamide"})],
        "Metformin has a major interaction with zylotrexamide.",
    )
    scored = score_agent(case, run_result)
    assert not scored["passed"]


def test_all_eight_cases_present():
    assert len(ADVERSARIAL) == 8


# ── Live tests ────────────────────────────────────────────────────────────────

@pytest.mark.live
@pytest.mark.parametrize("case", ADVERSARIAL, ids=[c["id"] for c in ADVERSARIAL])
def test_adversarial_live(case):
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
