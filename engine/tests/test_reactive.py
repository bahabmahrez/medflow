"""
Tests for engine.reactive.scan_prescription — the full reactive flow with the
query layer mocked. No Neo4j, no LLM, no network.
"""
from __future__ import annotations

from unittest.mock import patch

from engine import alerts as A
from engine.reactive import scan_prescription


def _found(payload: dict) -> dict:
    return {"status": "found", "data": payload, "message": "ok"}


def _none(payload: dict | None = None) -> dict:
    return {"status": "not_found", "data": payload or {}, "message": "none"}


def _resolutions(*names: str) -> dict:
    return {
        name: {
            "status": "found",
            "data": {"canonical": name.lower(), "rxnorm_cui": None,
                     "match_type": "inn", "input": name},
            "message": "ok",
        }
        for name in names
    }


def _run(**overrides):
    """Run a scan with every query-layer call mocked; overrides replace defaults."""
    defaults = {
        "resolve_many":                   lambda names: _resolutions(*names),
        "detect_pairwise_interactions":   lambda drugs: _none({"interactions": []}),
        "detect_cyp_competition":         lambda drugs: _none({"competitions": []}),
        "check_contraindications":        lambda d, c: _none({"contraindications": []}),
        "check_allergy_conflict":         lambda d, a: _none({"conflicts": []}),
        "check_therapeutic_duplication":  lambda d, m: _none({"duplicates": []}),
        "check_dose_appropriateness":     lambda d, dose, age, w, labs: _none(
                                              {"recommendations": []}),
    }
    defaults.update(overrides)
    scan_kwargs = defaults.pop("scan_kwargs", {})

    patchers = [patch(f"engine.reactive.{name}", side_effect=fn)
                for name, fn in defaults.items()]
    for p in patchers:
        p.start()
    try:
        return scan_prescription(**scan_kwargs)
    finally:
        for p in patchers:
            p.stop()


# ── Clean case ────────────────────────────────────────────────────────────────

def test_no_findings_yields_a_calm_dispense_report():
    report = _run(scan_kwargs={
        "prescription": [{"drug": "paracetamol"}],
        "patient_meds": ["metformin"],
    })

    assert report["status"] == "ok"
    assert report["alerts"] == []
    assert report["summary"]["alert_count"] == 0
    assert report["summary"]["overall_risk"] == "NONE"
    assert report["summary"]["recommended_action"] == A.DISPENSE
    assert report["warnings"] == []


# ── Findings, ordering and roll-up ────────────────────────────────────────────

def test_findings_are_sorted_with_the_dangerous_one_first():
    report = _run(
        detect_pairwise_interactions=lambda drugs: _found({"interactions": [
            {"drug_a": "warfarin", "drug_b": "amiodarone",
             "severity": "contre_indique", "effect": "Bleeding risk.",
             "mechanism": "Metabolic inhibition.", "source": "ANSM"},
        ]}),
        detect_cyp_competition=lambda drugs: _found({"competitions": [
            {"substrate": "simvastatin", "modulator": "clarithromycin",
             "enzyme": "CYP3A4", "effect": "INHIBITS", "strength": "moderate",
             "risk": "simvastatin accumulation risk"},
        ]}),
        scan_kwargs={
            "prescription": [{"drug": "clarithromycin"}],
            "patient_meds": ["warfarin", "amiodarone", "simvastatin"],
        },
    )

    severities = [a["severity"] for a in report["alerts"]]
    assert severities == [A.CONTRAINDICATED, A.MODERATE]
    assert report["summary"]["overall_risk"] == "HIGH"
    assert report["summary"]["recommended_action"] == A.DO_NOT_DISPENSE
    assert report["summary"]["by_severity"][A.CONTRAINDICATED] == 1


