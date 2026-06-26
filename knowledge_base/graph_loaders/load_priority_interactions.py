"""
Graph loader 5 — INTERACTS_WITH edges from FDA label text.

Mirrors knowledge_base/DB_loaders/load_priority_interactions.py.
Only sets severity_drugbank; never overwrites severity_ansm.
severity_active is recomputed as the more conservative of the two.
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, SEVERITY_RANK, most_conservative, ordered_inns

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "../sources/dataset/interactions_priority_50.csv")

driver = connect()
loaded = skipped_no_mol = skipped_exists = updated = 0

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        inn_a            = row["inn_a"].strip()
        inn_b            = row["inn_b"].strip()
        severity_openfda = row["severity_inferred"].strip()
        extracted_text   = row["extracted_text"].strip()[:1000] or None
        rank             = SEVERITY_RANK.get(severity_openfda, 0)

        inn_a, inn_b = ordered_inns(inn_a, inn_b)

        # Check if both molecules exist
        check = driver.execute_query(
            "MATCH (a:Molecule {inn:$a}), (b:Molecule {inn:$b}) RETURN 1 LIMIT 1",
            a=inn_a, b=inn_b,
        )
        if not check.records:
            skipped_no_mol += 1
            continue

        # Check if ANSM data already present (don't overwrite)
        existing = driver.execute_query(
            """
            MATCH (a:Molecule {inn:$a})-[r:INTERACTS_WITH]-(b:Molecule {inn:$b})
            RETURN r.severity_ansm AS ansm, r.severity_drugbank AS db, r.severity_active AS active
            """,
            a=inn_a, b=inn_b,
        )

        if existing.records:
            rec = existing.records[0]
            if rec["db"] is not None:
                skipped_exists += 1
                continue
            existing_ansm   = rec["ansm"]
            new_active      = most_conservative(existing_ansm, severity_openfda)
            new_rank        = SEVERITY_RANK.get(new_active, 0)
            driver.execute_query(
                """
                MATCH (a:Molecule {inn:$a})-[r:INTERACTS_WITH]-(b:Molecule {inn:$b})
                SET r.severity_drugbank = $sev_db,
                    r.severity_active   = $sev_active,
                    r.severity_rank     = $rank,
                    r.clinical_effect   = coalesce(r.clinical_effect, $clinical_effect)
                """,
                a=inn_a, b=inn_b, sev_db=severity_openfda,
                sev_active=new_active, rank=new_rank, clinical_effect=extracted_text,
            )
            updated += 1
        else:
            try:
                driver.execute_query(
                    """
                    MATCH (a:Molecule {inn:$a}), (b:Molecule {inn:$b})
                    MERGE (a)-[r:INTERACTS_WITH]->(b)
                    ON CREATE SET
                        r.severity_drugbank = $sev_db,
                        r.severity_active   = $sev_db,
                        r.severity_rank     = $rank,
                        r.clinical_effect   = $clinical_effect,
                        r.source_confidence = 'openfda_label'
                    """,
                    a=inn_a, b=inn_b, sev_db=severity_openfda,
                    rank=rank, clinical_effect=extracted_text,
                )
                loaded += 1
            except Exception as e:
                print(f"  SKIP {inn_a}+{inn_b}: {e}")
                skipped_no_mol += 1

driver.close()
print(f"\nDone.")
print(f"  New pairs inserted:       {loaded}")
print(f"  Existing pairs enriched:  {updated}")
print(f"  Already had openfda data: {skipped_exists}")
print(f"  Skipped (no molecule):    {skipped_no_mol}")
