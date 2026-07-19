"""
MedFlow MCP Server — wraps the 10 query-layer functions as MCP tools.

Run with:
    mcp dev medflow_mcp/server.py          # MCP Inspector (debugging)
    mcp run medflow_mcp/server.py           # stdio transport (for Claude Desktop)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Add project root to sys.path so query imports work when run via `mcp run`
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from query import (
    resolve_drug_name,
    get_drug_profile,
    get_drugs_by_class,
    detect_pairwise_interactions,
    detect_cyp_competition,
    check_contraindications,
    check_allergy_conflict,
    check_therapeutic_duplication,
    check_dose_appropriateness,
    full_prescription_check,
)

mcp = FastMCP(
    "MedFlow",
    instructions=(
        "MedFlow is a pharmacy safety assistant. You have access to a Neo4j "
        "knowledge graph of drugs, interactions, contraindications, allergies, "
        "and dosing guidance. Always call tools before answering drug-safety "
        "questions — never guess from training data. When pairwise interactions "
        "come back empty, follow up with CYP competition detection. Lead with "
        "the most severe finding."
    ),
)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def resolve_drug_name_tool(name: str) -> str:
    """Resolve any drug name (INN, brand, Tunisian brand, French brand) to its
    canonical INN molecule. Call this FIRST for unfamiliar or brand names."""
    return _json(resolve_drug_name(name))


@mcp.tool()
def get_drug_profile_tool(drug: str) -> str:
    """Retrieve everything the graph knows about one drug: brands, drug class,
    CYP relationships, interactions, contraindications, allergy group."""
    return _json(get_drug_profile(drug))


@mcp.tool()
def detect_pairwise_interactions_tool(drug_list: list[str]) -> str:
    """Check for direct, documented interactions between 2+ named drugs.
    Only include drugs the pharmacist actually named."""
    return _json(detect_pairwise_interactions(drug_list))


@mcp.tool()
def detect_cyp_competition_tool(drug_list: list[str]) -> str:
    """Check for enzyme-mediated (CYP450) interactions between 2+ drugs that
    have no direct interaction edge. Always run alongside pairwise checks."""
    return _json(detect_cyp_competition(drug_list))


@mcp.tool()
def check_contraindications_tool(drug: str, conditions: list[str]) -> str:
    """Check whether a drug is contraindicated for one or more patient conditions.
    Accepts free text or ICD-11 codes."""
    return _json(check_contraindications(drug, conditions))


@mcp.tool()
def check_allergy_conflict_tool(drug: str, allergies: list[str]) -> str:
    """Check whether a drug conflicts with the patient's allergies, including
    cross-reactivity (e.g. penicillin vs. cephalosporins)."""
    return _json(check_allergy_conflict(drug, allergies))


@mcp.tool()
def check_therapeutic_duplication_tool(new_drug: str, active_meds: list[str]) -> str:
    """Check whether a new drug is already being taken under a different
    brand/generic name."""
    return _json(check_therapeutic_duplication(new_drug, active_meds))


@mcp.tool()
def check_dose_appropriateness_tool(
    drug: str,
    dose: str | None = None,
    age: int | None = None,
    weight: float | None = None,
    labs: dict | None = None,
) -> str:
    """Check whether a prescribed dose needs adjustment for age, renal, or
    hepatic function. labs keys: creatinine_umol_L, egfr, alt_iu_L, ast_iu_L."""
    return _json(check_dose_appropriateness(drug, dose=dose, age=age, weight=weight, labs=labs))


@mcp.tool()
def get_drugs_by_class_tool(drug_class: str) -> str:
    """List all drugs in a given drug class or ATC prefix. Use for alternatives."""
    return _json(get_drugs_by_class(drug_class))


@mcp.tool()
def full_prescription_check_tool(
    prescription: list[dict] | None = None,
    patient_meds: list[str] | None = None,
    conditions: list[str] | None = None,
    allergies: list[str] | None = None,
    labs: dict | None = None,
) -> str:
    """Run a full consolidated safety check for one or more new drugs against the
    patient's active meds, conditions, allergies, and labs in one call.

    prescription: [{"drug": str, "dose"?: str}, ...]"""
    return _json(full_prescription_check(
        prescription,
        patient_meds=patient_meds,
        conditions=conditions,
        allergies=allergies,
        labs=labs,
    ))


# ── Resources ──────────────────────────────────────────────────────────────────

@mcp.resource("medflow://system-prompt")
def get_system_prompt() -> str:
    """Return the agent system prompt addendum for MedFlow."""
    prompt_path = Path(_PROJECT_ROOT) / "agent" / "system_prompt_addendum.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return "System prompt not found."


@mcp.resource("medflow://tools")
def get_tool_list() -> str:
    """Return the list of available tools and their descriptions."""
    tools = [
        {"name": "resolve_drug_name_tool", "description": "Resolve any drug name to canonical INN"},
        {"name": "get_drug_profile_tool", "description": "Full drug profile from knowledge graph"},
        {"name": "detect_pairwise_interactions_tool", "description": "Direct drug interactions"},
        {"name": "detect_cyp_competition_tool", "description": "CYP450 enzyme-mediated interactions"},
        {"name": "check_contraindications_tool", "description": "Contraindications vs patient conditions"},
        {"name": "check_allergy_conflict_tool", "description": "Allergy and cross-reactivity conflicts"},
        {"name": "check_therapeutic_duplication_tool", "description": "Duplicate therapy detection"},
        {"name": "check_dose_appropriateness_tool", "description": "Dose adjustment flags"},
        {"name": "get_drugs_by_class_tool", "description": "List drugs in a class"},
        {"name": "full_prescription_check_tool", "description": "Full consolidated safety check"},
    ]
    return _json(tools)


@mcp.resource("medflow://graph-stats")
def get_graph_stats() -> str:
    """Return basic statistics about the Neo4j knowledge graph."""
    from query._neo4j import connect
    driver = connect()
    try:
        result = driver.execute_query(
            "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC"
        )
        stats = {rec["label"]: rec["count"] for rec in result.records}
        return _json({"total_nodes": sum(stats.values()), "by_label": stats})
    except Exception as exc:
        return _json({"error": str(exc)})
    finally:
        driver.close()


# ── Prompts ────────────────────────────────────────────────────────────────────

@mcp.prompt()
def evaluate_prescription(
    drugs: str,
    patient_meds: str = "",
    conditions: str = "",
    allergies: str = "",
) -> str:
    """Generate a structured prompt for evaluating a new prescription.

    Args:
        drugs: Comma-separated new drug names (e.g. "simvastatin, clarithromycin")
        patient_meds: Comma-separated current medications
        conditions: Comma-separated patient conditions
        allergies: Comma-separated patient allergies
    """
    drug_list = [d.strip() for d in drugs.split(",") if d.strip()]
    med_list = [m.strip() for m in patient_meds.split(",") if m.strip()] if patient_meds else []
    cond_list = [c.strip() for c in conditions.split(",") if c.strip()] if conditions else []
    allerg_list = [a.strip() for a in allergies.split(",") if a.strip()] if allergies else []

    parts = [f"New prescription: {', '.join(drug_list)}"]
    if med_list:
        parts.append(f"Current medications: {', '.join(med_list)}")
    if cond_list:
        parts.append(f"Patient conditions: {', '.join(cond_list)}")
    if allerg_list:
        parts.append(f"Allergies: {', '.join(allerg_list)}")

    parts.append(
        "\nInstructions:\n"
        "1. If any drug name is unfamiliar, call resolve_drug_name_tool first.\n"
        "2. Call detect_pairwise_interactions_tool for all drugs together.\n"
        "3. Call detect_cyp_competition_tool for all drugs together.\n"
        "4. For each new drug, call check_contraindications_tool and check_allergy_conflict_tool.\n"
        "5. If a dose was provided, call check_dose_appropriateness_tool.\n"
        "6. Summarize all findings, leading with the most severe."
    )

    return "\n".join(parts)


@mcp.prompt()
def drug_info(drug_name: str) -> str:
    """Generate a prompt to look up a drug's full profile.

    Args:
        drug_name: The drug name to look up
    """
    return (
        f"Look up the full profile for '{drug_name}' using get_drug_profile_tool. "
        f"Present the results in a clear, organized format covering: brand names, "
        f"drug class, interactions, CYP relationships, contraindications, and "
        f"allergy group."
    )


@mcp.prompt()
def check_interactions(drug_names: str) -> str:
    """Generate a prompt to check interactions between drugs.

    Args:
        drug_names: Comma-separated drug names to check
    """
    drugs = [d.strip() for d in drug_names.split(",") if d.strip()]
    return (
        f"Check all interactions between: {', '.join(drugs)}.\n"
        f"1. Call detect_pairwise_interactions_tool with the full list.\n"
        f"2. Call detect_cyp_competition_tool with the full list.\n"
        f"3. Present findings sorted by severity (most severe first)."
    )


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
