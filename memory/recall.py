"""
Applying memory to a fresh alert report.

The point of memory is that a pharmacist who has already reviewed a finding for
a patient should not be shown the same red alert as though it were new. They
should be reminded, with what they decided last time.

What this does **not** do is change the clinical severity. A contraindication
that was overridden last week is still a contraindication today; only the
*presentation* softens. Two rules protect that:

* ``NEVER_DEMOTED`` — the most severe band always stays a fresh alert. It is
  annotated with the earlier decision, but never turned into a quiet reminder.
* **Escalation resets memory.** If a finding is more severe now than when it was
  reviewed, the earlier decision no longer applies to it and it resurfaces as
  new.

Reviews also expire (``DEFAULT_WINDOW_DAYS``): a decision from two years ago is
history, not a current judgement.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

STATUS_NEW      = "new"
STATUS_REMINDER = "reminder"

_STATUS_RANK = {STATUS_NEW: 0, STATUS_REMINDER: 1}

#: How long a pharmacist's decision keeps softening the alert.
DEFAULT_WINDOW_DAYS = 90

#: Severities that always stay a fresh alert, whatever the history.
#: Mirrors ``engine.alerts.CONTRAINDICATED``; kept as a literal so the memory
#: module stays independent of the engine.
NEVER_DEMOTED = frozenset({"contraindicated"})

#: Lower rank = more severe. Mirrors ``engine.alerts.SEVERITY_RANK``.
_SEVERITY_RANK = {"contraindicated": 1, "major": 2, "moderate": 3, "minor": 4}

#: Noun form, for badges and history lists ("Decision: overridden").
DECISION_LABEL = {
    "acknowledged":         "reviewed and accepted",
    "overridden":           "overridden",
    "prescriber_contacted": "prescriber contacted",
    "not_dispensed":        "not dispensed",
    "dismissed":            "dismissed as not applicable",
}

#: Past-tense verb form, for the sentence "You ___ this 3 days ago."
DECISION_VERB = {
    "acknowledged":         "reviewed and accepted",
    "overridden":           "overrode",
    "prescriber_contacted": "contacted the prescriber about",
    "not_dispensed":        "declined to dispense",
    "dismissed":            "dismissed",
}


def _rank(severity: str | None) -> int:
    return _SEVERITY_RANK.get((severity or "").lower(), 99)


def _humanise_age(reviewed_at: datetime, now: datetime) -> str:
    days = max((now - reviewed_at).days, 0)
    if days == 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


def apply_memory(
    alerts: list[dict],
    memories: dict[str, dict],
    *,
    fingerprint_of,
    now: datetime | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[dict]:
    """
    Annotate *alerts* with what the pharmacist previously decided.

    Args:
        alerts:        the report's alerts, already severity-sorted
        memories:      ``{fingerprint: {decision, note, severity, reviewed_at,
                       times_seen}}`` — the latest review per finding
        fingerprint_of: callable mapping an alert to its stable identity
        now:           override for testing
        window_days:   how long a decision keeps applying

    Returns:
        A new list. Each alert gains ``status`` (``new``/``reminder``) and, when
        remembered, a ``memory`` block. Reminders sort below new findings of the
        same severity so attention still lands on what is genuinely new.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    annotated: list[dict] = []
    for alert in alerts:
        item = dict(alert)
        item["status"] = STATUS_NEW

        record = memories.get(fingerprint_of(alert))
        if record:
            reviewed_at = record.get("reviewed_at")
            if isinstance(reviewed_at, datetime):
                if reviewed_at.tzinfo is None:
                    reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
            else:
                reviewed_at = None

            expired = reviewed_at is not None and reviewed_at < cutoff
            escalated = _rank(item.get("severity")) < _rank(record.get("severity"))

            if reviewed_at is not None and not expired:
                decision = record.get("decision", "")
                item["memory"] = {
                    "decision":       decision,
                    "decision_label": DECISION_LABEL.get(decision, decision),
                    "note":           record.get("note"),
                    "reviewed_at":    reviewed_at.isoformat(),
                    "reviewed_ago":   _humanise_age(reviewed_at, now),
                    "times_seen":     record.get("times_seen", 1),
                    "severity_when_reviewed": record.get("severity"),
                    "escalated":      escalated,
                }

                verb = DECISION_VERB.get(decision, decision)
                ago = _humanise_age(reviewed_at, now)
                demotable = (item.get("severity") or "").lower() not in NEVER_DEMOTED

                if demotable and not escalated:
                    item["status"] = STATUS_REMINDER
                    item["memory"]["reason_shown"] = f"You {verb} this {ago}."
                elif escalated:
                    item["memory"]["reason_shown"] = (
                        f"Reviewed {ago}, but this finding is now MORE severe than "
                        f"when you saw it ({record.get('severity')} -> "
                        f"{item.get('severity')})."
                    )
                else:
                    item["memory"]["reason_shown"] = (
                        f"You {verb} this {ago}, but the severity of this finding "
                        f"means it is always shown in full."
                    )

        annotated.append(item)

    annotated.sort(
        key=lambda a: (
            a.get("severity_rank", 99),
            _STATUS_RANK.get(a.get("status"), 0),
            a.get("type", ""),
            a.get("id", ""),
        )
    )
    return annotated


def memory_summary(alerts: list[dict]) -> dict:
    """Counts the interface uses to phrase 'N new, M already reviewed'."""
    new = sum(1 for a in alerts if a.get("status", STATUS_NEW) == STATUS_NEW)
    return {
        "new":              new,
        "reminders":        len(alerts) - new,
        "has_memory":       any("memory" in a for a in alerts),
        "escalated":        sum(1 for a in alerts if a.get("memory", {}).get("escalated")),
    }
