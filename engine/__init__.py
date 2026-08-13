"""
MedFlow reactive engine (Week 6) - the pharmacist's scan-a-prescription flow.

Usage:
    from engine import scan_prescription

    report = scan_prescription(
        [{"drug": "clarithromycin", "dose": "500mg"}],
        patient_meds=["simvastatin", "warfarin"],
    )
    print(report["summary"]["recommended_action"], report["latency_ms"])
    for alert in report["alerts"]:
        print(alert["severity"], alert["title"])
"""
from .alerts import (
    ACTION_LABEL,
    CONTACT_PRESCRIBER,
    CONTRAINDICATED,
    DISPENSE,
    DISPENSE_WITH_NOTE,
    DO_NOT_DISPENSE,
    MAJOR,
    MINOR,
    MODERATE,
    SEVERITY_COLOR,
    SEVERITY_RANK,
)
from .reactive import LATENCY_BUDGET_MS, scan_prescription

__all__ = [
    "scan_prescription",
    "LATENCY_BUDGET_MS",
    "CONTRAINDICATED", "MAJOR", "MODERATE", "MINOR",
    "DO_NOT_DISPENSE", "CONTACT_PRESCRIBER", "DISPENSE_WITH_NOTE", "DISPENSE",
    "ACTION_LABEL", "SEVERITY_RANK", "SEVERITY_COLOR",
]
