"""
Multi-tool scenario tests (10 cases) — open-ended prescriptions requiring the
agent to independently choose several checks in sequence.

Mocked unit tests always run (loop/scoring mechanics). The @pytest.mark.live
tests run the real agent against a live LLM + Neo4j.

Run:
    python -m pytest evaluation/agent_eval/test_multi_tool.py -v -m live
"""
import os
import pytest

from evaluation.agent_eval.cases import MULTI_TOOL
from evaluation.agent_eval.runner import score_agent
from agent.trace import new_trace, new_step, log_execution


def _live_key_available() -> bool:
    """Unlike llm_eval (hardcoded to ANTHROPIC_API_KEY), this checks whichever
    provider is actually configured — this repo runs on Groq."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    return bool(os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))


# ── Unit tests — scoring logic (mocked, no LLM/Neo4j) ────────────────────────

def _fake_run_result(tool_names: list[str], final_answer: str) -> dict:
    trace = new_trace("q", None)
    step = new_step(1, "", [{"id": f"call_{i}", "name": n, "arguments": {}} for i, n in enumerate(tool_names)])
    for i, name in enumerate(tool_names):
        log_execution(step, f"call_{i}", name, {}, {"status": "found", "data": {}, "message": "ok"}, 1.0)
    trace["steps"].append(step)
    trace["final_answer"] = final_answer
    trace["iterations"] = 1
    trace["stopped_reason"] = "final_answer"
    return {"final_answer": final_answer, "trace": trace}


def test_full_prescription_check_satisfies_granular_expected_set():
    """A model calling the consolidated tool instead of granular ones is not wrong."""
    case = next(c for c in MULTI_TOOL if c["id"] == "MT-01")
    run_result = _fake_run_result(["full_prescription_check"], "This is a MAJOR interaction — bleeding risk.")
    scored = score_agent(case, run_result)
    assert scored["passed"]


def test_wrong_tool_choice_fails_scoring():
    case = next(c for c in MULTI_TOOL if c["id"] == "MT-01")
    run_result = _fake_run_result(["get_drug_profile"], "This is a MAJOR interaction — bleeding risk.")
    scored = score_agent(case, run_result)
    assert not scored["passed"]
    assert any("no expected tool set matched" in f for f in scored["failures"])


def test_missing_required_phrase_fails_scoring():
    case = next(c for c in MULTI_TOOL if c["id"] == "MT-01")
    run_result = _fake_run_result(["detect_pairwise_interactions"], "Everything looks fine, no concerns.")
    scored = score_agent(case, run_result)
    assert not scored["passed"]
    assert any("missing required phrase" in f for f in scored["failures"])


def test_all_ten_cases_have_non_empty_expected_tool_sets():
    for case in MULTI_TOOL:
        assert case["expected_tool_sets"], f"{case['id']} has no expected tool sets"


# ── Live tests ────────────────────────────────────────────────────────────────

@pytest.mark.live
@pytest.mark.parametrize("case", MULTI_TOOL, ids=[c["id"] for c in MULTI_TOOL])
def test_multi_tool_live(case):
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
