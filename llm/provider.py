"""
LLM provider wrapper.

Single entry point: generate(system, user, context).
The provider, model, and API key are read from environment variables — never
hardcoded.  Swapping to a different provider means changing LLM_PROVIDER and
the relevant key; no other code changes.

Supported providers (LLM_PROVIDER env var):
  anthropic  — Claude via Anthropic SDK  (default)
  openai     — GPT via OpenAI SDK        (set LLM_PROVIDER=openai)
  groq       — Groq API (OpenAI-compat)  (set LLM_PROVIDER=groq)
"""
import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER  = os.getenv("LLM_PROVIDER",  "groq")
LLM_MODEL     = os.getenv("LLM_MODEL",     "groq/compound-mini")
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
    resolved_model      = model or LLM_MODEL
    resolved_max_tokens = max_tokens or LLM_MAX_TOKENS

    # Inject context into the user message if provided
    if context:
        user_message = _CONTEXT_TEMPLATE.format(context=context, question=user)
    else:
        user_message = user

    provider = LLM_PROVIDER.lower()

    if provider == "anthropic":
        return _call_anthropic(system, user_message, resolved_model, resolved_max_tokens)
    elif provider in ("openai", "groq"):
        return _call_openai_compat(system, user_message, resolved_model, resolved_max_tokens)
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER='{LLM_PROVIDER}'. "
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


def _call_openai_compat(system: str, user: str, model: str, max_tokens: int) -> str:
    """Handles both OpenAI and Groq (which uses the OpenAI-compatible API)."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    if LLM_PROVIDER.lower() == "groq":
        api_key  = os.getenv("GROQ_API_KEY")
        base_url = "https://api.groq.com/openai/v1"
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable not set")
    else:
        api_key  = os.getenv("OPENAI_API_KEY")
        base_url = None
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable not set")

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content
