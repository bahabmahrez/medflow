import psycopg2
import os
import sys

def main():
    print("Starting manual end-to-end pipeline verification test...")
    
    # Connect to PostgreSQL database
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "medflow"),
            user=os.getenv("POSTGRES_USER", "medflow"),
            password=os.getenv("POSTGRES_PASSWORD", "medflow"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
        )
        cur = conn.cursor()
    except Exception as e:
        print(f"[FAIL] Could not connect to PostgreSQL: {e}")
        sys.exit(1)

    try:
        # 1. Retrieve Trap Patient 1 (Mohamed Ben Ali)
        cur.execute("SELECT id, name FROM patients WHERE is_trap = TRUE AND trap_scenario = 'warfarin_aspirin' LIMIT 1")
        patient = cur.fetchone()
        if not patient:
            print("[FAIL] Trap Patient 1 (warfarin_aspirin) not found in the database. Run generate_patients.py first!")
            sys.exit(1)
        patient_id, patient_name = patient
        print(f"Found patient: {patient_name} (ID: {patient_id})")

        # 2. Get active medications for Patient 1
        cur.execute("""
            SELECT m.inn, am.rxnorm_cui FROM active_medications am
            JOIN drugs d ON d.id = am.drug_id
            JOIN molecules m ON m.id = d.molecule_id
            WHERE am.patient_id = %s
        """, (patient_id,))
        active_meds = cur.fetchall()
        print(f"Active medications: {[med[0] for med in active_meds]}")

        # Ensure patient is on warfarin
        warfarin_active = any(med[0] == "warfarin" for med in active_meds)
        if not warfarin_active:
            print("[FAIL] Patient is not actively taking warfarin.")
            sys.exit(1)

        # 3. Simulate prescription of Aspirin
        prescribed_drug = "aspirin"
        print(f"Simulating prescription of: {prescribed_drug}")

        # Get prescribed drug molecule ID
        cur.execute("SELECT id FROM molecules WHERE inn = %s", (prescribed_drug,))
        prescribed_mol = cur.fetchone()
        if not prescribed_mol:
            print(f"[FAIL] Molecule '{prescribed_drug}' not found in database.")
            sys.exit(1)
        prescribed_mol_id = prescribed_mol[0]

        # 4. Check for drug-drug interactions with active meds
        print("Checking for interactions...")
        interactions_found = 0
        for active_inn, active_cui in active_meds:
            # Get active molecule ID
            cur.execute("SELECT id FROM molecules WHERE inn = %s", (active_inn,))
            active_mol_id = cur.fetchone()[0]

            # Query drug_interactions table
            # Store pairs in consistent order (smaller ID first in schema, but let's check both or check ordering)
            id_a, id_b = min(active_mol_id, prescribed_mol_id), max(active_mol_id, prescribed_mol_id)
            cur.execute("""
                SELECT severity_ansm, severity_active, clinical_effect, management
                FROM drug_interactions
                WHERE molecule_a_id = %s AND molecule_b_id = %s
            """, (id_a, id_b))
            row = cur.fetchone()

            if row:
                severity_ansm, severity_active, clinical_effect, management = row
                print("\n=================== ALERT FOUND ===================")
                print(f"Interaction: {active_inn} + {prescribed_drug}")
                print(f"ANSM Severity: {severity_ansm}")
                print(f"Active Severity: {severity_active}")
                print(f"Clinical Effect: {clinical_effect}")
                print(f"Management: {management}")
                print("===================================================\n")
                interactions_found += 1
                
                # Check assertions
                assert severity_ansm == "deconseillee", f"Expected ANSM severity 'deconseillee', got '{severity_ansm}'"
                assert severity_active == "major", f"Expected active severity 'major', got '{severity_active}'"
                assert "bleeding" in clinical_effect.lower() or "hemorrhage" in clinical_effect.lower(), "Expected bleeding or hemorrhage warning in clinical effect"
                print("[SUCCESS] Assertions passed for warfarin + aspirin interaction.")

        if interactions_found == 0:
            print("[FAIL] No interactions were found between active medications and the prescription.")
            sys.exit(1)

        print("[SUCCESS] Manual end-to-end pipeline verification test PASSED!")

    except AssertionError as ae:
        print(f"[FAIL] Assertion error: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] General error: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
