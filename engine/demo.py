"""
MedFlow Reactive Safety Engine — Live Latency & Safety Report Demo

Demonstrates the latency separation between:
  1. Deterministic Graph Query Latency (< 50ms)
  2. LLM Synthesis Latency (depends on model / hardware)
"""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.reactive import scan_prescription
from llm.provider import generate

SYSTEM_PROMPT = """You are MedFlow's clinical safety synthesis engine.
Synthesize the structured graph safety alerts into a concise 1-2 sentence clinical summary for a pharmacist.
Cite the primary drug-drug finding and recommended action."""

def run_scenario(title, prescription, patient_meds, synthesize_llm=True):
    print("=" * 70)
    print(f"[{title}]")
    print("=" * 70)

    # 1. Deterministic Graph Query
    t0 = time.perf_counter()
    report = scan_prescription(prescription, patient_meds=patient_meds)
    graph_time_ms = (time.perf_counter() - t0) * 1000.0

    action = report["summary"]["recommended_action"]
    risk = report["summary"]["overall_risk"]
    alerts = report.get("alerts", [])

    print(f"\nOverall Status:     {risk}")
    print(f"Recommended Action: {action}")

    # 2. LLM Synthesis (if requested)
    llm_time_ms = 0.0
    summary_text = ""
    if synthesize_llm and alerts:
        t_llm = time.perf_counter()
        try:
            alerts_context = json.dumps([{
                "title": a.get("title"),
                "severity": a.get("severity"),
                "explanation": a.get("explanation"),
                "action": a.get("recommended_action"),
            } for a in alerts], indent=2)

            user_msg = f"Patient Meds: {patient_meds}\nNew Prescription: {prescription}\nSynthesize these findings."
            summary_text = generate(system=SYSTEM_PROMPT, user=user_msg, context=alerts_context)
            llm_time_ms = (time.perf_counter() - t_llm) * 1000.0
        except Exception as exc:
            summary_text = f"LLM synthesis skipped or offline ({exc})"
            llm_time_ms = (time.perf_counter() - t_llm) * 1000.0

    total_time_ms = graph_time_ms + llm_time_ms

    if summary_text:
        print(f"Summary:            {summary_text.strip()}")

    print("-" * 50)
    print("LATENCY BREAKDOWN:")
    print(f"  Deterministic Graph Query Latency: {graph_time_ms:6.2f} ms")
    print(f"  LLM Synthesis Latency:             {llm_time_ms:6.2f} ms")
    print(f"  Total Analysis Latency:            {total_time_ms:6.2f} ms")
    print("-" * 50)

    print(f"\nAlerts Found ({len(alerts)}):")
    for i, alert in enumerate(alerts, 1):
        print(f"  {i}. [{alert.get('severity', '').upper()}] {alert.get('title')}")
        if alert.get("explanation"):
            print(f"     Description: {alert['explanation']}")
        chain = alert.get("reasoning_chain", [])
        if chain:
            print("     Reasoning Chain:")
            for step in chain:
                print(f"       - {step}")
    print()

def main():
    print("======================================================================")
    print(" MedFlow Reactive Safety Engine — Live Latency & Safety Report")
    print("======================================================================")
    print()

    # Scenario 1: Aspirin for patient on Warfarin
    run_scenario(
        "Scenario 1: High-Risk Prescription Check: Aspirin for patient on Warfarin",
        prescription=[{"drug": "aspirin", "dose": "100mg"}],
        patient_meds=["warfarin"],
        synthesize_llm=True,
    )

    # Scenario 2: Simvastatin + Clarithromycin (CYP3A4)
    run_scenario(
        "Scenario 2: CYP450 Competition: Simvastatin + Clarithromycin",
        prescription=[{"drug": "clarithromycin", "dose": "500mg"}],
        patient_meds=["simvastatin"],
        synthesize_llm=False,
    )

if __name__ == "__main__":
    main()
