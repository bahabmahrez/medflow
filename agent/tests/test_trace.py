"""Tests for agent.trace — trace construction and pretty-printing."""
from agent.trace import new_trace, new_step, log_execution, all_tool_names, pretty_print


def _build_sample_trace():
    trace = new_trace("Is warfarin safe with aspirin?", {"allergies": ["penicillin"]})
    step = new_step(1, "Checking interactions...", [{"id": "call_1", "name": "detect_pairwise_interactions", "arguments": {"drug_list": ["warfarin", "aspirin"]}}])
    log_execution(
        step, "call_1", "detect_pairwise_interactions", {"drug_list": ["warfarin", "aspirin"]},
        {"status": "found", "data": {"interactions": [{"severity": "major"}]}, "message": "1 interaction(s) found"},
        duration_ms=12.345,
    )
    trace["steps"].append(step)
    trace["final_answer"] = "This is a MAJOR interaction."
    trace["iterations"] = 1
    trace["stopped_reason"] = "final_answer"
    return trace


def test_new_trace_shape():
    trace = new_trace("question", None)
    assert trace["question"] == "question"
    assert trace["patient_context"] is None
    assert trace["steps"] == []
    assert trace["final_answer"] is None


def test_log_execution_records_status_and_duration():
    step = new_step(1, "", [])
    log_execution(step, "call_1", "resolve_drug_name", {"name": "Tahor"},
                   {"status": "not_found", "data": {}, "message": "not found"}, duration_ms=5.0)
    execution = step["tool_executions"][0]
    assert execution["status"] == "not_found"
    assert execution["duration_ms"] == 5.0
    assert execution["name"] == "resolve_drug_name"


def test_all_tool_names_collects_across_steps():
    trace = _build_sample_trace()
    assert all_tool_names(trace) == ["detect_pairwise_interactions"]


def test_pretty_print_includes_question_tool_call_and_final_answer():
    trace = _build_sample_trace()
    output = pretty_print(trace)
    assert "Is warfarin safe with aspirin?" in output
    assert "detect_pairwise_interactions" in output
    assert "MAJOR interaction" in output
    assert "final_answer" in output.lower() or "Final answer" in output
