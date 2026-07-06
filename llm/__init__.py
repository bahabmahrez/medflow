"""
MedFlow LLM layer.

Usage:
    from llm import generate, load_system_prompt

    system  = load_system_prompt()
    answer  = generate(system, "Is simvastatin safe with clarithromycin?",
                       context="CYP3A4 competition detected. Clarithromycin ...")
"""
import os as _os

from .provider import generate, generate_with_tools, LLM_PROVIDER, LLM_MODEL

_PROMPT_PATH = _os.path.join(_os.path.dirname(__file__), "system_prompt.txt")


def load_system_prompt() -> str:
    """Load the system prompt from llm/system_prompt.txt."""
    with open(_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


__all__ = ["generate", "generate_with_tools", "load_system_prompt", "LLM_PROVIDER", "LLM_MODEL"]