def test_same_pair_flagged_twice_is_merged_into_one_alert():
    """
    A pair with both a direct interaction and enzyme competition must produce
    ONE alert - two would be redundant noise and inflate the alert count.
    """
    report = _run(
        detect_pairwise_interactions=lambda drugs: _found({"interactions": [
            {"drug_a": "clarithromycin", "drug_b": "simvastatin",
             "severity": "contre_indique", "effect": "Rhabdomyolysis risk.",
             "mechanism": "CYP3A4 inhibition.", "source": "ANSM"},
        ]}),
        detect_cyp_competition=lambda drugs: _found({"competitions": [
            {"substrate": "simvastatin", "modulator": "clarithromycin",
             "enzyme": "CYP3A4", "effect": "INHIBITS", "strength": "strong",
             "risk": "simvastatin accumulation"},
        ]}),
        scan_kwargs={
            "prescription": [{"drug": "clarithromycin"}],
            "patient_meds": ["simvastatin"],
        },
    )

    assert len(report["alerts"]) == 1
    alert = report["alerts"][0]
    # the more severe finding leads, the other survives as supporting detail
    assert alert["severity"] == A.CONTRAINDICATED
    assert "merged_from" in alert
    assert any("Supporting finding" in step for step in alert["reasoning_chain"])
    assert alert["evidence"].get("enzyme") == "CYP3A4"


def test_cyp_alert_never_claims_no_direct_edge_when_one_exists():
    """The 'no direct edge' line is the CYP check's core insight - it must be true."""
    report = _run(
        detect_pairwise_interactions=lambda drugs: _found({"interactions": [
            {"drug_a": "clarithromycin", "drug_b": "simvastatin",
             "severity": "moderate", "effect": "Myopathy risk.",
             "mechanism": "Shared pathway.", "source": "ANSM"},
        ]}),
        detect_cyp_competition=lambda drugs: _found({"competitions": [
            {"substrate": "simvastatin", "modulator": "clarithromycin",
             "enzyme": "CYP3A4", "effect": "INHIBITS", "strength": "strong"},
        ]}),
        scan_kwargs={
            "prescription": [{"drug": "clarithromycin"}],
            "patient_meds": ["simvastatin"],
        },
    )

    text = " ".join(
        step for alert in report["alerts"] for step in alert["reasoning_chain"]
    )
    assert "no direct interaction edge" not in text.lower()


def test_cyp_only_pair_still_states_the_no_direct_edge_insight():
    report = _run(
        detect_cyp_competition=lambda drugs: _found({"competitions": [
            {"substrate": "simvastatin", "modulator": "clarithromycin",
             "enzyme": "CYP3A4", "effect": "INHIBITS", "strength": "strong"},
        ]}),
        scan_kwargs={
            "prescription": [{"drug": "clarithromycin"}],
            "patient_meds": ["simvastatin"],
        },
    )

    assert len(report["alerts"]) == 1
    text = " ".join(report["alerts"][0]["reasoning_chain"]).lower()
    assert "no direct interaction edge" in text


def test_every_alert_carries_a_reasoning_chain_and_an_action():
    report = _run(
        detect_pairwise_interactions=lambda drugs: _found({"interactions": [
            {"drug_a": "warfarin", "drug_b": "aspirin", "severity": "major",
             "effect": "Additive bleeding risk.", "mechanism": "Both impair haemostasis.",
             "source": "ANSM"},
        ]}),
        scan_kwargs={
            "prescription": [{"drug": "aspirin"}],
            "patient_meds": ["warfarin"],
        },
    )

    assert report["alerts"], "expected at least one alert"
    for alert in report["alerts"]:
        assert alert["reasoning_chain"], "each finding must explain itself"
        assert len(alert["reasoning_chain"]) >= 3
        assert alert["recommended_action"] in A.ACTION_RANK
        assert alert["explanation"]
        assert alert["color"]


