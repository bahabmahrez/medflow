"""
Tests for the LLM provider wrapper.

Tests marked with @pytest.mark.live require ANTHROPIC_API_KEY and hit the
real API.  All others run without a key.
"""
import os
import pytest
from unittest.mock import patch, MagicMock

from llm.provider import generate, _CONTEXT_TEMPLATE
from llm import load_system_prompt


# ── Config and prompt loading ──────────────────────────────────────────────────

def test_system_prompt_loads():
    prompt = load_system_prompt()
    assert len(prompt) > 100
    assert "CONTEXT IS THE ONLY SOURCE OF TRUTH" in prompt
    assert "FABRICATION" in prompt
    assert "LANGUAGE" in prompt


def test_system_prompt_has_severity_rules():
    prompt = load_system_prompt()
    assert "contre_indique" in prompt
    assert "CONTRAINDICATED" in prompt
    assert "major" in prompt


def test_unknown_provider_raises():
    import llm.provider as mod
    original = mod.LLM_PROVIDER
    try:
        mod.LLM_PROVIDER = "fictional_provider"
        with pytest.raises(RuntimeError, match="Unknown LLM_PROVIDER"):
            mod.generate("system", "user")
    finally:
        mod.LLM_PROVIDER = original


def test_missing_api_key_raises():
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            generate("system", "user")
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_context_injected_into_user_message():
    """Context must appear before the question in the formatted message."""
    ctx = "CYP3A4 competition detected between simvastatin and clarithromycin."
    q   = "Is this combination safe?"
    formatted = _CONTEXT_TEMPLATE.format(context=ctx, question=q)
    assert ctx in formatted
    assert q in formatted
    assert formatted.index(ctx) < formatted.index(q)


def test_no_context_passes_question_directly():
    """Without context the user message is passed through unchanged."""
    captured = {}
    def fake_anthropic(system, user, model, max_tokens):
        captured["user"] = user
        return "mocked"

    with patch("llm.provider._call_anthropic", side_effect=fake_anthropic):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            generate("sys", "plain question")
    assert captured["user"] == "plain question"


def test_context_wraps_message():
    """With context the user message must contain the context block."""
    captured = {}
    def fake_anthropic(system, user, model, max_tokens):
        captured["user"] = user
        return "mocked"

    with patch("llm.provider._call_anthropic", side_effect=fake_anthropic):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            generate("sys", "Is this safe?", context="DDI data here")
    assert "DDI data here" in captured["user"]
    assert "Is this safe?" in captured["user"]


# ── Live API tests (require ANTHROPIC_API_KEY) ─────────────────────────────────

@pytest.mark.live
def test_live_generate_returns_string():
    """Real call — verifies the key works and the model responds."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    system = load_system_prompt()
    result = generate(system, "Say only the word: PONG")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.live
def test_live_respects_no_fabrication_rule():
    """
    Model must refuse to invent an interaction when context says 'none found'.
    The graph is the source of truth.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    system  = load_system_prompt()
    context = (
        "Pairwise interaction check: warfarin + amoxicillin\n"
        "interactions_found: 0\n"
        "No INTERACTS_WITH edge exists between these molecules."
    )
    result = generate(
        system,
        "Does warfarin interact with amoxicillin?",
        context=context,
    )
    lower = result.lower()
    # Must say no interaction on record — must NOT invent one
    assert any(phrase in lower for phrase in (
        "no interaction", "none on record", "not recorded",
        "aucune interaction", "no se registra"
    ))
    assert "major" not in lower
    assert "bleeding" not in lower


@pytest.mark.live
def test_live_states_severity_first():
    """Response for a contre_indique interaction must lead with CONTRAINDICATED."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    system  = load_system_prompt()
    context = (
        "Pairwise interaction: warfarin + amiodarone\n"
        "severity: contre_indique\n"
        "effect: amiodarone markedly potentiates warfarin anticoagulation "
        "by inhibiting CYP2C9 and CYP3A4, raising INR to dangerous levels.\n"
        "source: ANSM"
    )
    result = generate(
        system,
        "Can I give amiodarone to a patient already on warfarin?",
        context=context,
    )
    # Severity must appear in the first 120 characters
    first_120 = result[:120].upper()
    assert "CONTRAINDICATED" in first_120 or "CONTRE-INDIQUÉ" in first_120
