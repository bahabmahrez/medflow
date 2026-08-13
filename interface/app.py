"""
MedFlow - the pharmacist's scan screen (Week 6, Milestone 3).

Run it with:

    docker compose up -d
    streamlit run interface/app.py

One screen, one job: type or scan a prescription, see everything the knowledge
graph knows about it against this patient, with the dangerous finding first.

Layout decisions, all in service of "usable at a counter":

* the patient's active medications sit **beside** the prescription box, because
  a pharmacist judging an interaction needs both in view at once;
* the verdict is a single coloured banner at the top - action first, detail
  after, so the eye lands on "DO NOT DISPENSE" before it lands on anything else;
* findings are ordered by severity and colour-coded red / orange / yellow;
* the reasoning chain is one click away, collapsed by default, so the screen
  stays scannable but the evidence is never more than a click from the claim;
* "no issues found" is a calm green panel, not an empty screen - silence should
  look like a considered answer, not a failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Allow `streamlit run interface/app.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import scan_prescription                       # noqa: E402
from interface.patient_data import (                       # noqa: E402
    list_patients,
    load_patient,
    parse_prescription,
    to_scan_kwargs,
)
from interface.prescriber import draft_prescriber_message  # noqa: E402
from memory import DECISIONS, MemoryStore                  # noqa: E402

st.set_page_config(page_title="MedFlow - Prescription Safety Check",
                   page_icon="Rx", layout="wide")

# Red / orange / yellow as specified; blue for informational findings.
SEVERITY_STYLE = {
    "contraindicated": ("#c0392b", "#fdedec", "CONTRAINDICATED"),
    "major":           ("#e67e22", "#fdf2e9", "MAJOR"),
    "moderate":        ("#f1c40f", "#fef9e7", "MODERATE"),
    "minor":           ("#2980b9", "#eaf2f8", "MINOR"),
}
ACTION_STYLE = {
    "do_not_dispense":    ("#c0392b", "DO NOT DISPENSE"),
    "contact_prescriber": ("#e67e22", "CONTACT PRESCRIBER"),
    "dispense_with_note": ("#f1c40f", "DISPENSE WITH NOTE"),
    "dispense":           ("#27ae60", "DISPENSE"),
}

DECISION_HELP = {
    "acknowledged":         "Reviewed, risk accepted, dispensing as written.",
    "overridden":           "Dispensing despite the alert (record why).",
    "prescriber_contacted": "Escalated to the prescriber and resolved.",
    "not_dispensed":        "Refused to dispense.",
    "dismissed":            "Not applicable to this patient.",
}


# ── Cached resources ──────────────────────────────────────────────────────────

@st.cache_resource
def get_store() -> MemoryStore:
    return MemoryStore()


@st.cache_data(ttl=300)
def get_patients() -> list[dict]:
    return list_patients()


@st.cache_data(ttl=60)
def get_patient(patient_id: int) -> dict | None:
    return load_patient(patient_id)


# ── Small render helpers ──────────────────────────────────────────────────────

def banner(color: str, headline: str, detail: str) -> None:
    st.markdown(
        f"""
        <div style="background:{color};color:#fff;padding:14px 18px;
                    border-radius:8px;margin:6px 0 14px 0;">
          <div style="font-size:1.5rem;font-weight:700;letter-spacing:.5px;">{headline}</div>
          <div style="opacity:.92;font-size:.95rem;margin-top:2px;">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def alert_header(alert: dict) -> None:
    border, tint, label = SEVERITY_STYLE.get(
        alert.get("severity", ""), ("#7f8c8d", "#f4f6f6", alert.get("severity", "").upper())
    )
    status = alert.get("status", "new")
    chip = (
        '<span style="background:#ecf0f1;color:#566573;padding:2px 8px;'
        'border-radius:10px;font-size:.72rem;margin-left:8px;">ALREADY REVIEWED</span>'
        if status == "reminder" else
        '<span style="background:#34495e;color:#fff;padding:2px 8px;'
        'border-radius:10px;font-size:.72rem;margin-left:8px;">NEW</span>'
    )
    st.markdown(
        f"""
        <div style="border-left:6px solid {border};background:{tint};
                    padding:10px 14px;border-radius:0 6px 6px 0;margin-bottom:6px;">
          <span style="color:{border};font-weight:700;font-size:.78rem;
                       letter-spacing:.6px;">{label}</span>{chip}
          <div style="font-size:1.06rem;font-weight:600;color:#212f3d;margin-top:2px;">
            {alert.get('title', '')}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def patient_panel(patient: dict) -> None:
    """The context column - what the pharmacist needs in view while judging."""
    st.subheader(patient.get("name") or f"Patient #{patient.get('id')}")
    bits = [b for b in (
        f"{patient['age']} years" if patient.get("age") is not None else None,
        patient.get("sex"),
        f"{float(patient['weight_kg']):.0f} kg" if patient.get("weight_kg") else None,
    ) if b]
    st.caption(" · ".join(bits) if bits else "No demographics on file")
    if patient.get("is_trap"):
        st.caption(f"Test patient - scenario: {patient.get('trap_scenario')}")

    meds = patient.get("active_meds", [])
    st.markdown(f"**Active medications ({len(meds)})**")
    if meds:
        for med in meds:
            dose = f" {med['dose_mg']:g} mg" if med.get("dose_mg") else ""
            freq = f", {med['frequency']}" if med.get("frequency") else ""
            brand = f" ({med['brand_name']})" if med.get("brand_name") else ""
            st.markdown(f"- **{med['inn']}**{brand}{dose}{freq}")
    else:
        st.caption("None recorded")

    allergies = patient.get("allergies", [])
    st.markdown(f"**Allergies ({len(allergies)})**")
    if allergies:
        for a in allergies:
            reaction = f" - {a['reaction_type']}" if a.get("reaction_type") else ""
            st.markdown(f"- :red[**{a['allergy']}**]{reaction}")
    else:
        st.caption("None recorded")

    conditions = patient.get("conditions", [])
    st.markdown(f"**Conditions ({len(conditions)})**")
    if conditions:
        for c in conditions:
            code = f" ({c['icd11_code']})" if c.get("icd11_code") else ""
            st.markdown(f"- {c['condition_name']}{code}")
    else:
        st.caption("None recorded")

    labs = patient.get("lab_results", [])
    if labs:
        st.markdown("**Recent labs**")
        for lab in labs:
            st.markdown(f"- {lab['test_name']}: **{lab['value']:g}** {lab.get('unit') or ''}")


# ── Sidebar: who is scanning, and for whom ────────────────────────────────────

st.sidebar.title("MedFlow")
st.sidebar.caption("Prescription safety check")

pharmacist_code = st.sidebar.text_input(
    "Pharmacist code", value=st.session_state.get("pharmacist_code", ""),
    placeholder="e.g. ph-042",
    help="Decisions are remembered per pharmacist - your colleague still sees "
         "every finding at full strength.",
)
st.session_state["pharmacist_code"] = pharmacist_code

pharmacist_id = None
if pharmacist_code.strip():
    try:
        pharmacist_id = get_store().get_or_create_pharmacist(pharmacist_code.strip())
        st.sidebar.caption(f"Memory active (pharmacist #{pharmacist_id})")
    except Exception as exc:
        st.sidebar.warning(f"Memory unavailable: {exc}")
else:
    st.sidebar.caption("Enter a code to enable memory of past decisions.")

try:
    patients = get_patients()
except Exception as exc:
    st.error(
        f"Cannot reach the patient database: {exc}\n\n"
        "Start the databases with `docker compose up -d`."
    )
    st.stop()

if not patients:
    st.warning("No patients loaded. Run the patient loaders first.")
    st.stop()


def _label(p: dict) -> str:
    flag = "[test] " if p.get("is_trap") else ""
    age = f", {p['age']}y" if p.get("age") is not None else ""
    return f"{flag}{p['name']}{age} - {p['active_med_count']} active med(s)"


selected = st.sidebar.selectbox(
    "Patient", options=patients, format_func=_label,
    help="Test patients reproduce the known trap scenarios.",
)

st.sidebar.divider()
st.sidebar.caption(
    "Findings are ordered most dangerous first. Everything shown comes from the "
    "knowledge graph - the reasoning chain under each finding is its evidence."
)

patient = get_patient(selected["id"]) if selected else None
if patient is None:
    st.error("Could not load that patient.")
    st.stop()


# ── Main screen ───────────────────────────────────────────────────────────────

st.title("Prescription safety check")

left, right = st.columns([2, 1], gap="large")

with right:
    patient_panel(patient)

with left:
    st.markdown("**New prescription**")
    text = st.text_area(
        "New prescription", height=132, label_visibility="collapsed",
        placeholder="One medicine per line, dose optional:\n\n"
                    "clarithromycin 500mg\nibuprofen, 400mg\nTahor",
        key="prescription_text",
        help="Type, paste, or scan. A barcode scanner that types the name and "
             "presses Enter works as-is.",
    )
    entries = parse_prescription(text)
    if entries:
        st.caption("Reading: " + ", ".join(
            f"{e['drug']}{(' ' + e['dose']) if e['dose'] else ''}" for e in entries
        ))

    scan_clicked = st.button("Check prescription", type="primary",
                             use_container_width=True, disabled=not entries)

if scan_clicked:
    with st.spinner("Checking..."):
        report = scan_prescription(
            entries,
            patient_id=patient["id"],
            pharmacist_id=pharmacist_id,
            memory_store=get_store() if pharmacist_id else None,
            **to_scan_kwargs(patient),
        )
    st.session_state["report"] = report
    st.session_state["report_patient_id"] = patient["id"]
    st.session_state.pop("draft", None)

    # Log what was screened and shown. Never let logging break the screen.
    if pharmacist_id:
        try:
            st.session_state["scan_id"] = get_store().record_scan(
                patient["id"], pharmacist_id, report
            )
        except Exception:
            st.session_state["scan_id"] = None

report = st.session_state.get("report")
if report and st.session_state.get("report_patient_id") == patient["id"]:
    st.divider()

    summary = report["summary"]
    alerts = report["alerts"]
    latency = f"{report['latency_ms']:.0f} ms"

    if report["status"] == "unavailable":
        banner("#c0392b", "NOT CHECKED",
               "The knowledge graph is unreachable - this prescription has not "
               "been screened. Verify it manually.")
        for warning in report["warnings"]:
            st.error(warning)

    elif not alerts:
        banner("#27ae60", "NO ISSUES FOUND",
               f"{summary['checks_run']} checks ran against "
               f"{report['patient']['active_med_count']} active medication(s) "
               f"in {latency}. Nothing on record contraindicates this prescription.")

    else:
        color, label = ACTION_STYLE.get(summary["recommended_action"], ("#7f8c8d", "REVIEW"))
        counts = summary["by_severity"]
        parts = [f"{counts[k]} {k}" for k in
                 ("contraindicated", "major", "moderate", "minor") if counts.get(k)]
        detail = f"{summary['overall_risk']} risk · {' · '.join(parts)} · {latency}"
        mem = summary.get("memory")
        if mem and mem["reminders"]:
            detail += f" · {mem['new']} new, {mem['reminders']} already reviewed"
        banner(color, label, detail)

        if report.get("unresolved_drugs"):
            st.warning(
                "Not checked (unknown to the knowledge base): "
                + ", ".join(report["unresolved_drugs"])
                + ". Absence of an alert for these is not evidence of safety."
            )
        for warning in report.get("warnings", []):
            st.info(warning)

        for alert in alerts:
            aid = alert["id"]
            with st.container(border=True):
                alert_header(alert)
                st.markdown(alert.get("explanation", ""))

                if alert.get("memory"):
                    memo = alert["memory"]
                    line = memo.get("reason_shown", "")
                    if memo.get("note"):
                        line += f"  Note: *{memo['note']}*"
                    if memo.get("times_seen", 1) > 1:
                        line += f"  (seen {memo['times_seen']} times)"
                    st.caption(line)

                with st.expander("Why - reasoning chain"):
                    for i, step in enumerate(alert.get("reasoning_chain", []), 1):
                        st.markdown(f"{i}. {step}")
                    evidence = alert.get("evidence") or {}
                    if evidence:
                        st.caption("From the knowledge graph: " + " · ".join(
                            f"**{k}**: {v}" for k, v in evidence.items()
                        ))

                act_col, note_col = st.columns([3, 2])
                with act_col:
                    decision = st.radio(
                        "Decision", options=list(DECISIONS), horizontal=True,
                        index=None, key=f"dec-{aid}", label_visibility="collapsed",
                        format_func=lambda d: d.replace("_", " "),
                    )
                    if decision:
                        st.caption(DECISION_HELP.get(decision, ""))
                with note_col:
                    note = st.text_input(
                        "Note", key=f"note-{aid}", label_visibility="collapsed",
                        placeholder="Note (why - recorded in the audit trail)",
                    )

                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Record decision", key=f"rec-{aid}",
                                 use_container_width=True,
                                 disabled=not (decision and pharmacist_id)):
                        try:
                            get_store().record_decision(
                                patient["id"], pharmacist_id, alert, decision,
                                note=note or None,
                                scan_id=st.session_state.get("scan_id"),
                            )
                            st.success("Recorded. It will show as reviewed next time.")
                        except Exception as exc:
                            st.error(f"Could not record: {exc}")
                    if not pharmacist_id:
                        st.caption("Enter a pharmacist code to record decisions.")
                with b2:
                    if st.button("Draft message to prescriber", key=f"draft-{aid}",
                                 use_container_width=True):
                        st.session_state["draft"] = draft_prescriber_message(
                            alert, patient=patient, prescription=report["prescription"],
                            pharmacist_name=pharmacist_code or None,
                        )
                        st.session_state["draft_for"] = aid

                if st.session_state.get("draft_for") == aid and st.session_state.get("draft"):
                    st.text_area("Message to prescriber", value=st.session_state["draft"],
                                 height=300, key=f"draftbox-{aid}")
                    st.caption("Edit as needed, then copy into your messaging system. "
                               "Recording the decision as 'prescriber contacted' keeps "
                               "the audit trail complete.")

    with st.expander("Run detail"):
        st.caption(
            f"Status {report['status']} · {latency} "
            f"(budget {report['latency_budget_ms']:.0f} ms, "
            f"within budget: {report['within_budget']}) · "
            f"{summary['checks_run']} checks"
        )
        st.json(report["timings_ms"])