def test_per_drug_checks_produce_their_alerts():
    report = _run(
        check_contraindications=lambda d, c: _found({"contraindications": [
            {"input_condition": "CKD stage 4", "matched_concept": "chronic kidney disease",
             "icd_code": "N18", "severity": "contraindicated",
             "reason": "Lactic acidosis risk.", "source": "ANSM"},
        ]}),
        check_allergy_conflict=lambda d, a: _found({"conflicts": [
            {"type": "direct", "patient_allergy": "penicillin",
             "drug_group": "penicillins"},
        ]}),
        check_therapeutic_duplication=lambda d, m: _found({"duplicates": [
            {"input_name": "Tahor", "resolved_inn": "atorvastatin",
             "same_as": "atorvastatin"},
        ]}),
        check_dose_appropriateness=lambda d, dose, age, w, labs: _found({
            "prescribed_dose": "500mg", "standard_dose": "500mg q12h",
            "recommendations": [
                {"flag": "renal_impairment", "reason": "creatinine=210",
                 "guidance": "Reduce dose."},
            ],
        }),
        scan_kwargs={
            "prescription": [{"drug": "metformin", "dose": "500mg"}],
            "patient_meds": ["Tahor"],
            "conditions": ["CKD stage 4"],
            "allergies": ["penicillin"],
            "age": 80,
            "labs": {"creatinine_umol_L": 210},
        },
    )

    types = {a["type"] for a in report["alerts"]}
    assert {"contraindication", "allergy", "duplication", "dose"} <= types
    assert report["summary"]["recommended_action"] == A.DO_NOT_DISPENSE


# ── Safety-critical behaviours ────────────────────────────────────────────────

def test_unresolved_drug_is_reported_not_silently_skipped():
    def partial(names):
        out = _resolutions(*[n for n in names if n != "zyboxithol"])
        out["zyboxithol"] = {"status": "not_found", "data": {}, "message": "unknown"}
        return out

    report = _run(
        resolve_many=partial,
        scan_kwargs={
            "prescription": [{"drug": "zyboxithol"}],
            "patient_meds": ["warfarin"],
        },
    )

    assert report["unresolved_drugs"] == ["zyboxithol"]
    unknown = [a for a in report["alerts"] if a["type"] == "unknown_drug"]
    assert len(unknown) == 1
    chain = " ".join(unknown[0]["reasoning_chain"])
    assert "not evidence of safety" in chain


def test_backend_failure_is_never_reported_as_a_clean_scan():
    """
    A dead knowledge graph must not render as 'no issues found', and real
    drugs must not be mislabelled as unknown just because lookup failed.
    """
    def unreachable(names):
        return {n: {"status": "error", "data": {},
                    "message": "Couldn't connect to localhost:7687"} for n in names}

    report = _run(
        resolve_many=unreachable,
        scan_kwargs={
            "prescription": [{"drug": "clarithromycin"}],
            "patient_meds": ["simvastatin", "warfarin"],
        },
    )

    assert report["status"] == "unavailable"
    assert report["summary"]["overall_risk"] == "UNKNOWN"
    assert report["summary"]["recommended_action"] != A.DISPENSE
    # real drugs must NOT be blamed as missing from the knowledge base
    assert report["unresolved_drugs"] == []
    assert any("NO safety check" in w and "not been screened" in w
               for w in report["warnings"])


def test_backend_failure_short_circuits_instead_of_running_every_check():
    """Each downstream check would repeat the same timeout — none should run."""
    called: list[str] = []

    def unreachable(names):
        return {n: {"status": "error", "data": {}, "message": "down"} for n in names}

    def tracker(*args, **kwargs):
        called.append("check")
        return _none({})

    _run(
        resolve_many=unreachable,
        detect_pairwise_interactions=tracker,
        detect_cyp_competition=tracker,
        check_therapeutic_duplication=tracker,
        scan_kwargs={
            "prescription": [{"drug": "aspirin"}],
            "patient_meds": ["warfarin"],
        },
    )

    assert called == [], "no check should run once the backend is known to be down"


def test_a_failing_check_warns_instead_of_crashing_the_scan():
    def boom(drugs):
        raise RuntimeError("Neo4j unavailable")

    report = _run(
        detect_pairwise_interactions=boom,
        scan_kwargs={
            "prescription": [{"drug": "aspirin"}],
            "patient_meds": ["warfarin"],
        },
    )

    assert report["status"] == "ok"
    assert any("Neo4j unavailable" in w for w in report["warnings"])


def test_empty_input_returns_an_error_report_not_an_exception():
    report = scan_prescription([], patient_meds=[])
    assert report["status"] == "error"
    assert report["alerts"] == []
    assert report["warnings"]


# ── Memory integration (Milestone 2) ──────────────────────────────────────────

