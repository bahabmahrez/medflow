"""
Shared Neo4j helpers for all graph loaders.

Usage in each loader:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _neo4j import connect, SEVERITY_RANK, most_conservative, ordered_inns
"""
import os
from neo4j import GraphDatabase

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


def connect():
    """Return a Neo4j Driver.  Caller is responsible for driver.close()."""
    auth = (NEO4J_USER, NEO4J_PASSWORD) if NEO4J_USER else None
    return GraphDatabase.driver(NEO4J_URI, auth=auth)


SEVERITY_RANK: dict[str, int] = {
    "contre_indique":      4,
    "deconseillee":        3,
    "precaution_emploi":   2,
    "a_prendre_en_compte": 1,
    "major":               4,
    "moderate":            2,
    "minor":               1,
}


def most_conservative(s1: str | None, s2: str | None) -> str | None:
    if not s1:
        return s2
    if not s2:
        return s1
    return s1 if SEVERITY_RANK.get(s1, 0) >= SEVERITY_RANK.get(s2, 0) else s2


def ordered_inns(inn_a: str, inn_b: str) -> tuple[str, str]:
    """Return the two INNs in alphabetical order for consistent INTERACTS_WITH direction."""
    return (inn_a, inn_b) if inn_a <= inn_b else (inn_b, inn_a)
