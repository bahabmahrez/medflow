"""
Agent system prompt — Week 3's 8 safety rules plus the Week 4 agentic addendum.

The addendum is stored separately from llm/system_prompt.txt (not concatenated
into a duplicate copy on disk) so the two never drift out of sync.
"""
import os

from llm import load_system_prompt

_ADDENDUM_PATH = os.path.join(os.path.dirname(__file__), "system_prompt_addendum.txt")

_AGENT_SYSTEM_PROMPT: str | None = None


def _load_addendum() -> str:
    with open(_ADDENDUM_PATH, encoding="utf-8") as f:
        return f.read()


def agent_system_prompt() -> str:
    """Return the full agent system prompt (base rules + agentic addendum), cached."""
    global _AGENT_SYSTEM_PROMPT
    if _AGENT_SYSTEM_PROMPT is None:
        _AGENT_SYSTEM_PROMPT = load_system_prompt() + "\n\n" + _load_addendum()
    return _AGENT_SYSTEM_PROMPT
