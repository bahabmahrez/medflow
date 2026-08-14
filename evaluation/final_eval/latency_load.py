"""
Milestone 4 - LATENCY UNDER LOAD.

The 2-second requirement is a promise made to a pharmacist with a patient at the
counter, and a promise that only holds on an idle machine is not worth much. A
real pharmacy has several terminals; a hospital dispensary has more.

This drives concurrent scans through the engine and reports the tail, because
the tail is what people actually experience: p95 and p99, not the mean. The
worst case is the heavy polypharmacy scan, so that is what gets loaded.

Usage:
    python -m evaluation.final_eval.latency_load
    python -m evaluation.final_eval.latency_load --workers 8 --scans 200

Exits non-zero if p99 breaches the budget at any tested concurrency.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from engine import scan_prescription
from engine.reactive import LATENCY_BUDGET_MS

#: The heaviest realistic scan: 10 drugs, full patient context.
HEAVY = {
    "prescription": [
        {"drug": "clarithromycin", "dose": "500mg"},
        {"drug": "ibuprofen", "dose": "400mg"},
    ],
    "patient_meds": [
        "warfarin", "simvastatin", "metformin", "omeprazole",
        "amiodarone", "ramipril", "aspirin", "furosemide",
    ],
    "conditions": ["Chronic kidney disease stage 4", "Atrial fibrillation"],
    "allergies": ["penicillin"],
    "age": 78,
    "labs": {"creatinine_umol_L": 165, "egfr": 38},
}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _one_scan() -> float:
    started = perf_counter()
    scan_prescription(**HEAVY)
    return (perf_counter() - started) * 1000.0


def run_at(workers: int, scans: int) -> dict:
    """Drive *scans* scans through *workers* concurrent threads."""
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        latencies = list(pool.map(lambda _: _one_scan(), range(scans)))
    wall = perf_counter() - started

    return {
        "workers": workers,
        "scans": scans,
        "p50": _percentile(latencies, 0.50),
        "p95": _percentile(latencies, 0.95),
        "p99": _percentile(latencies, 0.99),
        "max": max(latencies),
        "throughput": scans / wall if wall else 0.0,
    }


def run(workers_list: list[int], scans: int, budget_ms: float) -> int:
    print()
    print("=" * 78)
    print(f"  MedFlow - Latency Under Load  (budget {budget_ms:.0f} ms, heavy 10-drug scan)")
    print("=" * 78)
    print()

    # Warm the caches first: a cold process is measured separately by
    # engine.benchmark, and mixing the two would misrepresent both.
    scan_prescription(**HEAVY)

    print(f"  {'concurrent':<12}{'scans':>7}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}"
          f"{'scans/s':>10}")
    print("  " + "-" * 74)

    breaches: list[str] = []
    for workers in workers_list:
        row = run_at(workers, scans)
        flag = "" if row["p99"] <= budget_ms else "  <-- OVER"
        if row["p99"] > budget_ms:
            breaches.append(f"{workers} workers: p99 {row['p99']:.0f} ms")
        print(f"  {workers:<12}{row['scans']:>7}{row['p50']:>9.1f}{row['p95']:>9.1f}"
              f"{row['p99']:>9.1f}{row['max']:>9.1f}{row['throughput']:>10.1f}{flag}")

    print("  " + "-" * 74)
    print()
    if breaches:
        print("  RESULT: FAIL - the budget breaks under load:")
        for breach in breaches:
            print(f"    - {breach}")
        print("=" * 78)
        return 1
    print(f"  RESULT: PASS - p99 stayed within {budget_ms:.0f} ms at every concurrency tested.")
    print("=" * 78)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency under concurrent load")
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8],
                        help="concurrency levels to test (default 1 2 4 8)")
    parser.add_argument("--scans", type=int, default=40, help="scans per level")
    parser.add_argument("--budget", type=float, default=LATENCY_BUDGET_MS)
    args = parser.parse_args()
    sys.exit(run(args.workers, args.scans, args.budget))


if __name__ == "__main__":
    main()