class _StubStore:
    """Stands in for memory.MemoryStore; records what was asked for."""

    def __init__(self, memories=None):
        self.memories = memories or {}
        self.asked = []

    def recall(self, patient_id, pharmacist_id, fingerprints):
        self.asked.append((patient_id, pharmacist_id, list(fingerprints)))
        return {fp: self.memories[fp] for fp in fingerprints if fp in self.memories}


def _interaction_scan(store=None, **ids):
    return _run(
        detect_pairwise_interactions=lambda drugs: _found({"interactions": [
            {"drug_a": "warfarin", "drug_b": "aspirin", "severity": "major",
             "effect": "Additive bleeding risk.", "mechanism": "Both impair haemostasis.",
             "source": "ANSM"},
        ]}),
        scan_kwargs={
            "prescription": [{"drug": "aspirin"}],
            "patient_meds": ["warfarin"],
            "memory_store": store,
            **ids,
        },
    )


def test_memory_is_skipped_when_no_patient_or_pharmacist_is_given():
    store = _StubStore()
    report = _interaction_scan(store)

    assert store.asked == [], "no ids means no memory lookup"
    assert report["summary"]["memory"] is None
    assert report["alerts"][0].get("status") in (None, "new")


def test_previously_reviewed_finding_returns_as_a_reminder():
    from datetime import datetime, timezone
    from memory.fingerprint import fingerprint

    key = fingerprint({"type": "interaction",
                       "drugs_involved": ["warfarin", "aspirin"], "evidence": {}})
    store = _StubStore({key: {
        "decision": "acknowledged", "note": "Prescriber confirmed.",
        "severity": "major", "reviewed_at": datetime.now(timezone.utc),
        "times_seen": 2,
    }})

    report = _interaction_scan(store, patient_id=7, pharmacist_id=3)

    assert store.asked == [(7, 3, [key])], "one lookup for every finding on screen"
    alert = report["alerts"][0]
    assert alert["status"] == "reminder"
    assert alert["memory"]["decision"] == "acknowledged"
    assert alert["severity"] == "major", "clinical severity is untouched"
    assert report["summary"]["memory"] == {
        "new": 0, "reminders": 1, "has_memory": True, "escalated": 0,
    }
    assert "memory_recall" in report["timings_ms"]


def test_unreviewed_finding_stays_new_when_memory_is_consulted():
    store = _StubStore()
    report = _interaction_scan(store, patient_id=7, pharmacist_id=3)

    assert report["alerts"][0]["status"] == "new"
    assert report["summary"]["memory"]["new"] == 1


def test_memory_outage_costs_the_annotations_never_the_scan():
    class _BrokenStore:
        def recall(self, *a, **kw):
            raise RuntimeError("PostgreSQL unavailable")

    report = _interaction_scan(_BrokenStore(), patient_id=7, pharmacist_id=3)

    assert report["status"] == "ok"
    assert len(report["alerts"]) == 1, "the safety finding still reaches the pharmacist"
    assert any("memory unavailable" in w for w in report["warnings"])


# ── Latency instrumentation ───────────────────────────────────────────────────

def test_every_run_is_measured_against_the_budget():
    report = _run(scan_kwargs={"prescription": [{"drug": "paracetamol"}]})

    assert isinstance(report["latency_ms"], float)
    assert report["latency_ms"] >= 0
    assert report["latency_budget_ms"] == 2000.0
    assert report["within_budget"] is True
    assert "preload_resolve" in report["timings_ms"]


def test_budget_flag_reflects_a_tighter_budget():
    report = _run(scan_kwargs={
        "prescription": [{"drug": "paracetamol"}],
        "latency_budget_ms": 0.0,
    })
    assert report["within_budget"] is False


def test_names_are_resolved_once_for_the_whole_scan():
    calls: list[list[str]] = []

    def tracking(names):
        calls.append(list(names))
        return _resolutions(*names)

    _run(
        resolve_many=tracking,
        scan_kwargs={
            "prescription": [{"drug": "clarithromycin"}],
            "patient_meds": ["warfarin", "simvastatin"],
        },
    )

    assert len(calls) == 1, "preload must resolve the whole scan in one call"
    assert set(calls[0]) == {"clarithromycin", "warfarin", "simvastatin"}
