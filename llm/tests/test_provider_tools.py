"""
Tests for llm.provider.generate_with_tools — the tool-calling entry point
added for the Week 4 agent. Mocked only; no live API calls here (see
evaluation/agent_eval for live tests).
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from llm.provider import (
    generate_with_tools,
    _to_anthropic_tools,
    _to_anthropic_messages,
)

_TOOLS = [
    {
        "name": "resolve_drug_name",
        "description": "Resolve a drug name to its canonical INN.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]

_MESSAGES = [
    {"role": "system", "content": "You are a pharmacy agent."},
    {"role": "user", "content": "Is Tahor safe with warfarin?"},
]


def _fake_openai_response(tool_calls=None, content="", finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _fake_tool_call(id_, name, arguments_json):
    function = SimpleNamespace(name=name, arguments=arguments_json)
    return SimpleNamespace(id=id_, function=function)


# ── OpenAI/Groq branch ──────────────────────────────────────────────────────────

def test_openai_compat_normalizes_tool_call():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_openai_response(
        tool_calls=[_fake_tool_call("call_1", "resolve_drug_name", '{"name": "Tahor"}')],
    )

    with patch("llm.provider._openai_client", return_value=fake_client):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}):
            with patch("llm.provider.load_dotenv"):
                result = generate_with_tools(_MESSAGES, _TOOLS)

    assert result["stop_reason"] == "tool_calls"
    assert result["tool_calls"] == [
        {"id": "call_1", "name": "resolve_drug_name", "arguments": {"name": "Tahor"}, "parse_error": False},
    ]

    # tools must be passed through in native OpenAI function-calling shape
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["tools"][0]["function"]["name"] == "resolve_drug_name"
    assert kwargs["tool_choice"] == "auto"


def test_openai_compat_final_answer_has_no_tool_calls():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_openai_response(
        tool_calls=None, content="Warfarin and Tahor show no recorded interaction.",
    )

    with patch("llm.provider._openai_client", return_value=fake_client):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}):
            with patch("llm.provider.load_dotenv"):
                result = generate_with_tools(_MESSAGES, _TOOLS)

    assert result["stop_reason"] == "stop"
    assert result["tool_calls"] == []
    assert "no recorded interaction" in result["content"]


def test_openai_compat_malformed_arguments_flagged_as_parse_error():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_openai_response(
        tool_calls=[_fake_tool_call("call_1", "resolve_drug_name", "{not valid json")],
    )

    with patch("llm.provider._openai_client", return_value=fake_client):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}):
            with patch("llm.provider.load_dotenv"):
                result = generate_with_tools(_MESSAGES, _TOOLS)

    tc = result["tool_calls"][0]
    assert tc["parse_error"] is True
    assert tc["arguments"]["_raw"] == "{not valid json"


def test_openai_compat_no_tools_omits_tools_kwarg():
    """A forced final-answer call (tools=[]) must not send an empty tools array."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_openai_response(content="Final answer.")

    with patch("llm.provider._openai_client", return_value=fake_client):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}):
            with patch("llm.provider.load_dotenv"):
                generate_with_tools(_MESSAGES, tools=[])

    _, kwargs = fake_client.chat.completions.create.call_args
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs


def test_unknown_provider_raises():
    with patch.dict(os.environ, {"LLM_PROVIDER": "fictional_provider"}):
        with patch("llm.provider.load_dotenv"):
            with pytest.raises(RuntimeError, match="Unknown LLM_PROVIDER"):
                generate_with_tools(_MESSAGES, _TOOLS)


# ── Anthropic translation shim ──────────────────────────────────────────────────

def test_to_anthropic_tools_renames_parameters_to_input_schema():
    converted = _to_anthropic_tools(_TOOLS)
    assert converted == [{
        "name": "resolve_drug_name",
        "description": "Resolve a drug name to its canonical INN.",
        "input_schema": _TOOLS[0]["parameters"],
    }]


def test_to_anthropic_messages_splits_system_and_translates_tool_turns():
    messages = [
        {"role": "system", "content": "sys prompt"},
        {"role": "user", "content": "Is Tahor safe with warfarin?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "resolve_drug_name", "arguments": '{"name": "Tahor"}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": json.dumps({"status": "found"})},
    ]

    system, anthropic_messages = _to_anthropic_messages(messages)

    assert system == "sys prompt"
    assert anthropic_messages[0] == {"role": "user", "content": "Is Tahor safe with warfarin?"}

    assistant_block = anthropic_messages[1]
    assert assistant_block["role"] == "assistant"
    assert assistant_block["content"][0]["type"] == "tool_use"
    assert assistant_block["content"][0]["input"] == {"name": "Tahor"}

    # Anthropic requires tool results as a user-role message with a tool_result block
    tool_result_block = anthropic_messages[2]
    assert tool_result_block["role"] == "user"
    assert tool_result_block["content"][0]["type"] == "tool_result"
    assert tool_result_block["content"][0]["tool_use_id"] == "call_1"


def test_anthropic_with_tools_normalizes_tool_use_block():
    fake_tool_use_block = SimpleNamespace(type="tool_use", id="call_1", name="resolve_drug_name", input={"name": "Tahor"})
    fake_response = SimpleNamespace(content=[fake_tool_use_block], stop_reason="tool_use")

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("anthropic.Anthropic", return_value=fake_client):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "LLM_PROVIDER": "anthropic"}):
            with patch("llm.provider.load_dotenv"):
                result = generate_with_tools(_MESSAGES, _TOOLS)

    assert result["stop_reason"] == "tool_calls"
    assert result["tool_calls"] == [
        {"id": "call_1", "name": "resolve_drug_name", "arguments": {"name": "Tahor"}, "parse_error": False},
    ]
