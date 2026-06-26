"""Shared Neo4j connection helper for graph trap verification scripts."""
import os
from neo4j import GraphDatabase


NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "medflow")


def connect():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def pass_(msg: str = "") -> None:
    print(f"PASS  {msg}")
    raise SystemExit(0)


def fail(msg: str = "") -> None:
    print(f"FAIL  {msg}")
    raise SystemExit(1)
