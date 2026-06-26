"""
Run all MedFlow graph loaders in the correct order.
Stops immediately if any loader fails.

Usage:
    docker compose up -d neo4j
    python db/graph/init_graph.py      # schema constraints + indexes
    python run_loaders_graph.py        # populate the graph
"""
import subprocess, sys, time

LOADERS = [
    ("Molecules (RxNorm + ChEMBL)",        "knowledge_base/graph_loaders/load_molecules.py"),
    ("Drugs, contraindications, allergies","knowledge_base/graph_loaders/load_drugs_contraindications.py"),
    ("PCT Tunisian brand names",           "knowledge_base/graph_loaders/load_pct_brands.py"),
    ("ANSM interaction pairs",             "knowledge_base/graph_loaders/load_ansm_interactions.py"),
    ("FDA priority interaction pairs",     "knowledge_base/graph_loaders/load_priority_interactions.py"),
    ("CYP enzyme relationships",           "knowledge_base/graph_loaders/load_cyp.py"),
    ("Drug classes + class interactions",  "knowledge_base/graph_loaders/load_drug_classes.py"),
    ("Curated high-risk overrides",        "knowledge_base/graph_loaders/load_curated_overrides.py"),
    ("Adverse effects (OpenFDA)",          "knowledge_base/graph_loaders/load_adverse_effects.py"),
    ("Molecular targets (ChEMBL)",         "knowledge_base/graph_loaders/load_molecular_targets.py"),
    ("Drug indications (treats)",          "knowledge_base/graph_loaders/load_treats.py"),
    ("Synthetic patients",                 "patients/synthetic/load_patients_graph.py"),
]

GREEN = "\033[92m"; RED = "\033[91m"; RESET = "\033[0m"; BOLD = "\033[1m"


def main():
    total = len(LOADERS)
    print(f"{BOLD}MedFlow graph loader pipeline — {total} steps{RESET}\n")

    for i, (label, script) in enumerate(LOADERS, 1):
        print(f"{BOLD}[{i}/{total}] {label}{RESET}")
        print(f"        {script}")

        start  = time.time()
        result = subprocess.run([sys.executable, script], capture_output=True, text=True)
        elapsed = time.time() - start

        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"        {line}")

        if result.returncode != 0:
            print(f"\n{RED}FAILED{RESET} after {elapsed:.1f}s")
            if result.stderr.strip():
                print(f"{RED}{result.stderr.strip()}{RESET}")
            print(f"\n{RED}Pipeline stopped at step {i}/{total}.{RESET}")
            sys.exit(1)

        print(f"        {GREEN}OK{RESET}  ({elapsed:.1f}s)\n")

    print(f"{GREEN}{BOLD}All {total} loaders completed successfully.{RESET}")
    print(f"\nNeo4j Browser  ->  http://localhost:7474")
    print(f"Quick check    ->  MATCH (n) RETURN labels(n)[0] AS label, count(n) ORDER BY count(n) DESC")


if __name__ == "__main__":
    main()
