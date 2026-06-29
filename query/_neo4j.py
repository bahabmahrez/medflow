"""Shared Neo4j connection + return-envelope helpers for all query functions."""
import os
from neo4j import GraphDatabase

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


def connect():
    auth = (NEO4J_USER, NEO4J_PASSWORD) if NEO4J_USER else None
    return GraphDatabase.driver(NEO4J_URI, auth=auth)


def ok(data: dict, message: str = "") -> dict:
    return {"status": "found", "data": data, "message": message}


def not_found(message: str = "", data: dict | None = None) -> dict:
    return {"status": "not_found", "data": data or {}, "message": message}


def err(message: str = "") -> dict:
    return {"status": "error", "data": {}, "message": message}
