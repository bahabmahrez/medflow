"""
Permissions layer for MedFlow agent tools.

Classifies tools as read-only or action (write-capable).
Action tools require explicit human confirmation before execution.

The classification is used by agent/loop.py as a gate before any tool
call is dispatched through MCP.
"""
from __future__ import annotations

import json
import sys

# All 10 current tools are read-only — none write data today.
# This set determines which tools execute without interruption.
READ_ONLY_TOOLS = frozenset({
    "resolve_drug_name",
    "get_drug_profile",
    "detect_pairwise_interactions",
    "detect_cyp_competition",
    "check_contraindications",
    "check_allergy_conflict",
    "check_therapeutic_duplication",
    "check_dose_appropriateness",
    "get_drugs_by_class",
    "full_prescription_check",
})

# Reserved for future write-capable tools (e.g. Week 6+).
# Any tool name added here will require human confirmation before execution.
ACTION_TOOLS: set[str] = set()


def classify_tool(tool_name: str) -> str:
    """
    Return the permission class for *tool_name*.

    Returns ``"read-only"`` for the 10 current safety-check tools.
    Returns ``"action"`` for any tool registered in ``ACTION_TOOLS``.
    Unknown tools default to ``"action"`` as a fail-safe.
    """
    if tool_name in ACTION_TOOLS:
        return "action"
    if tool_name in READ_ONLY_TOOLS:
        return "read-only"
    return "action"


def require_confirmation(tool_name: str, arguments: dict) -> bool:
    """
    Prompt the user (via stdin/stdout) to confirm an action-class tool call.

    Returns ``True`` if the user confirms, ``False`` if rejected.

    .. note::
        This function is designed to be patchable in tests. Tests should mock
        it to return ``True`` or ``False`` without blocking on stdin.
    """
    args_str = json.dumps(arguments, indent=2, ensure_ascii=False)
    print(f"\n⚠️  ACTION TOOL REQUIRES CONFIRMATION")
    print(f"    Tool:   {tool_name}")
    print(f"    Args:   {args_str}")
    while True:
        try:
            response = input("    Proceed? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n    Cancelled (input closed).")
            return False
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            print("    Cancelled.")
            return False
        print("    Enter 'y' or 'n'.")

