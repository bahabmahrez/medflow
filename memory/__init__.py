"""
MedFlow memory module (Week 6, Milestone 2).

The Memory box of the reference architecture: the agent remembers what a
pharmacist already decided about a patient, so a finding they reviewed last
week arrives as a reminder rather than a fresh red alert.

Usage:
    from memory import MemoryStore, recall_for_alerts

    store = MemoryStore()
    store.init_schema()                                   # once
    pid = store.get_or_create_pharmacist("ph-042", "A. Ben Salah")

    report["alerts"] = recall_for_alerts(report["alerts"], patient_id=7,
                                         pharmacist_id=pid, store=store)

    store.record_decision(7, pid, report["alerts"][0], "acknowledged",
                          note="Prescriber confirmed, INR monitored weekly.")
"""
from .fingerprint import fingerprint
from .recall import (
    DECISION_LABEL,
    DEFAULT_WINDOW_DAYS,
    STATUS_NEW,
    STATUS_REMINDER,
    apply_memory,
    memory_summary,
)
from .store import DECISIONS, MemoryStore

__all__ = [
    "MemoryStore", "DECISIONS", "fingerprint",
    "apply_memory", "memory_summary", "recall_for_alerts",
    "STATUS_NEW", "STATUS_REMINDER", "DECISION_LABEL", "DEFAULT_WINDOW_DAYS",
]


def recall_for_alerts(
    alerts: list[dict],
    patient_id: int,
    pharmacist_id: int,
    *,
    store: "MemoryStore | None" = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    now=None,
) -> list[dict]:
    """
    Annotate *alerts* with this pharmacist's past decisions for this patient.

    One database round-trip: every fingerprint on screen is looked up at once.
    """
    if not alerts:
        return alerts
    store = store or MemoryStore()
    fingerprints = [fingerprint(alert) for alert in alerts]
    memories = store.recall(patient_id, pharmacist_id, fingerprints)
    return apply_memory(
        alerts, memories, fingerprint_of=fingerprint,
        window_days=window_days, now=now,
    )
