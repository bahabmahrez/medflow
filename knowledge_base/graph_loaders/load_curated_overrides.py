"""
Graph loader 8 — Curated high-risk severity upgrades.

Mirrors knowledge_base/DB_loaders/load_curated_overrides.py.
Never downgrades. Upgrades INTERACTS_WITH and CLASS_INTERACTS_WITH severity
when the curated value is higher than what's already stored.
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from _neo4j import connect, SEVERITY_RANK, ordered_inns

# (inn_a, inn_b, severity, clinical_effect)
OVERRIDES = [
    (
        "tacrolimus", "fluconazole", "contre_indique",
        "Fluconazole (strong CYP3A4/CYP2C19 inhibitor) markedly increases tacrolimus "
        "exposure, leading to tacrolimus toxicity (nephrotoxicity, neurotoxicity). "
        "Combination is contra-indicated; use alternative antifungal or switch immunosuppressant."
    ),
    (
        "methotrexate", "ibuprofen", "deconseillee",
        "NSAIDs reduce renal clearance of methotrexate, increasing risk of methotrexate "
        "toxicity (myelosuppression, mucositis, nephrotoxicity). Avoid combination; "
        "if unavoidable, monitor methotrexate levels closely."
    ),
    (
        "allopurinol", "azathioprine", "contre_indique",
        "Allopurinol inhibits xanthine oxidase, the primary enzyme responsible for "
        "azathioprine inactivation. Co-administration causes a 4-fold increase in "
        "azathioprine exposure, leading to severe myelosuppression. Combination is "
        "contra-indicated; reduce azathioprine dose by 75% if unavoidable."
    ),
    (
        "amiodarone", "warfarin", "contre_indique",
        "Amiodarone is a potent inhibitor of CYP2C9 and CYP3A4, markedly reducing warfarin "
        "metabolism. Plasma warfarin concentrations can double or triple, causing severe "
        "haemorrhage. Combination is contra-indicated; if unavoidable, reduce warfarin dose "
        "by 30-50% and monitor INR twice weekly."
    ),
    (
        "amiodarone", "digoxin", "deconseillee",
        "Amiodarone inhibits P-glycoprotein and reduces renal clearance of digoxin, "
        "increasing digoxin plasma concentration by 70-100%. Risk of digoxin toxicity "
        "(bradycardia, AV block, arrhythmia). Halve the digoxin dose when starting "
        "amiodarone and monitor closely."
    ),
]

# (atc_a, atc_b, severity, clinical_effect)
CLASS_OVERRIDES = [
    (
        "M01AE", "B01AA", "deconseillee",
        "NSAIDs increase the anticoagulant effect of vitamin K antagonists by displacing "
        "them from plasma protein binding and inhibiting platelet function, raising the "
        "risk of bleeding. Combination should be avoided; if unavoidable, monitor INR closely."
    ),
]

driver = connect()
inserted = upgraded = skipped = 0
class_inserted = class_upgraded = class_skipped = 0

# ── Molecule-level overrides ──────────────────────────────────────────────────
for inn_a, inn_b, severity, effect in OVERRIDES:
    inn_a, inn_b = ordered_inns(inn_a, inn_b)
    curated_rank = SEVERITY_RANK.get(severity, 0)

    existing = driver.execute_query(
        """
        MATCH (a:Molecule {inn:$a})-[r:INTERACTS_WITH]-(b:Molecule {inn:$b})
        RETURN r.severity_active AS active, r.severity_rank AS rank
        """,
        a=inn_a, b=inn_b,
    )

    if existing.records:
        rec = existing.records[0]
        existing_rank = rec["rank"] or 0
        if curated_rank > existing_rank:
            driver.execute_query(
                """
                MATCH (a:Molecule {inn:$a})-[r:INTERACTS_WITH]-(b:Molecule {inn:$b})
                SET r.severity_ansm    = $sev,
                    r.severity_active  = $sev,
                    r.severity_rank    = $rank,
                    r.clinical_effect  = $effect,
                    r.source_confidence = 'curated'
                """,
                a=inn_a, b=inn_b, sev=severity, rank=curated_rank, effect=effect,
            )
            print(f"  UPGRADE  {inn_a} + {inn_b}: {rec['active']} -> {severity}")
            upgraded += 1
        else:
            print(f"  OK       {inn_a} + {inn_b}: already at {rec['active']}, no change")
            skipped += 1
    else:
        driver.execute_query(
            """
            MATCH (a:Molecule {inn:$a}), (b:Molecule {inn:$b})
            MERGE (a)-[r:INTERACTS_WITH]->(b)
            ON CREATE SET
                r.severity_ansm    = $sev,
                r.severity_active  = $sev,
                r.severity_rank    = $rank,
                r.clinical_effect  = $effect,
                r.source_confidence = 'curated'
            """,
            a=inn_a, b=inn_b, sev=severity, rank=curated_rank, effect=effect,
        )
        print(f"  INSERT   {inn_a} + {inn_b}: {severity}")
        inserted += 1

# ── Class-level overrides ─────────────────────────────────────────────────────
for atc_a, atc_b, severity, effect in CLASS_OVERRIDES:
    curated_rank = SEVERITY_RANK.get(severity, 0)
    if atc_a > atc_b:
        atc_a, atc_b = atc_b, atc_a

    existing = driver.execute_query(
        """
        MATCH (a:DrugClass {atc_code:$a})-[r:CLASS_INTERACTS_WITH]-(b:DrugClass {atc_code:$b})
        RETURN r.severity AS sev
        """,
        a=atc_a, b=atc_b,
    )

    if existing.records:
        rec = existing.records[0]
        existing_rank = SEVERITY_RANK.get(rec["sev"] or "", 0)
        if curated_rank > existing_rank:
            driver.execute_query(
                """
                MATCH (a:DrugClass {atc_code:$a})-[r:CLASS_INTERACTS_WITH]-(b:DrugClass {atc_code:$b})
                SET r.severity = $sev, r.clinical_effect = $effect
                """,
                a=atc_a, b=atc_b, sev=severity, effect=effect,
            )
            print(f"  UPGRADE class  {atc_a} + {atc_b}: {rec['sev']} -> {severity}")
            class_upgraded += 1
        else:
            print(f"  OK class       {atc_a} + {atc_b}: already at {rec['sev']}, no change")
            class_skipped += 1
    else:
        driver.execute_query(
            """
            MATCH (a:DrugClass {atc_code:$a}), (b:DrugClass {atc_code:$b})
            MERGE (a)-[r:CLASS_INTERACTS_WITH]->(b)
            ON CREATE SET r.severity = $sev, r.clinical_effect = $effect
            """,
            a=atc_a, b=atc_b, sev=severity, effect=effect,
        )
        print(f"  INSERT class   {atc_a} + {atc_b}: {severity}")
        class_inserted += 1

driver.close()
print(f"\nDone.")
print(f"  Class overrides    — Inserted: {class_inserted}  Upgraded: {class_upgraded}  Skipped: {class_skipped}")
print(f"  Molecule overrides — Inserted: {inserted}  Upgraded: {upgraded}  Skipped: {skipped}")
