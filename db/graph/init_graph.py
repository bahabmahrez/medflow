"""
MedFlow — Neo4j graph schema initialiser.

Reads db/graph/schema.cypher and applies every constraint and index
to the running Neo4j instance.  Safe to re-run: all statements use
IF NOT EXISTS so nothing is dropped or duplicated.

Usage:
    python db/graph/init_graph.py

Environment variables (with defaults matching docker-compose.yml):
    NEO4J_URI      bolt://localhost:7687
    NEO4J_USER     neo4j
    NEO4J_PASSWORD medflow
"""

import os
import sys
from pathlib import Path

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError


NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "medflow")

SCHEMA_FILE = Path(__file__).parent / "schema.cypher"


def _parse_statements(cypher: str) -> list[str]:
    """Split schema.cypher into individual statements, stripping comments."""
    statements = []
    current: list[str] = []
    for line in cypher.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped == "":
            continue
        current.append(stripped)
        if stripped.endswith(";"):
            stmt = " ".join(current).rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []
    return statements


def run():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
    except ServiceUnavailable:
        print(f"ERROR: Cannot reach Neo4j at {NEO4J_URI}")
        print("       Is the container running?  →  docker compose up -d neo4j")
        sys.exit(1)
    except AuthError:
        print("ERROR: Neo4j authentication failed.")
        print(f"       Check NEO4J_USER / NEO4J_PASSWORD (current: {NEO4J_USER} / ***)")
        sys.exit(1)

    print(f"Connected to Neo4j at {NEO4J_URI}\n")

    cypher = SCHEMA_FILE.read_text(encoding="utf-8")
    statements = _parse_statements(cypher)

    constraints = [s for s in statements if "CONSTRAINT" in s]
    indexes     = [s for s in statements if "INDEX"      in s and "CONSTRAINT" not in s]

    print(f"Applying {len(constraints)} constraints and {len(indexes)} indexes ...\n")

    applied = {"constraint": 0, "index": 0, "skipped": 0}

    with driver.session() as session:
        for stmt in statements:
            kind = "constraint" if "CONSTRAINT" in stmt else "index"
            # Extract the name (second token after CREATE CONSTRAINT / CREATE INDEX)
            tokens = stmt.split()
            name = tokens[2] if len(tokens) > 2 else "?"
            try:
                session.run(stmt)
                print(f"  OK  {kind:10s}  {name}")
                applied[kind] += 1
            except Exception as exc:
                # IF NOT EXISTS means this should never raise, but be safe
                print(f"  !!  {kind:10s}  {name}  →  {exc}")
                applied["skipped"] += 1

    print()
    _print_summary(driver)
    driver.close()


def _print_summary(driver):
    with driver.session() as session:
        constraints = session.run("SHOW CONSTRAINTS").data()
        indexes     = session.run("SHOW INDEXES WHERE type <> 'LOOKUP'").data()

    print("─" * 60)
    print(f"Schema summary")
    print(f"  Constraints : {len(constraints)}")
    print(f"  Indexes     : {len(indexes)}")
    print()

    print("  Node labels expected by schema:")
    labels = [
        "Molecule", "Drug", "CYPEnzyme", "DrugClass",
        "DiseaseConcept", "AllergyGroup", "MolecularTarget",
        "Patient", "LabResult",
    ]
    for label in labels:
        print(f"    · {label}")

    print()
    print("  Relationship types expected by loaders:")
    rel_types = [
        "BRAND_OF", "INTERACTS_WITH", "SUBSTRATE_OF", "INHIBITS", "INDUCES",
        "MEMBER_OF", "CLASS_INTERACTS_WITH", "CONTRAINDICATED_FOR", "INDICATED_FOR",
        "BELONGS_TO_ALLERGY_GROUP", "CROSS_REACTS_WITH", "TARGETS",
        "HAS_ADVERSE_EFFECT", "TAKES", "HAS_CONDITION", "ALLERGIC_TO", "HAS_LAB",
    ]
    for rt in rel_types:
        print(f"    · {rt}")

    print()
    print("Neo4j Browser  →  http://localhost:7474")
    print("Bolt URI       →  bolt://localhost:7687")
    print()
    print("Next step: python run_loaders_graph.py")


if __name__ == "__main__":
    run()
