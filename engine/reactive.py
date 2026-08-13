"""
The reactive engine - the pharmacist's core workflow.

``scan_prescription()`` takes a new prescription plus the patient's current
state and returns one structured **alert report**: every finding the knowledge
graph supports, sorted most-dangerous-first, each with a plain-language
explanation, a recommended action, and the reasoning chain behind it.

Meeting the 2-second clinical budget rests on three things:

1. **Preload** - every drug name in the prescription and the patient's active
   list is resolved in a single round-trip (``resolve_many``), which warms the
   process-wide cache so the checks that follow never re-query for names.
2. **Concurrency** - the independent checks (interactions, CYP competition,
   and the per-drug safety checks) are fanned out across a thread pool. They
   share one pooled Neo4j driver, so parallelism costs no extra connections.
3. **No inference in the hot path** - reasoning chains are composed from graph
   data (see ``engine.alerts``), so a scan never waits on an LLM.

Every run is measured: the report carries ``latency_ms``, a per-stage
breakdown, and a ``within_budget`` flag.
"""
from __future__ import annotations

import atexit
import threading
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from query.interactions import detect_cyp_competition, detect_pairwise_interactions
from query.resolve import resolve_many
from query.safety import (
    check_allergy_conflict,
    check_contraindications,
    check_dose_appropriateness,
    check_therapeutic_duplication,
)

from . import alerts as A

#: Clinical requirement - a pharmacist cannot wait at the counter.
LATENCY_BUDGET_MS = 2000.0

