"""
MedFlow agent — tool-calling pharmacy safety agent (Week 4).

Usage:
    from agent import run_agent

    result = run_agent("New prescription is clarithromycin for a patient "
                        "already on simvastatin and warfarin.")
    print(result["final_answer"])
    print(pretty_print(result["trace"]))
"""
from .loop import run_agent
from .tools import TOOLS, TOOL_REGISTRY, call_tool
from .prompts import agent_system_prompt
from .trace import pretty_print

__all__ = [
    "run_agent", "TOOLS", "TOOL_REGISTRY", "call_tool",
    "agent_system_prompt", "pretty_print",
]
