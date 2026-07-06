"""
Meta-test: across the full 25-case suite, every one of the 10 registered
tools must be reachable by at least one case's expected_tool_sets — proving
Milestone 1's tool wrapping isn't decorative, not just that a handful of
tools get exercised repeatedly.

Run:
    python -m pytest evaluation/agent_eval/test_coverage.py -v -m live
"""
import os
import pytest

from evaluation.agent_eval.cases import CASES, ALL_TOOL_NAMES
from agent.tools import TOOL_REGISTRY


def test_registry_matches_declared_tool_name_set():
    assert set(TOOL_REGISTRY.keys()) == ALL_TOOL_NAMES


def test_expected_tool_sets_cover_every_registered_tool():
    """Static check (no LLM call): every tool appears in at least one case's
    expected_tool_sets, so the suite is capable of exercising all 10 tools."""
    named_in_expectations = {
        name
        for case in CASES
        for tool_set in case["expected_tool_sets"]
        for name in tool_set
    }
    missing = ALL_TOOL_NAMES - named_in_expectations
    assert not missing, f"No case expects these tools to ever be called: {missing}"


@pytest.mark.live
def test_full_tool_coverage_live():
    """Across real agent runs of all 25 cases, the union of tools actually
    invoked must equal the full registered set."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    has_key = (
        bool(os.getenv("ANTHROPIC_API_KEY")) if provider == "anthropic"
        else bool(os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))
    )
    if not has_key:
        pytest.skip("no LLM API key configured for the active provider")

    from agent import run_agent
    from agent.trace import all_tool_names

    invoked = set()
    for case in CASES:
        result = run_agent(case["question"], patient_context=case.get("patient_context"))
        invoked.update(all_tool_names(result["trace"]))

    missing = ALL_TOOL_NAMES - invoked
    assert not missing, f"These tools were never actually invoked across all 25 live runs: {missing}"
