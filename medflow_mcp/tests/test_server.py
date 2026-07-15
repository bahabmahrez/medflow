"""
Tests for the MedFlow MCP server — verifies tool registration and smoke-tests
tool execution against the live Neo4j graph.
"""
import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from medflow_mcp.server import (
    mcp,
    resolve_drug_name_tool,
    get_drug_profile_tool,
    detect_pairwise_interactions_tool,
    detect_cyp_competition_tool,
    check_contraindications_tool,
    check_allergy_conflict_tool,
    check_therapeutic_duplication_tool,
    check_dose_appropriateness_tool,
    get_drugs_by_class_tool,
    full_prescription_check_tool,
)


class TestToolRegistration:
    """Verify all 10 tools are registered with the FastMCP server."""

    def test_tool_count(self):
        tools = mcp._tool_manager.list_tools()
        assert len(tools) == 10

    def test_tool_names(self):
        names = {t.name for t in mcp._tool_manager.list_tools()}
        expected = {
            "resolve_drug_name_tool",
            "get_drug_profile_tool",
            "detect_pairwise_interactions_tool",
            "detect_cyp_competition_tool",
            "check_contraindications_tool",
            "check_allergy_conflict_tool",
            "check_therapeutic_duplication_tool",
            "check_dose_appropriateness_tool",
            "get_drugs_by_class_tool",
            "full_prescription_check_tool",
        }
        assert names == expected

    def test_resource_count(self):
        resources = mcp._resource_manager.list_resources()
        assert len(resources) == 3

    def test_prompt_count(self):
        prompts = mcp._prompt_manager.list_prompts()
        assert len(prompts) == 3


class TestToolExecution:
    """Smoke-tests: call each tool and verify it returns valid JSON."""

    def test_resolve_drug_name(self):
        result = json.loads(resolve_drug_name_tool("Tahor"))
        assert result["status"] == "found"
        assert result["data"]["canonical"] == "atorvastatin"

    def test_resolve_drug_name_not_found(self):
        result = json.loads(resolve_drug_name_tool("zyboxithol"))
        assert result["status"] == "not_found"

    def test_get_drug_profile(self):
        result = json.loads(get_drug_profile_tool("warfarin"))
        assert result["status"] == "found"
        assert result["data"]["inn"] == "warfarin"
        assert "interactions" in result["data"]
        assert "cyp_relationships" in result["data"]

    def test_detect_pairwise_interactions(self):
        result = json.loads(detect_pairwise_interactions_tool(["warfarin", "aspirin"]))
        assert result["status"] == "found"
        assert result["data"]["interactions_found"] >= 1

    def test_detect_cyp_competition(self):
        result = json.loads(detect_cyp_competition_tool(["simvastatin", "clarithromycin"]))
        assert result["status"] == "found"
        assert result["data"]["competitions_found"] >= 1

    def test_check_contraindications(self):
        result = json.loads(check_contraindications_tool("metformin", ["renal impairment"]))
        assert result["status"] == "found"

    def test_check_allergy_conflict(self):
        result = json.loads(check_allergy_conflict_tool("amoxicillin", ["penicillin"]))
        assert result["status"] == "found"

    def test_check_therapeutic_duplication(self):
        result = json.loads(check_therapeutic_duplication_tool("atorvastatin", ["Tahor"]))
        assert result["status"] == "found"

    def test_check_dose_appropriateness(self):
        result = json.loads(check_dose_appropriateness_tool(
            "ciprofloxacin", dose="500mg", age=78,
            labs={"creatinine_umol_L": 210}
        ))
        assert result["status"] == "found"

    def test_get_drugs_by_class(self):
        result = json.loads(get_drugs_by_class_tool("HMG CoA Reductase Inhibitor"))
        assert result["status"] == "found"
        assert result["data"]["count"] >= 1

    def test_full_prescription_check(self):
        result = json.loads(full_prescription_check_tool(
            prescription=[{"drug": "simvastatin", "dose": "40mg"}, {"drug": "clarithromycin"}],
            patient_meds=["warfarin"],
            conditions=["diabetes"],
            allergies=["penicillin"],
        ))
        assert "summary" in result["data"]
        assert result["data"]["summary"]["overall_risk"] in ("LOW", "MEDIUM", "HIGH")
