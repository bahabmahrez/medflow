"""
Run all 20 graph trap verification scripts against Neo4j.

Each script exits 0 (PASS) or 1 (FAIL).
This runner prints a summary table and exits 1 if any trap fails.

Usage:
    docker compose up -d neo4j
    python run_loaders_graph.py          # populate the graph
    python evaluation/graph_verifications/run_all_graph_traps.py
"""
import subprocess, sys, time, os

TRAPS = [
    ("trap01", "trap01_warfarin_aspirin.py",       "Warfarin + Aspirin (direct DDI)"),
    ("trap02", "trap02_metformin_ckd.py",           "Metformin + CKD contraindication"),
    ("trap03", "trap03_simvastatin_cyp3a4.py",      "Simvastatin + Clarithromycin (CYP3A4 2-hop)"),
    ("trap04", "trap04_penicillin_allergy.py",      "Penicillin allergy -> cephalosporin cross-reactivity"),
    ("trap05", "trap05_serotonin_syndrome.py",      "Fluoxetine + Tramadol (serotonin syndrome)"),
    ("trap06", "trap06_elderly_dose.py",            "Elderly dose context (ciprofloxacin)"),
    ("trap07", "trap07_cyp2c9_overload.py",         "Warfarin + Fluconazole (CYP2C9 strong inhibitor)"),
    ("trap08", "trap08_brand_resolution.py",        "Tahor -> atorvastatin brand resolution"),
    ("trap09", "trap09_warfarin_amiodarone.py",     "Warfarin + Amiodarone (contre_indique)"),
    ("trap10", "trap10_rifampicin_inducer.py",      "Rifampicin CYP2C9 inducer -> subtherapeutic warfarin"),
    ("trap11", "trap11_allopurinol_azathioprine.py","Allopurinol + Azathioprine (xanthine oxidase)"),
    ("trap12", "trap12_tacrolimus_fluconazole.py",  "Tacrolimus + Fluconazole (narrow TI)"),
    ("trap13", "trap13_clopidogrel_omeprazole.py",  "Clopidogrel + Omeprazole (CYP2C19 2-hop)"),
    ("trap14", "trap14_cyp2d6_patient.py",          "CYP2D6 patient-centric traversal"),
    ("trap15", "trap15_nsaid_class_fallback.py",    "NSAID + VKA class-level interaction"),
    ("trap16", "trap16_egfr_lab_only.py",           "Metformin + eGFR lab-only (no CKD ICD code)"),
    ("trap17", "trap17_two_ssri.py",                "Two SSRIs — therapeutic duplication"),
    ("trap18", "trap18_polypharmacy_elderly.py",    "Polypharmacy elderly (>=6 drugs)"),
    ("trap19", "trap19_nsaid_peptic_ulcer.py",      "NSAID + Peptic ulcer contraindication"),
    ("trap20", "trap20_digoxin_amiodarone.py",      "Digoxin + Amiodarone (direct DDI)"),
]

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
RESET = "\033[0m";  BOLD = "\033[1m"

here = os.path.dirname(os.path.abspath(__file__))


def run_trap(script: str):
    path = os.path.join(here, script)
    start = time.time()
    result = subprocess.run(
        [sys.executable, path],
        capture_output=True, text=True,
    )
    elapsed = time.time() - start
    output = (result.stdout.strip() or result.stderr.strip() or "").splitlines()
    first_line = output[0] if output else ""
    return result.returncode, first_line, elapsed


def main():
    print(f"\n{BOLD}MedFlow Graph Trap Verifications — {len(TRAPS)} traps{RESET}\n")
    print(f"{'#':<7} {'Status':<7} {'Time':>6}  {'Description':<48}  Message")
    print("-" * 100)

    passed = failed = 0
    results = []

    for trap_id, script, description in TRAPS:
        rc, message, elapsed = run_trap(script)
        status  = f"{GREEN}PASS{RESET}" if rc == 0 else f"{RED}FAIL{RESET}"
        time_str = f"{elapsed:.2f}s"
        print(f"{trap_id:<7} {status:<14} {time_str:>6}  {description:<48}  {message}")
        if rc == 0:
            passed += 1
        else:
            failed += 1
        results.append((trap_id, rc, message))

    print("\n" + "=" * 100)
    colour = GREEN if failed == 0 else RED
    print(
        f"{colour}{BOLD}Results: {passed}/{len(TRAPS)} passed, {failed} failed{RESET}"
    )

    if failed:
        print(f"\n{RED}Failed traps:{RESET}")
        for tid, rc, msg in results:
            if rc != 0:
                print(f"  {tid}: {msg}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}All graph traps passed.{RESET}")
        print(f"\nNeo4j Browser ->  http://localhost:7474")
        print(
            "Quick check   ->  "
            "MATCH (p:Patient) WHERE p.is_trap = true "
            "RETURN p.trap_scenario, p.name ORDER BY p.patient_id"
        )


if __name__ == "__main__":
    main()
