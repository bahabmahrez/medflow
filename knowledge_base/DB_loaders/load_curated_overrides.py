"""
Curated high-risk drug interaction overrides.

These pairs are clinically critical and must be present at contre_indique /
deconseillee severity regardless of what OpenFDA or ANSM source files contain.

Rules:
  - If the pair already exists: upgrade severity_active and severity_ansm if the
    curated severity is higher; never downgrade.
  - If the pair does not exist: insert with source_confidence = 'curated'.
  - severity_ansm is set so the priority loader will never overwrite these.

Add new pairs here (never patch the DB directly) so colleagues get them on a
clean rebuild.
"""

import os
import psycopg2

SEVERITY_RANK = {
    "contre_indique":      4,
    "deconseillee":        3,
    "precaution_emploi":   2,
    "a_prendre_en_compte": 1,
}

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
]


def get_class_id(cur, atc_code: str):
    cur.execute("SELECT id FROM drug_classes WHERE atc_code = %s", (atc_code,))
    row = cur.fetchone()
    return row[0] if row else None


# (atc_a, atc_b, severity, clinical_effect)
CLASS_OVERRIDES = [
    (
        "M01AE", "B01AA", "deconseillee",
        "NSAIDs increase the anticoagulant effect of vitamin K antagonists by displacing "
        "them from plasma protein binding and inhibiting platelet function, raising the "
        "risk of bleeding. Combination should be avoided; if unavoidable, monitor INR closely."
    ),
]


def get_molecule_id(cur, inn: str):
    cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
    row = cur.fetchone()
    return row[0] if row else None


conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)
cur = conn.cursor()

inserted, upgraded, skipped = 0, 0, 0
class_inserted, class_upgraded, class_skipped = 0, 0, 0

# ── Class-level interaction overrides ─────────────────────────────────────────
for atc_a, atc_b, severity, effect in CLASS_OVERRIDES:
    id_a = get_class_id(cur, atc_a)
    id_b = get_class_id(cur, atc_b)

    if not id_a or not id_b:
        print(f"  SKIP class {atc_a}+{atc_b}: class not found in DB")
        class_skipped += 1
        continue

    cur.execute("""
        SELECT id, severity FROM class_interactions
        WHERE (class_a_id = %s AND class_b_id = %s)
           OR (class_a_id = %s AND class_b_id = %s)
    """, (id_a, id_b, id_b, id_a))
    existing = cur.fetchone()

    if existing:
        row_id, existing_sev = existing
        if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(existing_sev or "", 0):
            cur.execute("""
                UPDATE class_interactions
                SET severity = %s, clinical_effect = %s
                WHERE id = %s
            """, (severity, effect, row_id))
            print(f"  UPGRADE class  {atc_a} + {atc_b}: {existing_sev} -> {severity}")
            class_upgraded += 1
        else:
            print(f"  OK class       {atc_a} + {atc_b}: already at {existing_sev}, no change")
            class_skipped += 1
    else:
        cur.execute("""
            INSERT INTO class_interactions (class_a_id, class_b_id, severity, clinical_effect)
            VALUES (%s, %s, %s, %s)
        """, (id_a, id_b, severity, effect))
        print(f"  INSERT class   {atc_a} + {atc_b}: {severity}")
        class_inserted += 1

# ── Molecule-level interaction overrides ──────────────────────────────────────
for inn_a, inn_b, severity, effect in OVERRIDES:
    id_a = get_molecule_id(cur, inn_a)
    id_b = get_molecule_id(cur, inn_b)

    if not id_a or not id_b:
        print(f"  SKIP {inn_a}+{inn_b}: molecule not found in DB")
        skipped += 1
        continue

    # Canonical order: smaller id first
    if id_a > id_b:
        id_a, id_b = id_b, id_a

    cur.execute("""
        SELECT id, severity_ansm, severity_active
        FROM drug_interactions
        WHERE molecule_a_id = %s AND molecule_b_id = %s
    """, (id_a, id_b))
    existing = cur.fetchone()

    if existing:
        row_id, existing_ansm, existing_active = existing
        existing_rank = SEVERITY_RANK.get(existing_active or "", 0)
        curated_rank  = SEVERITY_RANK.get(severity, 0)

        if curated_rank > existing_rank:
            cur.execute("""
                UPDATE drug_interactions
                SET severity_ansm   = %s,
                    severity_active = %s,
                    clinical_effect = %s,
                    source_confidence = 'curated'
                WHERE id = %s
            """, (severity, severity, effect, row_id))
            print(f"  UPGRADE  {inn_a} + {inn_b}: {existing_active} -> {severity}")
            upgraded += 1
        else:
            print(f"  OK       {inn_a} + {inn_b}: already at {existing_active}, no change")
            skipped += 1
    else:
        cur.execute("""
            INSERT INTO drug_interactions
                (molecule_a_id, molecule_b_id,
                 severity_ansm, severity_active,
                 clinical_effect, source_confidence)
            VALUES (%s, %s, %s, %s, %s, 'curated')
        """, (id_a, id_b, severity, severity, effect))
        print(f"  INSERT   {inn_a} + {inn_b}: {severity}")
        inserted += 1

conn.commit()

cur.execute("SELECT COUNT(*) FROM drug_interactions")
total = cur.fetchone()[0]

cur.close()
conn.close()

print(f"\nDone.")
print(f"  Class overrides  — Inserted: {class_inserted}  Upgraded: {class_upgraded}  Skipped: {class_skipped}")
print(f"  Molecule overrides — Inserted: {inserted}  Upgraded: {upgraded}  Skipped: {skipped}")
print(f"  Total drug_interactions: {total}")