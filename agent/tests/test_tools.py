"""Tests for agent.tools — schema shape, registry, and safe dispatch."""
from unittest.mock import patch, MagicMock

from agent.tools import TOOLS, TOOL_REGISTRY, call_tool


def test_all_ten_tools_registered():
    names = {t["name"] for t in TOOLS}
    assert names == set(TOOL_REGISTRY.keys())
    assert len(TOOLS) == 10


def test_every_tool_has_name_description_and_parameters_schema():
    for t in TOOLS:
        assert t["name"]
        assert len(t["description"]) > 20, f"{t['name']} description too vague"
        assert t["parameters"]["type"] == "object"
        assert "properties" in t["parameters"]


def test_call_tool_unknown_name_returns_error_not_raise():
    result = call_tool("delete_all_patients", {})
    assert result["status"] == "error"
    assert "Unknown tool" in result["message"]


def test_call_tool_missing_required_argument_returns_error_not_raise():
    result = call_tool("check_contraindications", {"drug": "metformin"})  # missing "conditions"
    assert result["status"] == "error"
    assert "conditions" in result["message"]


def test_call_tool_parse_error_short_circuits_without_calling_function():
    mocked = MagicMock()
    with patch.dict(TOOL_REGISTRY, {"resolve_drug_name": mocked}):
        result = call_tool("resolve_drug_name", {"name": "Tahor", "parse_error": True, "_raw": "{bad json"})
    assert result["status"] == "error"
    assert "not valid JSON" in result["message"]
    mocked.assert_not_called()


def test_call_tool_dispatches_with_kwargs():
    def fake_resolve(name):
        assert name == "Tahor"
        return {"status": "found", "data": {"canonical": "atorvastatin"}, "message": "ok"}

    with patch.dict(TOOL_REGISTRY, {"resolve_drug_name": fake_resolve}):
        result = call_tool("resolve_drug_name", {"name": "Tahor"})

    assert result["status"] == "found"
    assert result["data"]["canonical"] == "atorvastatin"


def test_call_tool_catches_exception_from_underlying_function():
    def boom(**kwargs):
        raise RuntimeError("neo4j connection refused")

    with patch.dict(TOOL_REGISTRY, {"resolve_drug_name": boom}):
        result = call_tool("resolve_drug_name", {"name": "Tahor"})

    assert result["status"] == "error"
    assert "neo4j connection refused" in result["message"]
