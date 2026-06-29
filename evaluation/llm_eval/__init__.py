"""MedFlow GraphRAG evaluation suite — 30 cases across 3 tiers."""
from .cases import CASES, TIER1, TIER2, TIER3
from .runner import score, run_cases, report

__all__ = ["CASES", "TIER1", "TIER2", "TIER3", "score", "run_cases", "report"]
