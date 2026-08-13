"""
Latency benchmark for the reactive engine - proves the 2-second requirement.

Runs a set of representative pharmacy scenarios (including the trap patients
and a heavy polypharmacy case) repeatedly, then reports cold/warm latency
percentiles against the budget.

Usage:
    python -m engine.benchmark                 # 5 runs per scenario
    python -m engine.benchmark --runs 20
    python -m engine.benchmark --budget 2000

Requires a running Neo4j (``docker compose up -d``).
Exits non-zero if p95 for any scenario exceeds the budget.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from time import perf_counter

from query.resolve import clear_resolve_cache, resolve_cache_size

from .reactive import LATENCY_BUDGET_MS, scan_prescription

SCENARIOS: list[dict] = [
    {
        "name": "simple - single new drug, no context",
        "kwargs": {"prescription": [{"drug": "warfarin"}]},
    },
    {
        "name": "trap: warfarin + aspirin (direct interaction)",
        "kwargs": {
            "prescription": [{"drug": "aspirin", "dose": "100mg"}],
            "patient_meds": ["warfarin"],
        },
    },
    {
        "name": "trap: simvastatin + clarithromycin (CYP3A4, no direct edge)",
        "kwargs": {
            "prescription": [{"drug": "clarithromycin", "dose": "500mg"}],
            "patient_meds": ["simvastatin", "warfarin"],
        },
    },
    {
        "name": "trap: penicillin allergy (cross-reactivity)",
        "kwargs": {
            "prescription": [{"drug": "amoxicillin", "dose": "1g"}],
            "patient_meds": ["metformin"],
            "allergies": ["penicillin"],
        },
    },
    {
        "name": "trap: elderly + renal impairment (dose review)",
        "kwargs": {
            "prescription": [{"drug": "ciprofloxacin", "dose": "500mg"}],
            "patient_meds": ["metformin", "ramipril"],
            "age": 82,
            "labs": {"creatinine_umol_L": 210},
        },
    },
    {
        "name": "trap: therapeutic duplication (brand vs INN)",
        "kwargs": {
            "prescription": [{"drug": "atorvastatin", "dose": "20mg"}],
            "patient_meds": ["Tahor", "metformin"],
        },
    },
    {
        "name": "heavy: polypharmacy, 8 active meds + 2 new + full context",
        "kwargs": {
            "prescription": [
                {"drug": "clarithromycin", "dose": "500mg"},
                {"drug": "ibuprofen", "dose": "400mg"},
            ],
            "patient_meds": [
                "warfarin", "simvastatin", "metformin", "omeprazole",
                "amiodarone", "ramipril", "aspirin", "furosemide",
            ],
            "conditions": ["CKD stage 3", "atrial fibrillation"],
            "allergies": ["penicillin"],
            "age": 78,
            "labs": {"creatinine_umol_L": 165, "egfr": 38},
        },
    },
]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lower, upper = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def run_benchmark(runs: int = 5, budget_ms: float = LATENCY_BUDGET_MS) -> int:
    print()
    print("=" * 78)
    print(f"  MedFlow Reactive Engine - latency benchmark  (budget {budget_ms:.0f} ms)")
    print("=" * 78)

    # Cold run first: empty cache, first connection - the realistic worst case.
    clear_resolve_cache()
    cold_start = perf_counter()
    first = scan_prescription(**SCENARIOS[0]["kwargs"])
    cold_ms = (perf_counter() - cold_start) * 1000.0

    if first.get("warnings") and first.get("summary", {}).get("checks_run", 0) == 0:
        print("\n  ERROR: the engine could not reach the knowledge graph.")
        for warning in first["warnings"]:
            print(f"    - {warning}")
        print("\n  Start the databases first:  docker compose up -d\n")
        return 2

    print(f"\n  Cold start (empty cache, first connection): {cold_ms:8.1f} ms")
    print(f"  {'Scenario':<52}{'p50':>8}{'p95':>8}{'max':>8}")
    print("  " + "-" * 74)

    failures: list[str] = []
    all_latencies: list[float] = []

    for scenario in SCENARIOS:
        latencies: list[float] = []
        alert_count = 0
        for _ in range(runs):
            report = scan_prescription(**scenario["kwargs"])
            latencies.append(report["latency_ms"])
            alert_count = report["summary"]["alert_count"]

        all_latencies.extend(latencies)
        p50 = _percentile(latencies, 0.50)
        p95 = _percentile(latencies, 0.95)
        worst = max(latencies)
        flag = "" if p95 <= budget_ms else "  <-- OVER BUDGET"
        if p95 > budget_ms:
            failures.append(scenario["name"])

        label = scenario["name"][:50]
        print(f"  {label:<52}{p50:>8.1f}{p95:>8.1f}{worst:>8.1f}{flag}")
        print(f"    {'':<50}({alert_count} alert(s))")

    print("  " + "-" * 74)
    overall_p95 = _percentile(all_latencies, 0.95)
    overall_max = max(all_latencies) if all_latencies else 0.0
    print(f"  {'ALL SCENARIOS':<52}{_percentile(all_latencies, 0.5):>8.1f}"
          f"{overall_p95:>8.1f}{overall_max:>8.1f}")
    print(f"\n  Runs per scenario: {runs}   |   cached drug names: {resolve_cache_size()}")

    print()
    if failures:
        print(f"  RESULT: FAIL - {len(failures)} scenario(s) exceeded {budget_ms:.0f} ms p95:")
        for name in failures:
            print(f"    - {name}")
        print("=" * 78)
        return 1

    print(f"  RESULT: PASS - every scenario met the {budget_ms:.0f} ms budget "
          f"(worst observed {overall_max:.1f} ms).")
    print("=" * 78)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the MedFlow reactive engine")
    parser.add_argument("--runs", type=int, default=5, help="runs per scenario (default 5)")
    parser.add_argument("--budget", type=float, default=LATENCY_BUDGET_MS,
                        help="latency budget in ms (default 2000)")
    args = parser.parse_args()
    sys.exit(run_benchmark(runs=args.runs, budget_ms=args.budget))


if __name__ == "__main__":
    main()
