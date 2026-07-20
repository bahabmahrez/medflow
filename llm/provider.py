"""
LLM provider wrapper.

Single entry point: generate(system, user, context).
The provider, model, and API key are read from environment variables — never
hardcoded.  Swapping to a different provider means changing LLM_PROVIDER and
the relevant key; no other code changes.

Supported providers (LLM_PROVIDER env var):
  openai     — OpenAI-compatible API     (set LLM_PROVIDER=openai)
               This includes local Ollama — set OPENAI_BASE_URL to
               http://localhost:11434/v1 and OPENAI_API_KEY to "ollama".
  anthropic  — Claude via Anthropic SDK  (set LLM_PROVIDER=anthropic)
  groq       — Groq API (OpenAI-compat)  (set LLM_PROVIDER=groq)
"""
import json
import os
from dotenv import load_dotenv

load_dotenv(override=True)

LLM_PROVIDER   = os.getenv("LLM_PROVIDER",  "groq")
LLM_MODEL      = os.getenv("LLM_MODEL",     "llama-3.3-70b-versatile")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# ── Context injection template ─────────────────────────────────────────────────
_CONTEXT_TEMPLATE = """\
--- RETRIEVED CONTEXT (from drug knowledge graph) ---
{context}
--- END CONTEXT ---

Question: {question}"""


