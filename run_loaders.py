"""
Run all MedFlow data loaders in the correct order.
Stops immediately if any loader fails.
"""

import subprocess
import sys
import time

LOADERS = [
    ("Molecules (RxNorm + ChEMBL)",       "knowledge_base/DB_loaders/load_rxnorm_chembl.py"),
    ("Drugs, contraindications, allergies","knowledge_base/DB_loaders/load_drugs_contraindications.py"),
    ("PCT Tunisian brand names",           "knowledge_base/DB_loaders/load_pct_brands.py"),
    ("ANSM interaction pairs",             "knowledge_base/DB_loaders/load_ansm_interactions.py"),
    ("FDA priority interaction pairs",     "knowledge_base/DB_loaders/load_priority_interactions.py"),
    ("CYP enzyme relationships",           "knowledge_base/DB_loaders/load_cyp_flockhart.py"),
    ("Drug classes + class interactions",  "knowledge_base/DB_loaders/load_drug_classes.py"),
    ("Curated high-risk overrides",        "knowledge_base/DB_loaders/load_curated_overrides.py"),
    ("Adverse effects (OpenFDA)",          "knowledge_base/DB_loaders/load_adverse_effects.py"),
    ("Molecular targets (ChEMBL)",         "knowledge_base/DB_loaders/load_molecular_targets.py"),
    ("Drug indications (treats)",          "knowledge_base/DB_loaders/load_treats.py"),
    ("Synthetic patients",                 "patients/synthetic/load_patients.py"),
]

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def main():
    total = len(LOADERS)
    print(f"{BOLD}MedFlow loader pipeline — {total} steps{RESET}\n")

    for i, (label, script) in enumerate(LOADERS, 1):
        print(f"{BOLD}[{i}/{total}] {label}{RESET}")
        print(f"        {script}")

        start = time.time()
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - start

        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"        {line}")

        if result.returncode != 0:
            print(f"\n{RED}FAILED{RESET} after {elapsed:.1f}s")
            if result.stderr.strip():
                print(f"{RED}{result.stderr.strip()}{RESET}")
            print(f"\n{RED}Pipeline stopped at step {i}/{total}.{RESET}")
            print("Fix the error above, then re-run.")
            sys.exit(1)

        print(f"        {GREEN}OK{RESET}  ({elapsed:.1f}s)\n")

    print(f"{GREEN}{BOLD}All {total} loaders completed successfully.{RESET}")

if __name__ == "__main__":
    main()
