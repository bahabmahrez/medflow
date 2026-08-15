# End-to-End Pipeline Test — Trap Patient 1
# Warfarin + Aspirin interaction
# Run after DB is seeded: python evaluation/e2e_test.py

import pytest
import psycopg2
import os

pytestmark = pytest.mark.live


def main():
    conn = psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "medflow"),
        user=os.getenv("POSTGRES_USER", "medflow"),
        password=os.getenv("POSTGRES_PASSWORD", "medflow"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
    )
    cur = conn.cursor()

    # 1. Pull Trap Patient 1's active medications
    cur.execute("""
        SELECT m.inn, am.dose_mg, am.frequency
        FROM active_medications am
        JOIN drugs d ON d.id = am.drug_id
        JOIN molecules m ON m.id = d.molecule_id
        JOIN patients p ON p.id = am.patient_id
        WHERE p.trap_scenario = 'warfarin_aspirin'
    """)
    meds = cur.fetchall()
    print("Active meds:", meds)
    assert any(r[0] == 'warfarin' for r in meds), "FAIL: warfarin not in active meds"

    # 2. Query interaction for warfarin-aspirin
    cur.execute("""
        SELECT di.severity_active, di.clinical_effect, di.management
        FROM drug_interactions di
        JOIN molecules ma ON ma.id = di.molecule_a_id
        JOIN molecules mb ON mb.id = di.molecule_b_id
        WHERE (ma.inn = 'warfarin' AND mb.inn = 'aspirin')
           OR (ma.inn = 'aspirin'  AND mb.inn = 'warfarin')
    """)
    result = cur.fetchone()
    assert result is not None, "FAIL: warfarin-aspirin interaction not found in DB"
    severity, effect, management = result
    assert severity in ('contre-indique', 'contre-indiqué', 'major', 'deconseillee', 'déconseillée'), f"FAIL: unexpected severity '{severity}'"
    assert effect and effect.strip(), "FAIL: clinical effect is empty"
    assert management and management.strip(), "FAIL: management recommendation is empty"

    print(f"PASS  severity    : {severity}")
    print(f"      effect      : {effect}")
    print(f"      management  : {management}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
