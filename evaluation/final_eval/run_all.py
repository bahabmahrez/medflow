"""
Milestone 4 - the complete final assessment, in one run.

Executes every measurable part of the evaluation and prints a single verdict.
The parts that need a human (the pharmacist session) or a paid API (the live
agent suites) are reported as "not run here" rather than silently skipped, so
the summary never overstates what was actually checked.

    python -m evaluation.final_eval.run_all           # full
    python -m evaluation.final_eval.run_all --quick   # skip load testing

Requires Neo4j + PostgreSQL (docker compose up -d).
Exits non-zero if any executed suite fails.
"""
from __future__ import annotations

import argparse
import sys
from time import perf_counter

from . import latency_load, severity_accuracy, specificity, trap_sensitivity

SUITES = [
    ("Sensitivity (trap patients)", "a missed danger is a patient harmed"),
    ("Specificity (safe cases)",    "crying wolf causes alert fatigue"),
    ("Severity accuracy",           "the grade drives the pharmacist's action"),
    ("Latency under load",          "the 2-second promise must hold concurrently"),
]


def run(quick: bool = False) -> int:
    started = perf_counter()

    print()
    print("#" * 78)
    print("#  MedFlow - Milestone 4 Final Evaluation")
    print("#" * 78)
    print()
    print("  Suites and why each exists:")
    for name, why in SUITES:
        print(f"    - {name:<30} {why}")
    if quick:
        print("    (--quick: latency under load skipped)")

    results: dict[str, int] = {}

    results["sensitivity"] = trap_sensitivity.run()
    results["specificity"] = specificity.run()
    results["severity"] = severity_accuracy.run()
    if not quick:
        results["latency_load"] = latency_load.run([1, 2, 4, 8], 40, 2000.0)

    elapsed = perf_counter() - started
    failed = [name for name, code in results.items() if code != 0]

    print()
    print("#" * 78)
    print("#  FINAL VERDICT")
    print("#" * 78)
    for name, code in results.items():
        print(f"    {name:<20} {'PASS' if code == 0 else 'FAIL'}")

    print()
    print("  Not run here (require a human or a live API):")
    print("    - Adversarial battery   python -m evaluation.agent_eval.runner --tier adversarial")
    print("    - GraphRAG evaluation   python -m evaluation.llm_eval.runner")
    print("    - Real pharmacist test  docs/PHARMACIST_SESSION_KIT.md")

    print()
    print(f"  completed in {elapsed:.1f}s")
    if failed:
        print(f"  RESULT: FAIL ({', '.join(failed)})")
        print("#" * 78)
        return 1
    print("  RESULT: PASS - every executed suite met its bar.")
    print("#" * 78)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full final evaluation")
    parser.add_argument("--quick", action="store_true", help="skip load testing")
    args = parser.parse_args()
    sys.exit(run(quick=args.quick))


if __name__ == "__main__":
    main()