def generate(
    system:    str,
    user:      str,
    context:   str | None = None,
    *,
    model:     str | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Call the configured LLM and return the response text.

    Args:
        system:     The system prompt (rules, persona, safety boundaries).
        user:       The user's question.
        context:    Optional retrieved graph data to inject before the question.
                    When provided, it is wrapped in a structured block so the
                    model clearly distinguishes graph data from the question.
        model:      Override LLM_MODEL for this call.
        max_tokens: Override LLM_MAX_TOKENS for this call.

    Returns:
        The model's response as a plain string.

    Raises:
        RuntimeError on provider misconfiguration.
        Provider-specific exceptions on API errors (let them propagate so the
        caller — the pipeline — can handle them).
    """
    # Re-read .env on every call so key changes take effect without restart
    load_dotenv(override=True)
    provider   = os.getenv("LLM_PROVIDER",  LLM_PROVIDER).lower()
    live_model = model or os.getenv("LLM_MODEL", LLM_MODEL)
    resolved_model      = live_model
    resolved_max_tokens = max_tokens or LLM_MAX_TOKENS

    # Inject context into the user message if provided
    if context:
        user_message = _CONTEXT_TEMPLATE.format(context=context, question=user)
    else:
        user_message = user

    if provider == "anthropic":
        return _call_anthropic(system, user_message, resolved_model, resolved_max_tokens)
    elif provider in ("openai", "groq"):
        return _call_openai_compat(system, user_message, resolved_model, resolved_max_tokens, provider)
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER='{provider}'. "
            "Set to 'anthropic', 'openai', or 'groq'."
        )


# ── Provider implementations ───────────────────────────────────────────────────

def _call_anthropic(system: str, user: str, model: str, max_tokens: int) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


def _call_openai_compat(system: str, user: str, model: str, max_tokens: int, provider: str = "groq") -> str:
    """Handles both OpenAI and Groq (which uses the OpenAI-compatible API)."""
    client = _openai_client(provider)
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content


def _openai_client(provider: str):
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    load_dotenv(override=True)
    if provider == "groq":
        api_key  = os.getenv("GROQ_API_KEY")
        base_url = "https://api.groq.com/openai/v1"
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable not set")
    else:
        api_key  = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")  # None for real OpenAI; set for Ollama
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable not set")

    return OpenAI(api_key=api_key, base_url=base_url)


# ── Tool-calling (agentic) entry point ─────────────────────────────────────────
#
# Unlike generate(), this takes and returns provider-agnostic, OpenAI-wire-format
# structures directly — messages is a list of {"role", "content", ...} dicts
# (roles: system/user/assistant/tool), tools is a list of
# {"name", "description", "parameters"} dicts. The Anthropic branch translates
# both directions internally; callers (the agent loop) never see SDK objects.

def generate_with_tools(
    messages: list[dict],
    tools:    list[dict],
    *,
    model:      str | None = None,
    max_tokens: int | None = None,
) -> dict:
    """
    Call the configured LLM with tool definitions and return a normalized turn.

    Args:
        messages:   OpenAI-wire conversation history. messages[0] must be
                    {"role": "system", "content": ...}.
        tools:      List of {"name", "description", "parameters"} tool schemas.
        model:      Override LLM_MODEL for this call.
        max_tokens: Override LLM_MAX_TOKENS for this call.

    Returns:
        {
            "content":     str,   — model's text for this turn ("" if pure tool-calls)
            "stop_reason": "tool_calls" | "stop" | "length" | "error",
            "tool_calls":  [{"id", "name", "arguments": dict, "parse_error": bool}],
        }
    """
    load_dotenv(override=True)
    provider   = os.getenv("LLM_PROVIDER",  LLM_PROVIDER).lower()
    live_model = model or os.getenv("LLM_MODEL", LLM_MODEL)
    resolved_max_tokens = max_tokens or LLM_MAX_TOKENS

    if provider == "anthropic":
        return _call_anthropic_with_tools(messages, tools, live_model, resolved_max_tokens)
    elif provider in ("openai", "groq"):
        return _call_openai_compat_with_tools(messages, tools, live_model, resolved_max_tokens, provider)
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER='{provider}'. "
            "Set to 'anthropic', 'openai', or 'groq'."
        )


def _call_openai_compat_with_tools(
    messages: list[dict], tools: list[dict], model: str, max_tokens: int, provider: str = "groq",
) -> dict:
    client = _openai_client(provider)
    kwargs = {}
    if tools:
        kwargs["tools"] = [
            {"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["parameters"],
            }}
            for t in tools
        ]
        kwargs["tool_choice"] = "auto"
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        temperature=0.0,
        **kwargs,
    )
    message = response.choices[0].message
    finish_reason = response.choices[0].finish_reason

    tool_calls = []
    for tc in (message.tool_calls or []):
        try:
            arguments = json.loads(tc.function.arguments)
            parse_error = False
        except (json.JSONDecodeError, TypeError):
            arguments = {"_raw": tc.function.arguments}
            parse_error = True
        tool_calls.append({
            "id": tc.id, "name": tc.function.name,
            "arguments": arguments, "parse_error": parse_error,
        })

    stop_reason = "tool_calls" if tool_calls else ("length" if finish_reason == "length" else "stop")
    return {"content": message.content or "", "stop_reason": stop_reason, "tool_calls": tool_calls}


# ── Anthropic tool-calling translation shim ────────────────────────────────────
# Only unit-tested with a mocked anthropic client in this environment — no
# ANTHROPIC_API_KEY is configured here, so this path never runs live.

def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
        for t in tools
    ]


def _to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Split off the leading system message and translate OpenAI-wire history
    (assistant tool_calls / role:"tool" results) into Anthropic content blocks."""
    system = ""
    anthropic_messages: list[dict] = []

    for msg in messages:
        role = msg["role"]
        if role == "system":
            system = msg["content"]
        elif role in ("user", "assistant") and not msg.get("tool_calls"):
            anthropic_messages.append({"role": role, "content": msg["content"] or ""})
        elif role == "assistant" and msg.get("tool_calls"):
            content = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                content.append({
                    "type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                    "input": json.loads(tc["function"]["arguments"]),
                })
            anthropic_messages.append({"role": "assistant", "content": content})
        elif role == "tool":
            # Anthropic requires tool results as a user-role message.
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg["content"],
                }],
            })

    return system, anthropic_messages


def _call_anthropic_with_tools(messages: list[dict], tools: list[dict], model: str, max_tokens: int) -> dict:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    system, anthropic_messages = _to_anthropic_messages(messages)
    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {"tools": _to_anthropic_tools(tools)} if tools else {}
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=anthropic_messages,
        **kwargs,
    )

    content_text = ""
    tool_calls = []
    for block in response.content:
        if block.type == "text":
            content_text += block.text
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id, "name": block.name,
                "arguments": block.input, "parse_error": False,
            })

    stop_reason = "tool_calls" if tool_calls else (
        "length" if response.stop_reason == "max_tokens" else "stop"
    )
    return {"content": content_text, "stop_reason": stop_reason, "tool_calls": tool_calls}
