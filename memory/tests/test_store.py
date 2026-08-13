"""
Round-trip tests for memory.store against a real PostgreSQL.

Skipped cleanly when the database is unreachable, so the suite stays runnable
without docker. Each test uses a throwaway pharmacist code and removes its own
rows afterwards.
"""
from __future__ import annotations

import uuid

import pytest

from memory.fingerprint import fingerprint
from memory.store import MemoryStore


@pytest.fixture(scope="module")
def store():
    store = MemoryStore()
    try:
        store.init_schema()
    except Exception as exc:  # postgres not running
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    return store


@pytest.fixture(scope="module")
def patient_id(store):
    """Any real patient — alert_reviews.patient_id is a foreign key."""
    with store._connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM patients ORDER BY id LIMIT 1")
        row = cur.fetchone()
    if not row:
        pytest.skip("no patients loaded; run the loaders first")
    return row[0]


@pytest.fixture
def pharmacist(store):
    code = f"test-{uuid.uuid4().hex[:12]}"
    pid = store.get_or_create_pharmacist(code, "Test Pharmacist")
    yield pid
    with store._connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM alert_reviews WHERE pharmacist_id = %s", (pid,))
        cur.execute("DELETE FROM prescription_scans WHERE pharmacist_id = %s", (pid,))
        cur.execute("DELETE FROM pharmacists WHERE id = %s", (pid,))


def _alert(severity="major", drugs=("warfarin", "aspirin")):
    return {
        "id": "INT-01", "type": "interaction", "severity": severity,
        "title": " + ".join(drugs), "drugs_involved": list(drugs), "evidence": {},
    }


# ── Pharmacists ───────────────────────────────────────────────────────────────

def test_get_or_create_pharmacist_is_idempotent(store, pharmacist):
    with store._connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT code FROM pharmacists WHERE id = %s", (pharmacist,))
        code = cur.fetchone()[0]
    assert store.get_or_create_pharmacist(code) == pharmacist


def test_blank_pharmacist_code_is_rejected(store):
    with pytest.raises(ValueError):
        store.get_or_create_pharmacist("   ")


# ── Record and recall ─────────────────────────────────────────────────────────

def test_a_recorded_decision_comes_back_on_recall(store, patient_id, pharmacist):
    alert = _alert()
    store.record_decision(patient_id, pharmacist, alert, "acknowledged",
                          note="Prescriber confirmed.")

    found = store.recall(patient_id, pharmacist, [fingerprint(alert)])

    assert fingerprint(alert) in found
    record = found[fingerprint(alert)]
    assert record["decision"] == "acknowledged"
    assert record["note"] == "Prescriber confirmed."
    assert record["severity"] == "major"
    assert record["times_seen"] == 1


def test_recall_returns_the_latest_decision_and_counts_every_one(store, patient_id,
                                                                pharmacist):
    alert = _alert()
    store.record_decision(patient_id, pharmacist, alert, "acknowledged")
    store.record_decision(patient_id, pharmacist, alert, "prescriber_contacted",
                          note="Escalated on review.")

    record = store.recall(patient_id, pharmacist, [fingerprint(alert)])[fingerprint(alert)]

    assert record["decision"] == "prescriber_contacted", "latest decision wins"
    assert record["times_seen"] == 2, "history is append-only, not overwritten"


def test_recall_is_scoped_to_the_reviewing_pharmacist(store, patient_id, pharmacist):
    alert = _alert()
    store.record_decision(patient_id, pharmacist, alert, "acknowledged")

    other = store.get_or_create_pharmacist(f"test-{uuid.uuid4().hex[:12]}")
    try:
        assert store.recall(patient_id, other, [fingerprint(alert)]) == {}
    finally:
        with store._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pharmacists WHERE id = %s", (other,))


def test_recall_of_nothing_is_free(store, patient_id, pharmacist):
    assert store.recall(patient_id, pharmacist, []) == {}


def test_unknown_decision_is_rejected(store, patient_id, pharmacist):
    with pytest.raises(ValueError):
        store.record_decision(patient_id, pharmacist, _alert(), "whatever")


# ── Scans and patterns ────────────────────────────────────────────────────────

def test_record_scan_stores_what_was_shown(store, patient_id, pharmacist):
    report = {
        "prescription": [{"drug": "clarithromycin", "dose": "500mg"}],
        "alerts": [_alert()],
        "summary": {"alert_count": 1, "overall_risk": "HIGH",
                    "recommended_action": "contact_prescriber"},
        "latency_ms": 152.3,
    }
    scan_id = store.record_scan(patient_id, pharmacist, report)

    with store._connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT alert_count, overall_risk, latency_ms FROM prescription_scans "
            "WHERE id = %s", (scan_id,),
        )
        count, risk, latency = cur.fetchone()
    assert (count, risk, float(latency)) == (1, "HIGH", 152.3)


def test_recurring_findings_surface_repeat_offenders(store, patient_id, pharmacist):
    repeated = _alert(drugs=("warfarin", "aspirin"))
    once     = _alert(drugs=("warfarin", "amiodarone"))
    for _ in range(3):
        store.record_decision(patient_id, pharmacist, repeated, "acknowledged")
    store.record_decision(patient_id, pharmacist, once, "acknowledged")

    patterns = {p["fingerprint"]: p for p in store.recurring_findings(patient_id,
                                                                     min_times=2)}

    assert patterns[fingerprint(repeated)]["times_seen"] >= 3
    assert fingerprint(once) not in patterns


def test_patient_history_is_newest_first(store, patient_id, pharmacist):
    store.record_decision(patient_id, pharmacist, _alert(drugs=("a1", "b1")), "acknowledged")
    store.record_decision(patient_id, pharmacist, _alert(drugs=("a2", "b2")), "overridden")

    history = store.patient_history(patient_id, limit=5)

    assert history[0]["decision"] == "overridden"
    assert history[0]["pharmacist_code"].startswith("test-")
