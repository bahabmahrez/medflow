"""
Tests for agent.loop.run_agent — loop mechanics with generate_with_tools
and the MCP session mocked. No live LLM/Neo4j/MCP calls here.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock, AsyncMock

from agent.loop import run_agent


# ── Mock MCP helpers ──────────────────────────────────────────────────────────

class _MockTool:
    """Mimics an MCP ``types.Tool`` object with name/description/inputSchema."""
    def __init__(self, name: str, description: str = "", input_schema: dict | None = None):
        self.name = name
        self.description = description
        self.inputSchema = input_schema or {"type": "object", "properties": {}}


class _MockContent:
    """Mimics an MCP ``TextContent``."""
    def __init__(self, text: str):
        self.text = text
        self.type = "text"


class _MockCallToolResult:
    """Mimics an MCP ``CallToolResult``."""
    def __init__(self, content: list, is_error: bool = False):
        self.content = content
        self.isError = is_error


class _MockListToolsResult:
    """Mimics an MCP ``ListToolsResult``."""
    def __init__(self, tools: list):
        self.tools = tools


# The 10 MedFlow MCP tools, as they appear from session.list_tools().
_DEFAULT_MCP_TOOLS = [
    _MockTool("resolve_drug_name_tool", "Resolve a drug name to canonical INN",
              {"type": "object", "properties": {"name": {"type": "string"}}}),
    _MockTool("get_drug_profile_tool", "Full drug profile",
              {"type": "object", "properties": {"drug": {"type": "string"}}}),
    _MockTool("detect_pairwise_interactions_tool", "Direct drug interactions",
              {"type": "object", "properties": {"drug_list": {"type": "array", "items": {"type": "string"}}}}),
    _MockTool("detect_cyp_competition_tool", "CYP enzyme competition",
              {"type": "object", "properties": {"drug_list": {"type": "array", "items": {"type": "string"}}}}),
    _MockTool("check_contraindications_tool", "Contraindications vs conditions",
              {"type": "object", "properties": {"drug": {"type": "string"}, "conditions": {"type": "array", "items": {"type": "string"}}}}),
    _MockTool("check_allergy_conflict_tool", "Allergy conflicts",
              {"type": "object", "properties": {"drug": {"type": "string"}, "allergies": {"type": "array", "items": {"type": "string"}}}}),
    _MockTool("check_therapeutic_duplication_tool", "Therapeutic duplication",
              {"type": "object", "properties": {"new_drug": {"type": "string"}, "active_meds": {"type": "array", "items": {"type": "string"}}}}),
    _MockTool("check_dose_appropriateness_tool", "Dose appropriateness",
              {"type": "object", "properties": {"drug": {"type": "string"}}}),
    _MockTool("get_drugs_by_class_tool", "List drugs in a class",
              {"type": "object", "properties": {"drug_class": {"type": "string"}}}),
    _MockTool("full_prescription_check_tool", "Full safety check",
              {"type": "object", "properties": {"prescription": {"type": "array"}}}),
]


def _mock_session(call_tool_result: dict | None = None, tools: list | None = None):
    """
    Build a mock ``ClientSession`` that returns predefined tools and
    call_tool results.

    The returned object can be used as an async context manager.
    """
    session = AsyncMock()
    # list_tools
    session.list_tools = AsyncMock(return_value=_MockListToolsResult(tools or _DEFAULT_MCP_TOOLS))
    # call_tool
    if call_tool_result is None:
        call_tool_result = {"status": "found", "data": {"result": "ok"}, "message": "ok"}
    session.call_tool = AsyncMock(
        return_value=_MockCallToolResult(
            content=[_MockContent(text=json.dumps(call_tool_result))],
            is_error=False,
        )
    )
    # initialize
    session.initialize = AsyncMock()
    # async context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def _mock_stack():
    """Mock the AsyncExitStack that owns the MCP session lifecycle."""
    stack = AsyncMock()
    stack.aclose = AsyncMock(return_value=None)
    return stack


def _run_with_mocks(
    generate_responses: list,
    call_tool_result: dict | None = None,
    **agent_kwargs,
) -> dict:
    """
    Run ``run_agent()`` with both ``generate_with_tools`` and the MCP
    session mocked.

    *generate_responses* is a list of return values for
    ``generate_with_tools`` (one per turn).

    *call_tool_result* is the dict the mock ``call_tool`` should return
    (wrapped into an MCP result envelope).
    """
    session = _mock_session(call_tool_result)
    stack = _mock_stack()

    patchers = [
        patch("agent.loop.generate_with_tools", side_effect=generate_responses),
        patch("agent.loop._create_mcp_session", new=AsyncMock(return_value=(session, stack))),
    ]
    for p in patchers:
        p.start()

    try:
        return run_agent(**agent_kwargs)
    finally:
        for p in patchers:
            p.stop()


def _final(content):
    return {"content": content, "stop_reason": "stop", "tool_calls": []}


def _tool_call(tool_id, name, arguments, content=""):
    return {
        "content": content,
        "stop_reason": "tool_calls",
        "tool_calls": [{"id": tool_id, "name": name, "arguments": arguments, "parse_error": False}],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_single_turn_final_answer_no_tools():
    result = _run_with_mocks(
        generate_responses=[_final("No interaction on record.")],
        question="Is X safe with Y?",
    )

    assert result["final_answer"] == "No interaction on record."
    trace = result["trace"]
    assert trace["stopped_reason"] == "final_answer"
    assert trace["iterations"] == 1
    assert len(trace["steps"]) == 1
    assert trace["steps"][0]["tool_calls_requested"] == []


def test_multi_step_tool_call_then_final_answer():
    responses = [
        _tool_call("call_1", "resolve_drug_name", {"name": "Tahor"}),
        _final("Tahor resolves to atorvastatin; no interaction found with warfarin."),
    ]

    result = _run_with_mocks(
        generate_responses=responses,
        call_tool_result={"status": "found", "data": {"canonical": "atorvastatin"}, "message": "ok"},
        question="Is Tahor safe with warfarin?",
    )

    assert result["final_answer"] == "Tahor resolves to atorvastatin; no interaction found with warfarin."
    trace = result["trace"]
    assert trace["iterations"] == 2
    assert trace["stopped_reason"] == "final_answer"

    first_step = trace["steps"][0]
    assert len(first_step["tool_executions"]) == 1
    assert first_step["tool_executions"][0]["name"] == "resolve_drug_name"
    assert first_step["tool_executions"][0]["status"] == "found"

    # tool result must be fed back into the conversation for the next turn
    tool_messages = [m for m in trace["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "call_1"


def test_iteration_cap_forces_final_answer_with_no_tools():
    """The model keeps requesting tools forever; loop must stop and force an answer."""
    infinite_tool_calls = _tool_call("call_x", "resolve_drug_name", {"name": "warfarin"})
    forced_answer = _final("Best answer given what was gathered.")

    call_log = []

    def fake_generate(messages, tools, **kwargs):
        call_log.append(tools)
        return forced_answer if tools == [] else infinite_tool_calls

    session = _mock_session()
    stack = _mock_stack()

    with patch("agent.loop.generate_with_tools", side_effect=fake_generate):
        with patch("agent.loop._create_mcp_session", new=AsyncMock(return_value=(session, stack))):
            result = run_agent("Ambiguous question", max_iterations=3)

    trace = result["trace"]
    assert trace["stopped_reason"] == "max_iterations_reached"
    assert trace["iterations"] == 4  # 3 capped iterations + 1 forced final call
    assert result["final_answer"] == "Best answer given what was gathered."
    # the forced final call must have been made with an empty tool list
    assert call_log[-1] == []


def test_provider_error_does_not_crash_and_produces_graceful_final_answer():
    """A provider-level exception must be caught and produce a graceful answer."""
    session = _mock_session()
    stack = _mock_stack()

    with patch("agent.loop.generate_with_tools", side_effect=RuntimeError("400 tool_use_failed: bad schema")):
        with patch("agent.loop._create_mcp_session", new=AsyncMock(return_value=(session, stack))):
            result = run_agent("Is metformin an appropriate dose for this patient?")

    trace = result["trace"]
    assert trace["stopped_reason"] == "llm_error"
    assert "malformed tool request" in result["final_answer"]
    assert "LLM call failed" in trace["steps"][0]["model_content"]


def test_provider_error_on_forced_final_call_also_handled_gracefully():
    infinite_tool_calls = _tool_call("call_x", "resolve_drug_name", {"name": "warfarin"})

    def fake_generate(messages, tools, **kwargs):
        if tools == []:
            raise RuntimeError("400 tool_use_failed: bad schema")
        return infinite_tool_calls

    session = _mock_session()
    stack = _mock_stack()

    with patch("agent.loop.generate_with_tools", side_effect=fake_generate):
        with patch("agent.loop._create_mcp_session", new=AsyncMock(return_value=(session, stack))):
            result = run_agent("Ambiguous question", max_iterations=2)

    assert result["trace"]["stopped_reason"] == "llm_error"
    assert "provider error" in result["final_answer"]


def test_patient_context_rendered_into_first_user_message():
    session = _mock_session()
    stack = _mock_stack()

    with patch("agent.loop.generate_with_tools", return_value=_final("ok")) as mocked:
        with patch("agent.loop._create_mcp_session", new=AsyncMock(return_value=(session, stack))):
            run_agent("Review this prescription", patient_context={"allergies": ["penicillin"], "age": 78})

    messages = mocked.call_args[0][0]
    user_message = messages[1]["content"]
    assert "penicillin" in user_message
    assert "78" in user_message


# ── Permission gate tests ─────────────────────────────────────────────────────


def test_read_only_tool_executes_immediately_without_confirmation():
    """Read-only classified tools should execute without hitting the confirmation gate."""
    responses = [
        _tool_call("call_1", "resolve_drug_name", {"name": "warfarin"}),
        _final("Warfarin is an anticoagulant."),
    ]

    with patch("agent.loop.require_confirmation") as mock_confirm:
        result = _run_with_mocks(
            generate_responses=responses,
            call_tool_result={"status": "found", "data": {"canonical": "warfarin"}, "message": "ok"},
            question="What is warfarin?",
        )

    # require_confirmation should NOT have been called for a read-only tool
    mock_confirm.assert_not_called()
    assert result["final_answer"] == "Warfarin is an anticoagulant."


def test_action_tool_requires_confirmation_and_cancels_if_rejected():
    """
    Register a mock action tool, have the LLM call it, reject confirmation,
    and confirm the result is 'cancelled'.
    """
    from agent.permissions import ACTION_TOOLS

    ACTION_TOOLS.add("resolve_drug_name")
    try:
        responses = [
            _tool_call("call_1", "resolve_drug_name", {"name": "warfarin"}),
            _final("Final answer after cancelled tool."),
        ]

        with patch("agent.loop.require_confirmation", return_value=False):
            result = _run_with_mocks(
                generate_responses=responses,
                call_tool_result={"status": "found", "data": {"canonical": "warfarin"}, "message": "ok"},
                question="What is warfarin?",
            )

        trace = result["trace"]
        # The first step should have a cancelled execution
        first_step = trace["steps"][0]
        assert len(first_step["tool_executions"]) == 1
        assert first_step["tool_executions"][0]["name"] == "resolve_drug_name"
        assert first_step["tool_executions"][0]["status"] == "cancelled"

        # The cancelled result must be fed back into the conversation
        tool_messages = [m for m in trace["messages"] if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        cancelled_content = json.loads(tool_messages[0]["content"])
        assert cancelled_content["status"] == "cancelled"
    finally:
        ACTION_TOOLS.discard("resolve_drug_name")


# ── Context compaction test ───────────────────────────────────────────────────


def test_context_compaction_triggers_at_threshold():
    """
    Feed a long conversation that triggers compaction.
    Mock `generate` (not `generate_with_tools`) to return a summary string.
    """
    # Build many tool-call turns to exceed _COMPACTION_THRESHOLD (12)
    tool_call_response = _tool_call("call_x", "resolve_drug_name", {"name": "warfarin"})
    final_response = _final("Final answer after many turns.")

    # We need ~13+ messages to trigger compaction.
    # Each turn adds: assistant msg + tool result = 2 messages.
    # So 7 turns = 14 messages + initial system+user = 16 total > 12 threshold.
    responses = [tool_call_response] * 7 + [final_response]

    session = _mock_session(call_tool_result={"status": "found", "data": {"canonical": "warfarin"}, "message": "ok"})
    stack = _mock_stack()

    with patch("agent.loop.generate_with_tools", side_effect=responses):
        with patch("agent.loop.generate", return_value="Compacted summary of earlier turns.") as mock_generate:
            with patch("agent.loop._create_mcp_session", new=AsyncMock(return_value=(session, stack))):
                result = run_agent("Long conversation test", max_iterations=10)

    assert result["final_answer"] == "Final answer after many turns."
    # generate() should have been called at least once for compaction
    assert mock_generate.called, "Context compaction should have triggered generate()"

    # The conversation should have a summary message
    trace = result["trace"]
    summary_messages = [
        m for m in trace["messages"]
        if isinstance(m.get("content"), str) and "Summary of earlier turns" in m["content"]
    ]
    assert len(summary_messages) >= 1, "Expected at least one summary message in the conversation"



# ── Provider failure classification (Week 6 M4) ───────────────────────────────
# Every provider failure used to be reported as "malformed tool request". During
# the M4 evaluation that message was shown for an exhausted token quota, which
# sent debugging in the wrong direction for a while. The cause must be named.

def test_rate_limit_is_reported_as_a_quota_problem_not_a_model_fault():
    session = _mock_session()
    stack = _mock_stack()
    err = RuntimeError(
        "Error code: 429 - rate_limit_exceeded ... tokens per day (TPD): Limit 100000"
    )

    with patch("agent.loop.generate_with_tools", side_effect=err):
        with patch("agent.loop._create_mcp_session",
                   new=AsyncMock(return_value=(session, stack))):
            result = run_agent("Is metformin safe here?")

    trace = result["trace"]
    assert trace["stopped_reason"] == "rate_limited"
    assert "usage limit" in result["final_answer"]
    assert "quota problem, not a clinical one" in result["final_answer"]
    assert "malformed" not in result["final_answer"]
    assert "429" in trace["error"], "the raw provider error is kept for debugging"


def test_bad_credentials_are_reported_as_credentials():
    session = _mock_session()
    stack = _mock_stack()

    with patch("agent.loop.generate_with_tools",
               side_effect=RuntimeError("Error code: 401 - invalid api key")):
        with patch("agent.loop._create_mcp_session",
                   new=AsyncMock(return_value=(session, stack))):
            result = run_agent("Is metformin safe here?")

    assert result["trace"]["stopped_reason"] == "auth_error"
    assert "credentials" in result["final_answer"]


def test_a_genuine_malformed_tool_call_still_says_so():
    session = _mock_session()
    stack = _mock_stack()

    with patch("agent.loop.generate_with_tools",
               side_effect=RuntimeError("400 tool_use_failed: bad schema")):
        with patch("agent.loop._create_mcp_session",
                   new=AsyncMock(return_value=(session, stack))):
            result = run_agent("Is metformin safe here?")

    assert result["trace"]["stopped_reason"] == "llm_error"
    assert "malformed tool request" in result["final_answer"]