_MAX_WORKERS = 12
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """Process-wide pool, created once - thread startup stays out of the budget."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=_MAX_WORKERS, thread_name_prefix="medflow-scan"
                )
    return _executor


def _shutdown_executor() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False)
            _executor = None


atexit.register(_shutdown_executor)


def _timed(fn, *args, **kwargs):
    """Run *fn*, returning ``(envelope, elapsed_ms)`` and never raising."""
    start = perf_counter()
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # a failed check must not sink the whole scan
        result = {"status": "error", "data": {}, "message": str(exc)}
    return result, (perf_counter() - start) * 1000.0


def _payload(envelope, key, default=None):
    """Pull ``data[key]`` out of a query envelope defensively."""
    if not isinstance(envelope, dict):
        return default if default is not None else []
    return envelope.get("data", {}).get(key, default if default is not None else [])


def scan_prescription(
    prescription: list[dict] | None = None,
    *,
    patient_meds: list[str] | None = None,
    conditions:   list[str] | None = None,
    allergies:    list[str] | None = None,
    age:          int   | None = None,
    weight:       float | None = None,
    labs:         dict  | None = None,
    patient_id:    int | None = None,
    pharmacist_id: int | None = None,
    memory_store=None,
    latency_budget_ms: float = LATENCY_BUDGET_MS,
) -> dict:
    """
    Run the complete safety analysis for one prescription, in one pass.

    Args:
        prescription: ``[{"drug": "clarithromycin", "dose": "500mg"}, ...]``
        patient_meds: the patient's currently active medications (any name form)
        conditions:   patient conditions, free text or ICD-11 codes
        allergies:    patient allergies, e.g. ``["penicillin"]``
        age, weight:  patient demographics used for dose review
        labs:         ``creatinine_umol_L`` / ``egfr`` / ``alt_iu_L`` / ``ast_iu_L``
        patient_id, pharmacist_id: when both are given, findings this pharmacist
                      already reviewed for this patient come back as reminders
                      rather than fresh alerts (Milestone 2 memory)
        memory_store: optional ``memory.MemoryStore`` override, for tests
        latency_budget_ms: budget the run is measured against (default 2000 ms)

    Returns:
        The alert report - see module docstring. Always returns a report;
        backend failures surface in ``warnings`` rather than raising.
    """
    started = perf_counter()

    prescription = prescription or []
    patient_meds = [m for m in (patient_meds or []) if m and m.strip()]
    conditions   = conditions or []
    allergies    = allergies  or []
    labs         = labs       or {}

    entries = [e for e in prescription if e.get("drug")]
    new_names = [e["drug"] for e in entries]

    if not new_names and not patient_meds:
        return _empty_report(
            started, latency_budget_ms,
            message="No prescription drugs or active medications provided.",
            status="error",
        )

    all_names = new_names + patient_meds
    timings: dict[str, float] = {}
    warnings: list[str] = []

    # ── 1. Preload: resolve every name in one round-trip ──────────────────────
    preload_start = perf_counter()
    resolutions = resolve_many(all_names)
    timings["preload_resolve"] = (perf_counter() - preload_start) * 1000.0

    # A backend failure is not the same as an unknown drug. If resolution
    # errored we cannot vouch for anything, so stop here and say so plainly
    # rather than fanning out checks that would each repeat the same timeout
    # and then render a reassuring, empty report.
    backend_errors = sorted({
        (resolutions.get(name) or {}).get("message", "resolution failed")
        for name in all_names
        if (resolutions.get(name) or {}).get("status") == "error"
    })
    if backend_errors:
        return _unavailable_report(
            started, latency_budget_ms, backend_errors, entries, patient_meds,
            timings,
        )

    def _canonical(name: str) -> str:
        env = resolutions.get(name) or {}
        if env.get("status") == "found":
            return env["data"]["canonical"]
        return name

    # Only genuinely not-in-the-graph names land here.
    unresolved = sorted({
        name for name in all_names
        if (resolutions.get(name) or {}).get("status") == "not_found"
    })

    new_inns    = {_canonical(n).lower() for n in new_names}
    active_inns = {_canonical(m).lower() for m in patient_meds}

    # ── 2. Fan out every independent check ───────────────────────────────────
    executor = _get_executor()
    futures: dict[str, object] = {}

    if len(all_names) >= 2:
        futures["interactions"] = executor.submit(
            _timed, detect_pairwise_interactions, all_names
        )
        futures["cyp_competition"] = executor.submit(
            _timed, detect_cyp_competition, all_names
        )

    dose_relevant = bool(labs) or age is not None or any(e.get("dose") for e in entries)

    for position, entry in enumerate(entries):
        drug = entry["drug"]
        if conditions:
            futures[f"contraindications::{position}::{drug}"] = executor.submit(
                _timed, check_contraindications, drug, conditions
            )
        if allergies:
            futures[f"allergy::{position}::{drug}"] = executor.submit(
                _timed, check_allergy_conflict, drug, allergies
            )
        if patient_meds:
            futures[f"duplication::{position}::{drug}"] = executor.submit(
                _timed, check_therapeutic_duplication, drug, patient_meds
            )
        if dose_relevant:
            futures[f"dose::{position}::{drug}"] = executor.submit(
                _timed, check_dose_appropriateness, drug,
                entry.get("dose"), age, weight, labs,
            )

    results: dict[str, dict] = {}
    for key, future in futures.items():
        envelope, elapsed = future.result()
        results[key] = envelope
        timings[key.split("::")[0]] = max(timings.get(key.split("::")[0], 0.0), elapsed)
        if envelope.get("status") == "error":
            warnings.append(f"{key.split('::')[0]}: {envelope.get('message', 'check failed')}")

    # ── 3. Turn findings into alerts ─────────────────────────────────────────
    built: list[dict] = []

    # Direct interactions first, indexed by the unordered drug pair so an
    # enzyme finding about the same pair can be merged into it rather than
    # shown twice.
    by_pair: dict[frozenset, int] = {}
    for i, item in enumerate(_payload(results.get("interactions"), "interactions"), 1):
        alert = A.build_interaction_alert(item, i, new_inns, active_inns)
        pair = frozenset({
            (item.get("drug_a") or "").lower(), (item.get("drug_b") or "").lower()
        })
        by_pair[pair] = len(built)
        built.append(alert)

    for i, item in enumerate(_payload(results.get("cyp_competition"), "competitions"), 1):
        pair = frozenset({
            (item.get("substrate") or "").lower(), (item.get("modulator") or "").lower()
        })
        position = by_pair.get(pair)
        cyp_alert = A.build_cyp_alert(
            item, i, new_inns, active_inns, has_direct_edge=position is not None
        )
        if position is None:
            built.append(cyp_alert)
        else:
            built[position] = A.merge_pair_alerts(built[position], cyp_alert)

    counters = {"ci": 0, "alg": 0, "dup": 0, "dose": 0}
    for key, envelope in results.items():
        kind = key.split("::")[0]
        if kind in ("interactions", "cyp_competition"):
            continue
        drug_label = _canonical(key.split("::", 2)[2]) if "::" in key else ""

        if kind == "contraindications":
            for item in _payload(envelope, "contraindications"):
                counters["ci"] += 1
                built.append(A.build_contraindication_alert(item, drug_label, counters["ci"]))
        elif kind == "allergy":
            for item in _payload(envelope, "conflicts"):
                counters["alg"] += 1
                built.append(A.build_allergy_alert(item, drug_label, counters["alg"]))
        elif kind == "duplication":
            for item in _payload(envelope, "duplicates"):
                counters["dup"] += 1
                built.append(A.build_duplication_alert(item, counters["dup"]))
        elif kind == "dose":
            dose_data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
            for rec in _payload(envelope, "recommendations"):
                counters["dose"] += 1
                built.append(A.build_dose_alert(rec, drug_label, dose_data, counters["dose"]))

    # A drug we could not resolve was never checked - say so plainly.
    for i, name in enumerate(unresolved, 1):
        built.append({
            "id": f"UNK-{i:02d}",
            "type": "unknown_drug",
            "severity": A.MINOR,
            "severity_rank": A.SEVERITY_RANK[A.MINOR],
            "color": A.SEVERITY_COLOR[A.MINOR],
            "title": f"'{name}' is not in the knowledge base",
            "explanation": (
                f"'{name}' could not be matched to a known molecule or brand, so it "
                f"was excluded from every automated check."
            ),
            "reasoning_chain": [
                f"The name '{name}' matched no INN and no brand name in the knowledge base.",
                "No interaction, contraindication, allergy or dose check could run for it.",
                "Absence of an alert for this drug is therefore not evidence of safety.",
                "Recommended handling is to verify this medicine manually before dispensing.",
            ],
            "drugs_involved": [name],
            "recommended_action": A.DISPENSE_WITH_NOTE,
            "action_label": A.ACTION_LABEL[A.DISPENSE_WITH_NOTE],
            "evidence": {"input_name": name},
        })

    ordered = A.sort_alerts(built)

    # ── 4. Memory: soften what this pharmacist has already ruled on ───────────
    # Imported lazily so the engine has no hard dependency on PostgreSQL, and
    # guarded so a memory outage costs the annotations, never the safety scan.
    memory_info: dict | None = None
    if patient_id is not None and pharmacist_id is not None and ordered:
        memory_start = perf_counter()
        try:
            from memory import memory_summary, recall_for_alerts

            ordered = recall_for_alerts(
                ordered, patient_id, pharmacist_id, store=memory_store
            )
            memory_info = memory_summary(ordered)
        except Exception as exc:
            warnings.append(
                f"memory unavailable, showing every finding as new: {exc}"
            )
        timings["memory_recall"] = (perf_counter() - memory_start) * 1000.0

    action = A.overall_action(ordered)
    latency_ms = (perf_counter() - started) * 1000.0

    return {
        "status": "ok",
        "latency_ms": round(latency_ms, 1),
        "latency_budget_ms": latency_budget_ms,
        "within_budget": latency_ms <= latency_budget_ms,
        "summary": {
            "overall_risk":        A.overall_risk(ordered),
            "recommended_action":  action,
            "action_label":        A.ACTION_LABEL.get(action, action),
            "alert_count":         len(ordered),
            "by_severity":         A.severity_counts(ordered),
            "checks_run":          len(futures) + 1,  # + the preload
            "memory":              memory_info,
        },
        "alerts": ordered,
        "patient": {
            "active_med_count": len(patient_meds),
            "active_meds":      patient_meds,
            "conditions":       conditions,
            "allergies":        allergies,
            "age":              age,
            "weight":           weight,
            "labs":             labs,
        },
        "prescription":     entries,
        "unresolved_drugs": unresolved,
        "warnings":         warnings,
        "timings_ms":       {k: round(v, 1) for k, v in timings.items()},
    }


def _unavailable_report(
    started: float,
    budget: float,
    errors: list[str],
    entries: list[dict],
    patient_meds: list[str],
    timings: dict[str, float],
) -> dict:
    """
    The knowledge graph could not be reached - report that, loudly.

    The dangerous failure mode here is a clean-looking report with no alerts,
    which reads as "nothing wrong". This says the opposite: nothing was checked.
    """
    latency_ms = (perf_counter() - started) * 1000.0
    return {
        "status": "unavailable",
        "latency_ms": round(latency_ms, 1),
        "latency_budget_ms": budget,
        "within_budget": latency_ms <= budget,
        "summary": {
            "overall_risk":       "UNKNOWN",
            "recommended_action": A.CONTACT_PRESCRIBER,
            "action_label":       "Knowledge base unavailable - verify manually",
            "alert_count":        0,
            "by_severity":        A.severity_counts([]),
            "checks_run":         0,
        },
        "alerts": [],
        "patient": {"active_med_count": len(patient_meds), "active_meds": patient_meds},
        "prescription": entries,
        "unresolved_drugs": [],
        "warnings": [
            "The knowledge graph is unreachable - NO safety check was performed. "
            "This prescription has not been screened; verify it manually.",
            *errors,
        ],
        "timings_ms": {k: round(v, 1) for k, v in timings.items()},
    }


def _empty_report(started: float, budget: float, *, message: str, status: str) -> dict:
    latency_ms = (perf_counter() - started) * 1000.0
    return {
        "status": status,
        "latency_ms": round(latency_ms, 1),
        "latency_budget_ms": budget,
        "within_budget": latency_ms <= budget,
        "summary": {
            "overall_risk":       "NONE",
            "recommended_action": A.DISPENSE,
            "action_label":       A.ACTION_LABEL[A.DISPENSE],
            "alert_count":        0,
            "by_severity":        A.severity_counts([]),
            "checks_run":         0,
        },
        "alerts": [],
        "patient": {"active_med_count": 0, "active_meds": []},
        "prescription": [],
        "unresolved_drugs": [],
        "warnings": [message],
        "timings_ms": {},
    }
