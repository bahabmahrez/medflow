"""
The agent loop — sends the question and the full tool list to the model,
executes whatever tools it requests via MCP, feeds results back, and
repeats until the model gives a final answer or a hard iteration cap is hit.

Architecture change (Week 5+): the loop no longer imports tools directly
from agent.tools.py. Instead, it connects to medflow_mcp/server.py over
stdio as an MCP client, discovers tools dynamically, and executes every
tool call through the MCP round-trip. A permissions gate classifies tools
as read-only (execute immediately) or action (require human confirmation).
A context compactor summarises conversation history when it grows too long.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from llm import generate, generate_with_tools
from .permissions import classify_tool, require_confirmation
from .prompts import agent_system_prompt
from .trace import log_execution, new_step, new_trace

# ── MCP server path ───────────────────────────────────────────────────────────
# Resolved relative to this file so the path stays correct regardless of
# the working directory from which the agent is invoked.
_MCP_SERVER_PATH = str(
    Path(__file__).resolve().parent.parent / "medflow_mcp" / "server.py"
)

# The short LLM tool name -> MCP tool name map is built dynamically during
# discovery (see _convert_mcp_tools_to_llm_schema) from whatever names the
# server actually advertises — there is no hardcoded table, so tools added
# to the server work automatically.

# ── Context-compaction thresholds ─────────────────────────────────────────────
_COMPACTION_THRESHOLD = 12   # total messages before compaction triggers
_RECENT_TAIL_COUNT = 5       # keep the last N turns verbatim


# ── Helpers ───────────────────────────────────────────────────────────────────

def _render_patient_context(patient_context: dict) -> str:
    lines = ["Patient context (for reference — you must still decide which checks to run):"]
    for key in ("conditions", "allergies", "active_meds", "age", "weight", "labs"):
        if patient_context.get(key):
            lines.append(f"  {key}: {patient_context[key]}")
    return "\n".join(lines)


def _safe_generate_with_tools(
    messages: list[dict], tools: list[dict], model: str | None,
) -> tuple[dict | None, str | None]:
    """
    Wrap generate_with_tools so a provider-level failure never crashes the loop.
    """
    try:
        return generate_with_tools(messages, tools, model=model), None
    except Exception as exc:
        return None, str(exc)


_RATE_LIMIT_MARKERS = (
    "rate limit", "rate_limit", "429", "too many requests",
    "tokens per day", "tokens per minute", "quota",
)
_AUTH_MARKERS = ("401", "403", "invalid api key", "unauthorized", "authentication")


def _classify_llm_failure(error: str) -> tuple[str, str]:
    """
    Turn a provider exception into ``(stopped_reason, message)``.

    Every provider failure used to be reported as "the model produced a
    malformed tool request". That is only one of the ways this can fail, and
    saying it for a quota error or a bad key sends whoever is debugging in
    entirely the wrong direction - the M4 evaluation lost time to exactly that.
    """
    lowered = (error or "").lower()

    if any(marker in lowered for marker in _RATE_LIMIT_MARKERS):
        return "rate_limited", (
            "I couldn't complete this analysis because the language model's usage "
            "limit has been reached. This is a quota problem, not a clinical one - "
            "the knowledge base is unaffected. Please retry later or check the "
            "provider plan."
        )
    if any(marker in lowered for marker in _AUTH_MARKERS):
        return "auth_error", (
            "I couldn't reach the language model: the API credentials were "
            "rejected. Please check the provider key configuration."
        )
    return "llm_error", (
        "I wasn't able to complete this analysis - the model produced a malformed "
        "tool request. Please rephrase the question or provide the missing values "
        "explicitly."
    )


def _assistant_message(response: dict) -> dict:
    """Build the OpenAI-wire assistant turn to append to conversation history."""
    msg: dict[str, Any] = {"role": "assistant", "content": response["content"] or None}
    if response["tool_calls"]:
        msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"]),
                },
            }
            for tc in response["tool_calls"]
        ]
    return msg


def _convert_mcp_tools_to_llm_schema(
    mcp_tools: list[Any],
) -> tuple[list[dict], dict[str, str]]:
    """
    Convert MCP tool descriptions (from ``session.list_tools()``) into the
    OpenAI-wire tool schema that ``generate_with_tools`` expects, and build
    the short-name -> MCP-name map used to call each tool back.

    MCP tools have fields: ``name``, ``description``, ``inputSchema``.
    The LLM schema needs: ``name``, ``description``, ``parameters``.
    We strip the ``_tool`` suffix so the LLM sees the short canonical name
    (e.g. ``resolve_drug_name`` instead of ``resolve_drug_name_tool``) and
    record ``short_name -> tool.name`` so invocation always uses whatever
    names the server advertised — no hardcoded map, so tools added to the
    server work automatically.

    Returns ``(llm_tools, name_map)``.
    """
    llm_tools: list[dict] = []
    name_map: dict[str, str] = {}
    for tool in mcp_tools:
        short_name = tool.name
        if short_name.endswith("_tool"):
            short_name = short_name[: -len("_tool")]
        name_map[short_name] = tool.name
        llm_tools.append({
            "name": short_name,
            "description": tool.description or "",
            "parameters": dict(tool.inputSchema) if tool.inputSchema else {
                "type": "object",
                "properties": {},
            },
        })
    return llm_tools, name_map


def _convert_mcp_result(result: Any) -> dict:
    """
    Convert an MCP ``CallToolResult`` into the standard ``{status, data,
    message}`` tool-result dict the conversation expects.

    MCP results have:
      - ``result.content`` — list of ``TextContent`` / ``EmbeddedResource``
      - ``result.isError`` — bool

    The MedFlow MCP tools always return a single ``TextContent`` whose
    ``.text`` is a JSON string (via ``_json(...)`` in server.py).
    """
    if result.isError:
        error_text = ""
        if result.content:
            error_text = getattr(result.content[0], "text", "") or str(result.content[0])
        return {"status": "error", "data": {}, "message": error_text or "MCP tool call failed"}

    if not result.content:
        return {"status": "not_found", "data": {}, "message": "No data returned"}

    try:
        parsed = json.loads(result.content[0].text)
    except (json.JSONDecodeError, IndexError, AttributeError):
        return {
            "status": "error",
            "data": {},
            "message": f"Could not parse MCP result: {result.content[0].text[:200] if result.content else 'empty'}",
        }

    # The MedFlow MCP tools return {"status": "...", "data": ..., "message": "..."}
    # or sometimes just raw data. Normalise both cases.
    if isinstance(parsed, dict) and "status" in parsed:
        return parsed  # already in canonical form
    return {"status": "found", "data": parsed, "message": "ok"}


def _compact_conversation(messages: list[dict], model: str | None) -> list[dict]:
    """
    If *messages* exceed ``_COMPACTION_THRESHOLD``, summarise everything
    older than the recent tail into a compact summary block, then replace
    those old messages with the summary.

    The first message (system prompt) is always preserved intact.
    """
    if len(messages) <= _COMPACTION_THRESHOLD:
        return messages

    # Preserve system message at index 0; compact everything before the tail.
    system = [messages[0]] if messages and messages[0]["role"] == "system" else []

    # Choose the tail boundary so the retained tail never *begins* on a
    # role:"tool" message. If it did, the assistant tool_calls turn that
    # produced it would be summarised away, leaving a tool message with no
    # preceding tool_calls — which the provider rejects (HTTP 400). Walk the
    # boundary back to include the owning assistant turn.
    tail_start = max(len(system), len(messages) - _RECENT_TAIL_COUNT)
    while tail_start > len(system) and messages[tail_start].get("role") == "tool":
        tail_start -= 1

    tail = messages[tail_start:]
    old_part = messages[len(system):tail_start]

    if not old_part:
        return messages

    # Build a summarization prompt from the old messages.
    summary_lines = []
    for m in old_part:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if isinstance(content, str) and content:
            summary_lines.append(f"[{role}]: {content[:300]}")
        elif isinstance(content, list):
            # Anthropic-style content blocks
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    summary_lines.append(f"[{role}]: {block['text'][:300]}")

    if not summary_lines:
        return messages

    summary_text = "\n".join(summary_lines)
    summary_prompt = (
        "Summarise the following conversation so far in 3-4 sentences. "
        "Include: which patient/drugs were discussed, what findings were "
        "already flagged, and any pending questions. Keep only facts.\n\n"
        + summary_text
    )

    try:
        summary = generate(
            system="You are a precise summariser. Condense the conversation below into 3-4 factual sentences.",
            user=summary_prompt,
            model=model,
        )
    except Exception:
        # If summarisation fails, return the original messages unchanged.
        return messages

    compact: list[dict] = list(system)
    compact.append({
        "role": "system",
        "content": f"[Summary of earlier turns]: {summary.strip()}",
    })
    compact.extend(tail)

    return compact


# ── MCP session lifecycle (extracted for testability) ─────────────────────────

async def _create_mcp_session():
    """
    Connect to the MedFlow MCP server over stdio and return an initialised
    ``ClientSession`` together with the ``AsyncExitStack`` that owns its
    lifecycle.

    Both the stdio client and the client session are async context managers
    whose ``__aexit__`` performs the real teardown — terminating the server
    subprocess and unwinding anyio's cancel scopes. Entering them via
    ``__aenter__`` without a matching ``__aexit__`` leaks the subprocess and
    can raise "cancel scope" errors, so we route both through a single
    ``AsyncExitStack``. The caller MUST ``await stack.aclose()`` when done;
    because the stack is entered and closed in the same task, teardown is
    correct.

    Extracted so tests can patch ``agent.loop._create_mcp_session`` with a
    mock returning a fake session + a no-op stack.
    """
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.session import ClientSession

    params = StdioServerParameters(
        command=sys.executable,
        args=[_MCP_SERVER_PATH],
    )
    stack = AsyncExitStack()
    try:
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
    except Exception:
        await stack.aclose()
        raise
    return session, stack


# ── Public API ────────────────────────────────────────────────────────────────

def run_agent(
    question: str,
    *,
    patient_context: dict | None = None,
    max_iterations: int = 8,
    model: str | None = None,
) -> dict:
    """
    Run the tool-calling agent loop for one pharmacist question.

    This is the synchronous public API. It delegates to the async
    implementation via ``asyncio.run()``.

    Returns:
        {"final_answer": str, "trace": dict}  — see agent.trace for trace schema.
    """
    return asyncio.run(
        _run_agent_async(question, patient_context, max_iterations, model)
    )


async def _run_agent_async(
    question: str,
    patient_context: dict | None,
    max_iterations: int,
    model: str | None,
) -> dict:
    """
    Async core of the agent loop.

    1. Connect to MCP server, discover tools dynamically.
    2. Run the multi-turn LLM loop (max *max_iterations* turns).
    3. Each tool call passes through the permissions gate first.
    4. Long conversations are compacted automatically.
    5. Everything is logged in the trace.
    """
    # ── MCP connection ─────────────────────────────────────────────────────
    try:
        session, mcp_stack = await _create_mcp_session()
    except Exception as exc:
        return {
            "final_answer": (
                f"I couldn't connect to the knowledge graph backend. "
                f"Please make sure the databases are running (docker compose up -d). "
                f"Error: {exc}"
            ),
            "trace": {
                "question": question,
                "patient_context": patient_context,
                "final_answer": None,
                "iterations": 0,
                "stopped_reason": "mcp_connection_error",
                "steps": [],
                "messages": [],
                "error": str(exc),
            },
        }

    try:
        return await _run_agent_loop(
            session, question, patient_context, max_iterations, model,
        )
    finally:
        # Unwind the stdio client + client session (reverse order) so the
        # MCP server subprocess is terminated cleanly.
        try:
            await mcp_stack.aclose()
        except Exception:
            pass


async def _run_agent_loop(
    session: Any,
    question: str,
    patient_context: dict | None,
    max_iterations: int,
    model: str | None,
) -> dict:
    """
    Core loop: discover tools, then iterate with the LLM.
    Extracted so both the real path and tests can call it with a mock session.
    """
    # ── Dynamic tool discovery ─────────────────────────────────────────────
    try:
        tools_result = await session.list_tools()
        mcp_tools = list(tools_result.tools)
        tools_schema, mcp_name_map = _convert_mcp_tools_to_llm_schema(mcp_tools)
    except Exception as exc:
        return {
            "final_answer": f"Failed to discover tools from knowledge graph backend: {exc}",
            "trace": {
                "question": question,
                "patient_context": patient_context,
                "final_answer": None,
                "iterations": 0,
                "stopped_reason": "tool_discovery_error",
                "steps": [],
                "messages": [],
                "error": str(exc),
            },
        }

    # ── Build initial messages ─────────────────────────────────────────────
    user_content = question
    if patient_context:
        user_content = f"{question}\n\n{_render_patient_context(patient_context)}"

    messages: list[dict] = [
        {"role": "system", "content": agent_system_prompt()},
        {"role": "user", "content": user_content},
    ]

    trace = new_trace(question, patient_context)
    final_answer: str | None = None
    stopped_reason: str | None = None
    iteration = 0

    # ── Main loop ──────────────────────────────────────────────────────────
    while iteration < max_iterations:
        iteration += 1

        # --- LLM call ---
        response, error = _safe_generate_with_tools(messages, tools_schema, model)
        if error:
            trace["steps"].append(
                new_step(iteration, f"[LLM call failed: {error}]", [])
            )
            stopped_reason, final_answer = _classify_llm_failure(error)
            trace["error"] = error
            break

        messages.append(_assistant_message(response))

        step = new_step(iteration, response["content"], response["tool_calls"])
        trace["steps"].append(step)

        if not response["tool_calls"]:
            final_answer = response["content"]
            stopped_reason = "final_answer"
            break

        # --- Execute each tool call ---
        for tc in response["tool_calls"]:
            short_name = tc["name"]
            arguments = tc["arguments"]

            # Permission gate
            perm = classify_tool(short_name)
            if perm == "action":
                if not require_confirmation(short_name, arguments):
                    result = {
                        "status": "cancelled",
                        "data": {},
                        "message": "Cancelled by user — action tool requires confirmation.",
                    }
                    log_execution(step, tc["id"], short_name, arguments, result, 0.0)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })
                    continue

            # Execute via MCP
            mcp_name = mcp_name_map.get(short_name, short_name)
            start = time.perf_counter()
            try:
                mcp_result = await session.call_tool(mcp_name, arguments)
                result = _convert_mcp_result(mcp_result)
            except Exception as exc:
                result = {
                    "status": "error",
                    "data": {},
                    "message": f"MCP call failed: {exc}",
                }
            duration_ms = (time.perf_counter() - start) * 1000

            log_execution(step, tc["id"], short_name, arguments, result, duration_ms)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result),
            })

        # --- Context compaction ---
        messages = _compact_conversation(messages, model)

    # ── Handle iteration cap ───────────────────────────────────────────────
    if final_answer is None:
        response, error = _safe_generate_with_tools(messages, [], model)
        iteration += 1
        if error:
            trace["steps"].append(
                new_step(iteration, f"[LLM call failed: {error}]", [])
            )
            stopped_reason, _ = _classify_llm_failure(error)
            trace["error"] = error
            final_answer = (
                "I wasn't able to synthesise a final answer due to a model/provider error."
            )
        else:
            messages.append(_assistant_message(response))
            trace["steps"].append(new_step(iteration, response["content"], []))
            final_answer = response["content"]
            stopped_reason = "max_iterations_reached"

    # ── Finalise trace ─────────────────────────────────────────────────────
    trace["final_answer"] = final_answer
    trace["iterations"] = iteration
    trace["stopped_reason"] = stopped_reason
    trace["messages"] = messages

    return {"final_answer": final_answer, "trace": trace}
