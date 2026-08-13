"""
Tests for memory.recall — how a past decision changes what the pharmacist sees.
Pure logic; no database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from memory.fingerprint import fingerprint
from memory.recall import (
    STATUS_NEW,
    STATUS_REMINDER,
    apply_memory,
    memory_summary,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

_RANK = {"contraindicated": 1, "major": 2, "moderate": 3, "minor": 4}


def _alert(severity="major", alert_type="interaction", drugs=("warfarin", "aspirin"),
           alert_id="INT-01", **evidence):
    return {
        "id": alert_id,
        "type": alert_type,
        "severity": severity,
        "severity_rank": _RANK[severity],
        "drugs_involved": list(drugs),
        "evidence": evidence,
        "title": f"{drugs[0]} + {drugs[1]}" if len(drugs) > 1 else drugs[0],
    }


def _review(alert, *, decision="acknowledged", days_ago=7, severity=None, times=1,
            note=None):
    return {
        fingerprint(alert): {
            "decision": decision,
            "note": note,
            "severity": severity or alert["severity"],
            "reviewed_at": NOW - timedelta(days=days_ago),
            "times_seen": times,
        }
    }


def _apply(alerts, memories):
    return apply_memory(alerts, memories, fingerprint_of=fingerprint, now=NOW)


# ── No memory ─────────────────────────────────────────────────────────────────

def test_unseen_finding_is_new():
    [out] = _apply([_alert()], {})
    assert out["status"] == STATUS_NEW
    assert "memory" not in out


def test_memory_for_a_different_finding_does_not_leak():
    other = _alert(drugs=("warfarin", "amiodarone"))
    [out] = _apply([_alert()], _review(other))
    assert out["status"] == STATUS_NEW


# ── Remembered findings ───────────────────────────────────────────────────────

def test_reviewed_finding_becomes_a_reminder_carrying_the_decision():
    alert = _alert(severity="major")
    [out] = _apply([alert], _review(alert, decision="acknowledged", days_ago=7,
                                    note="Prescriber confirmed; INR weekly."))

    assert out["status"] == STATUS_REMINDER
    assert out["memory"]["decision"] == "acknowledged"
    assert out["memory"]["decision_label"] == "reviewed and accepted"
    assert out["memory"]["note"] == "Prescriber confirmed; INR weekly."
    assert out["memory"]["reviewed_ago"] == "7 days ago"
    assert "reviewed and accepted" in out["memory"]["reason_shown"]


def test_clinical_severity_is_never_rewritten_by_memory():
    alert = _alert(severity="major")
    [out] = _apply([alert], _review(alert))
    assert out["severity"] == "major"
    assert out["severity_rank"] == _RANK["major"]


def test_times_seen_is_carried_through_for_recurring_findings():
    alert = _alert()
    [out] = _apply([alert], _review(alert, times=4))
    assert out["memory"]["times_seen"] == 4


# ── Safety rules ──────────────────────────────────────────────────────────────

def test_contraindicated_findings_are_never_demoted_to_a_reminder():
    """An overridden contraindication is still a contraindication today."""
    alert = _alert(severity="contraindicated")
    [out] = _apply([alert], _review(alert, decision="overridden", days_ago=3))

    assert out["status"] == STATUS_NEW
    assert "memory" in out, "it should still show what was decided before"
    assert "always shown in full" in out["memory"]["reason_shown"]


def test_escalated_finding_resurfaces_as_new():
    """Reviewed when moderate, now major - the old decision no longer applies."""
    alert = _alert(severity="major")
    [out] = _apply([alert], _review(alert, severity="moderate", days_ago=5))

    assert out["status"] == STATUS_NEW
    assert out["memory"]["escalated"] is True
    assert "MORE severe" in out["memory"]["reason_shown"]


def test_de_escalated_finding_still_becomes_a_reminder():
    alert = _alert(severity="moderate")
    [out] = _apply([alert], _review(alert, severity="major", days_ago=5))
    assert out["status"] == STATUS_REMINDER
    assert out["memory"]["escalated"] is False


def test_expired_review_resurfaces_as_new():
    alert = _alert()
    memories = _review(alert, days_ago=200)
    [out] = apply_memory([alert], memories, fingerprint_of=fingerprint, now=NOW,
                         window_days=90)
    assert out["status"] == STATUS_NEW
    assert "memory" not in out


def test_window_is_configurable():
    alert = _alert()
    memories = _review(alert, days_ago=200)
    [out] = apply_memory([alert], memories, fingerprint_of=fingerprint, now=NOW,
                         window_days=365)
    assert out["status"] == STATUS_REMINDER


# ── Ordering ──────────────────────────────────────────────────────────────────

def test_reminders_sink_below_new_findings_of_the_same_severity():
    seen   = _alert(severity="major", drugs=("warfarin", "aspirin"), alert_id="INT-01")
    unseen = _alert(severity="major", drugs=("warfarin", "amiodarone"), alert_id="INT-02")

    out = _apply([seen, unseen], _review(seen))

    assert [a["status"] for a in out] == [STATUS_NEW, STATUS_REMINDER]
    assert out[0]["drugs_involved"] == ["warfarin", "amiodarone"]


def test_a_more_severe_reminder_still_outranks_a_less_severe_new_finding():
    severe_seen = _alert(severity="major", drugs=("warfarin", "aspirin"), alert_id="INT-01")
    minor_new   = _alert(severity="minor", drugs=("a", "b"), alert_id="INT-02")

    out = _apply([severe_seen, minor_new], _review(severe_seen))

    assert out[0]["severity"] == "major"
    assert out[0]["status"] == STATUS_REMINDER


# ── Summary ───────────────────────────────────────────────────────────────────

def test_memory_summary_counts_new_versus_reminders():
    seen   = _alert(severity="major", drugs=("warfarin", "aspirin"), alert_id="INT-01")
    unseen = _alert(severity="major", drugs=("warfarin", "amiodarone"), alert_id="INT-02")

    out = _apply([seen, unseen], _review(seen))
    summary = memory_summary(out)

    assert summary["new"] == 1
    assert summary["reminders"] == 1
    assert summary["has_memory"] is True
    assert summary["escalated"] == 0


def test_summary_of_an_untouched_report():
    out = _apply([_alert()], {})
    assert memory_summary(out) == {
        "new": 1, "reminders": 0, "has_memory": False, "escalated": 0,
    }


def test_apply_memory_does_not_mutate_the_input_alerts():
    alert = _alert()
    original = dict(alert)
    _apply([alert], _review(alert))
    assert alert == original
