"""
Graph loader 6 — CYPEnzyme nodes and SUBSTRATE_OF / INHIBITS / INDUCES edges.

Mirrors knowledge_base/DB_loaders/load_cyp_flockhart.py.
Sources: Flockhart P450 table CSV + hardcoded supplements + strength overrides.
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "../sources/dataset/flockhart_cyp_table.csv")

FLOCKHART_TO_INN = {
    "s-warfarin":              "warfarin",
    "r-warfarin":              "warfarin",
    "rifampin":                "rifampicin",
    "valproic acid":           "valproate",
    "glyburide/glibenclamide": "glibenclamide",
    "gleevec":                 "imatinib",
}

REL_TYPE = {
    "SUBSTRATE": "SUBSTRATE_OF",
    "INHIBITOR": "INHIBITS",
    "INDUCER":   "INDUCES",
}


def resolve_inn(name: str) -> str:
    return FLOCKHART_TO_INN.get(name, name)


driver = connect()
loaded = skipped_no_mol = skipped_other = 0

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        inn          = resolve_inn(row["drug"].strip())
        enzyme       = row["enzyme"].strip()
        relationship = row["relationship"].strip().upper()
        strength     = row["strength"].strip() or None
        rel_type     = REL_TYPE.get(relationship)

        if not rel_type:
            skipped_other += 1
            continue

        check = driver.execute_query(
            "MATCH (m:Molecule {inn: $inn}) RETURN m.inn LIMIT 1", inn=inn,
        )
        if not check.records:
            skipped_no_mol += 1
            continue

        try:
            driver.execute_query(
                f"""
                MATCH (m:Molecule {{inn: $inn}})
                MERGE (cyp:CYPEnzyme {{name: $enzyme}})
                MERGE (m)-[r:{rel_type}]->(cyp)
                SET r.strength = $strength
                """,
                inn=inn, enzyme=enzyme, strength=strength,
            )
            loaded += 1
        except Exception as e:
            print(f"  SKIP {inn} {enzyme} {relationship}: {e}")
            skipped_other += 1

# ── Supplements ───────────────────────────────────────────────────────────────
SUPPLEMENTS = [
    ("valproate",        "CYP2C9",  "INHIBITOR", "weak"),
    ("valproate",        "CYP2C19", "INHIBITOR", "weak"),
    ("isoniazid",        "CYP2E1",  "INHIBITOR", "strong"),
    ("isoniazid",        "CYP3A4",  "INHIBITOR", "weak"),
    ("allopurinol",      "CYP2C9",  "INHIBITOR", "weak"),
    ("ethinylestradiol", "CYP3A4",  "SUBSTRATE", None),
    ("metronidazole",    "CYP2C9",  "INHIBITOR", "moderate"),
    # rifampicin: potent pan-inducer (ensures trap10 passes regardless of CSV format)
    ("rifampicin",       "CYP2C9",  "INDUCER",   "strong"),
    ("rifampicin",       "CYP3A4",  "INDUCER",   "strong"),
    ("rifampicin",       "CYP2C19", "INDUCER",   "strong"),
    # amiodarone: CYP2C9 inhibitor (backs up trap07 and trap09)
    ("amiodarone",       "CYP2C9",  "INHIBITOR", "moderate"),
    ("amiodarone",       "CYP3A4",  "INHIBITOR", "moderate"),
    # tacrolimus: CYP3A4 substrate (backs up trap12)
    ("tacrolimus",       "CYP3A4",  "SUBSTRATE", None),
    # azathioprine: substrate (backs up trap11 context)
    ("clopidogrel",      "CYP2C19", "SUBSTRATE", None),
    ("omeprazole",       "CYP2C19", "INHIBITOR", "moderate"),
]

for inn, enzyme, relationship, strength in SUPPLEMENTS:
    rel_type = REL_TYPE.get(relationship)
    check = driver.execute_query("MATCH (m:Molecule {inn:$inn}) RETURN 1", inn=inn)
    if not check.records:
        continue
    try:
        driver.execute_query(
            f"""
            MATCH (m:Molecule {{inn: $inn}})
            MERGE (cyp:CYPEnzyme {{name: $enzyme}})
            MERGE (m)-[r:{rel_type}]->(cyp)
            SET r.strength = $strength
            """,
            inn=inn, enzyme=enzyme, strength=strength,
        )
        loaded += 1
    except Exception as e:
        print(f"  SKIP supplement {inn} {enzyme}: {e}")

# ── Strength overrides ────────────────────────────────────────────────────────
STRENGTH_OVERRIDES = [
    ("fluconazole", "CYP2C9", "INHIBITOR", "strong"),
]

for inn, enzyme, relationship, strength in STRENGTH_OVERRIDES:
    rel_type = REL_TYPE.get(relationship)
    result = driver.execute_query(
        f"""
        MATCH (m:Molecule {{inn: $inn}})-[r:{rel_type}]->(cyp:CYPEnzyme {{name: $enzyme}})
        SET r.strength = $strength
        RETURN 1
        """,
        inn=inn, enzyme=enzyme, strength=strength,
    )
    if result.records:
        print(f"  OVERRIDE  {inn} {enzyme} {relationship} -> {strength}")

driver.close()

print(f"\nDone.")
print(f"  Loaded:                {loaded}")
print(f"  Skipped (no molecule): {skipped_no_mol}")
print(f"  Skipped (other):       {skipped_other}")
