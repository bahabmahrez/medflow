"""
The agent loop — sends the question and the full tool list to the model,
executes whatever tools it requests, feeds results back, and repeats until
the model gives a final answer or a hard iteration cap is hit.
"""
import json
import time

from llm import generate_with_tools
from .prompts import agent_system_prompt
from .tools import TOOLS, call_tool
from .trace import new_trace, new_step, log_execution


def _render_patient_context(patient_context: dict) -> str:
    lines = ["Patient context (for reference — you must still decide which checks to run):"]
    for key in ("conditions", "allergies", "active_meds", "age", "weight", "labs"):
        if patient_context.get(key):
            lines.append(f"  {key}: {patient_context[key]}")
    return "\n".join(lines)


def _assistant_message(response: dict) -> dict:
    """Build the OpenAI-wire assistant turn to append to conversation history."""
    msg = {"role": "assistant", "content": response["content"] or None}
    if response["tool_calls"]:
        msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
            }
            for tc in response["tool_calls"]
        ]
    return msg


def run_agent(
    question: str,
    *,
    patient_context: dict | None = None,
    max_iterations: int = 8,
    model: str | None = None,
) -> dict:
    """
    Run the tool-calling agent loop for one pharmacist question.

    Returns:
        {"final_answer": str, "trace": dict}  — see agent.trace for trace schema.
    """
    user_content = question
    if patient_context:
        user_content = f"{question}\n\n{_render_patient_context(patient_context)}"

    messages = [
        {"role": "system", "content": agent_system_prompt()},
        {"role": "user", "content": user_content},
    ]

    trace = new_trace(question, patient_context)
    final_answer = None
    stopped_reason = None
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        response = generate_with_tools(messages, TOOLS, model=model)
        messages.append(_assistant_message(response))

        step = new_step(iteration, response["content"], response["tool_calls"])
        trace["steps"].append(step)

        if not response["tool_calls"]:
            final_answer = response["content"]
            stopped_reason = "final_answer"
            break

        for tc in response["tool_calls"]:
            start = time.perf_counter()
            result = call_tool(tc["name"], tc["arguments"])
            duration_ms = (time.perf_counter() - start) * 1000
            log_execution(step, tc["id"], tc["name"], tc["arguments"], result, duration_ms)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result),
            })

    if final_answer is None:
        # Iteration cap hit — force one last call with no tools so the model
        # synthesizes an answer from whatever has already been gathered,
        # instead of silently truncating.
        response = generate_with_tools(messages, tools=[], model=model)
        messages.append(_assistant_message(response))
        iteration += 1
        step = new_step(iteration, response["content"], [])
        trace["steps"].append(step)
        final_answer = response["content"]
        stopped_reason = "max_iterations_reached"

    trace["final_answer"] = final_answer
    trace["iterations"] = iteration
    trace["stopped_reason"] = stopped_reason
    trace["messages"] = messages

    return {"final_answer": final_answer, "trace": trace}
