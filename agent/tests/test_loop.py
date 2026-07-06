"""
Tests for agent.loop.run_agent — loop mechanics with generate_with_tools
mocked. No live LLM/Neo4j calls here.
"""
from unittest.mock import patch

from agent.loop import run_agent


def _final(content):
    return {"content": content, "stop_reason": "stop", "tool_calls": []}


def _tool_call(tool_id, name, arguments, content=""):
    return {
        "content": content,
        "stop_reason": "tool_calls",
        "tool_calls": [{"id": tool_id, "name": name, "arguments": arguments, "parse_error": False}],
    }


def test_single_turn_final_answer_no_tools():
    with patch("agent.loop.generate_with_tools", return_value=_final("No interaction on record.")):
        result = run_agent("Is X safe with Y?")

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

    with patch("agent.loop.generate_with_tools", side_effect=responses):
        with patch("agent.loop.call_tool", return_value={"status": "found", "data": {"canonical": "atorvastatin"}, "message": "ok"}) as mocked_call_tool:
            result = run_agent("Is Tahor safe with warfarin?")

    assert result["final_answer"] == "Tahor resolves to atorvastatin; no interaction found with warfarin."
    trace = result["trace"]
    assert trace["iterations"] == 2
    assert trace["stopped_reason"] == "final_answer"

    first_step = trace["steps"][0]
    assert len(first_step["tool_executions"]) == 1
    assert first_step["tool_executions"][0]["name"] == "resolve_drug_name"
    assert first_step["tool_executions"][0]["status"] == "found"

    mocked_call_tool.assert_called_once_with("resolve_drug_name", {"name": "Tahor"})

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

    with patch("agent.loop.generate_with_tools", side_effect=fake_generate):
        with patch("agent.loop.call_tool", return_value={"status": "found", "data": {}, "message": "ok"}):
            result = run_agent("Ambiguous question", max_iterations=3)

    trace = result["trace"]
    assert trace["stopped_reason"] == "max_iterations_reached"
    assert trace["iterations"] == 4  # 3 capped iterations + 1 forced final call
    assert result["final_answer"] == "Best answer given what was gathered."
    # the forced final call must have been made with an empty tool list
    assert call_log[-1] == []


def test_patient_context_rendered_into_first_user_message():
    with patch("agent.loop.generate_with_tools", return_value=_final("ok")) as mocked:
        run_agent("Review this prescription", patient_context={"allergies": ["penicillin"], "age": 78})

    messages = mocked.call_args[0][0]
    user_message = messages[1]["content"]
    assert "penicillin" in user_message
    assert "78" in user_message
