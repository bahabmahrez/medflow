"""
Drafting the "contact prescriber" message.

When a pharmacist decides to query a prescription, the slow part is writing the
message: restating the patient, the drugs, the finding and why it matters. The
finding already contains all of that, so the interface drafts it and the
pharmacist edits rather than composes.

Pure text generation - no database, no LLM, nothing to hallucinate. Every line
comes from the alert the pharmacist is looking at.
"""
from __future__ import annotations

from datetime import date

_ASK = {
    "do_not_dispense": (
        "Given this, I am holding the dispensation pending your advice. Could you "
        "confirm whether you would like to change the prescription, or advise how "
        "you would like to proceed?"
    ),
    "contact_prescriber": (
        "Could you confirm whether you would like to adjust the prescription, or "
        "whether you are happy for it to proceed with monitoring?"
    ),
    "dispense_with_note": (
        "I intend to dispense with counselling and monitoring advice unless you "
        "would prefer a change."
    ),
}
_DEFAULT_ASK = _ASK["contact_prescriber"]


def _format_dob(dob) -> str:
    if isinstance(dob, date):
        return dob.strftime("%d/%m/%Y")
    return str(dob) if dob else ""


def _patient_line(patient: dict | None) -> str:
    if not patient:
        return "this patient"
    name = patient.get("name") or f"patient #{patient.get('id', '?')}"
    bits = []
    if patient.get("dob"):
        bits.append(f"DOB {_format_dob(patient['dob'])}")
    if patient.get("age") is not None:
        bits.append(f"{patient['age']} years")
    return f"{name} ({', '.join(bits)})" if bits else name


def draft_prescriber_message(
    alert: dict,
    *,
    patient: dict | None = None,
    prescription: list[dict] | None = None,
    pharmacist_name: str | None = None,
) -> str:
    """
    Draft a message to the prescriber about one finding.

    Returns plain text the pharmacist can edit and send. The reasoning chain is
    included because it is what makes the query answerable without the
    prescriber having to re-derive the interaction themselves.
    """
    severity = (alert.get("severity") or "").upper()
    title = alert.get("title") or "a safety finding"
    action = alert.get("recommended_action", "")

    lines: list[str] = []
    lines.append(f"Subject: Prescription query - {_patient_line(patient)}")
    lines.append("")
    lines.append("Dear Doctor,")
    lines.append("")

    rx_names = [e.get("drug") for e in (prescription or []) if e.get("drug")]
    if rx_names:
        lines.append(
            f"Regarding the prescription for {_patient_line(patient)} "
            f"({', '.join(rx_names)}), I would like to raise a safety finding "
            f"before dispensing:"
        )
    else:
        lines.append(
            f"Regarding the prescription for {_patient_line(patient)}, I would "
            f"like to raise a safety finding before dispensing:"
        )
    lines.append("")
    lines.append(f"  {severity} - {title}")
    if alert.get("explanation"):
        lines.append(f"  {alert['explanation']}")
    lines.append("")

    chain = alert.get("reasoning_chain") or []
    if chain:
        lines.append("  Why this was flagged:")
        for i, step in enumerate(chain, 1):
            lines.append(f"    {i}. {step}")
        lines.append("")

    meds = [m.get("inn") for m in (patient or {}).get("active_meds", []) if m.get("inn")]
    if meds:
        lines.append(f"Current medications on file: {', '.join(meds)}.")
        lines.append("")

    memory = alert.get("memory")
    if memory and memory.get("reviewed_ago"):
        note = f" Note recorded at the time: {memory['note']}" if memory.get("note") else ""
        lines.append(
            f"For context, this finding was reviewed {memory['reviewed_ago']} "
            f"({memory.get('decision_label', memory.get('decision', 'reviewed'))})."
            + note
        )
        lines.append("")

    lines.append(_ASK.get(action, _DEFAULT_ASK))
    lines.append("")
    lines.append("Kind regards,")
    lines.append(f"{pharmacist_name or '[Pharmacist]'}")

    return "\n".join(lines)
