"""
Trace structure for the agent loop — every tool call, argument, result, and
model turn logged, so the agent's reasoning can be inspected and asserted on.
"""
import json


def new_trace(question: str, patient_context: dict | None) -> dict:
    return {
        "question": question,
        "patient_context": patient_context,
        "final_answer": None,
        "iterations": 0,
        "stopped_reason": None,
        "steps": [],
        "messages": [],
    }


def new_step(step_number: int, model_content: str, tool_calls_requested: list[dict]) -> dict:
    return {
        "step": step_number,
        "model_content": model_content,
        "tool_calls_requested": tool_calls_requested,
        "tool_executions": [],
    }


def log_execution(step: dict, tool_call_id: str, name: str, arguments: dict, result: dict, duration_ms: float) -> None:
    step["tool_executions"].append({
        "tool_call_id": tool_call_id,
        "name": name,
        "arguments": arguments,
        "result": result,
        "status": result.get("status", "error"),
        "duration_ms": round(duration_ms, 2),
    })


def all_tool_names(trace: dict) -> list[str]:
    """Every tool name actually invoked across the whole trace, in call order."""
    return [
        execution["name"]
        for step in trace["steps"]
        for execution in step["tool_executions"]
    ]


def pretty_print(trace: dict) -> str:
    lines = [f"Question: {trace['question']}"]
    if trace.get("patient_context"):
        lines.append(f"Patient context: {trace['patient_context']}")
    lines.append("")

    for step in trace["steps"]:
        text = step["model_content"].strip() or "(no text, tool-call-only turn)"
        lines.append(f"Step {step['step']}: {text}")
        for execution in step["tool_executions"]:
            args = json.dumps(execution["arguments"], ensure_ascii=False)
            lines.append(
                f"  -> called {execution['name']}({args}) => "
                f"{execution['status']}: {execution['result'].get('message', '')}"
            )
        lines.append("")

    lines.append(f"Stopped: {trace['stopped_reason']} after {trace['iterations']} iteration(s)")
    lines.append(f"Final answer: {trace['final_answer']}")
    return "\n".join(lines)
