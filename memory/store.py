"""
PostgreSQL persistence for the memory module.

Holds three things (see db/migrations/002_memory.sql for the schema and the
reasoning behind it):

* **pharmacists**        who is reviewing
* **alert_reviews**      their decisions, append-only
* **prescription_scans** what was screened and what was shown

The store is deliberately thin: connections are opened per operation with a
short timeout, so a database that is down fails fast and a scan degrades to
"no memory" rather than hanging or crashing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg2
import psycopg2.extras

_MIGRATION = Path(__file__).resolve().parent.parent / "db" / "migrations" / "002_memory.sql"

#: Decisions a pharmacist can record against a finding.
DECISIONS = (
    "acknowledged",          # reviewed, risk accepted, dispensed as written
    "overridden",            # dispensed despite the alert, with justification
    "prescriber_contacted",  # escalated to the prescriber and resolved
    "not_dispensed",         # refused
    "dismissed",             # judged not applicable to this patient
)


class MemoryStore:
    """Read/write access to what the agent remembers."""

    def __init__(self, **overrides) -> None:
        self._params = {
            "dbname":   os.getenv("POSTGRES_DB", "medflow"),
            "user":     os.getenv("POSTGRES_USER", "medflow"),
            "password": os.getenv("POSTGRES_PASSWORD", "medflow"),
            "host":     os.getenv("POSTGRES_HOST", "localhost"),
            "port":     os.getenv("POSTGRES_PORT", "5432"),
            # Fail fast, for the same reason the graph driver does: a slow
            # failure at the counter is worse than a clear one.
            "connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "3")),
        }
        self._params.update(overrides)

    def _connect(self):
        return psycopg2.connect(**self._params)

    # ── Schema ────────────────────────────────────────────────────────────────

    def init_schema(self) -> None:
        """
        Apply 002_memory.sql. Idempotent — safe to run on an existing database.

        Needed because docker-entrypoint-initdb.d only runs on a *fresh* volume,
        and the project's Postgres volume already exists.
        """
        sql = _MIGRATION.read_text(encoding="utf-8")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql)

    def schema_ready(self) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.alert_reviews') IS NOT NULL")
            return bool(cur.fetchone()[0])

    # ── Pharmacists ───────────────────────────────────────────────────────────

    def get_or_create_pharmacist(self, code: str, name: str | None = None) -> int:
        """Resolve a badge/login code to a pharmacist id, creating it if new."""
        if not code or not code.strip():
            raise ValueError("pharmacist code is required")
        code = code.strip()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pharmacists (code, name) VALUES (%s, %s)
                ON CONFLICT (code) DO UPDATE SET name = COALESCE(EXCLUDED.name, pharmacists.name)
                RETURNING id
                """,
                (code, name),
            )
            return cur.fetchone()[0]

    # ── Recall (the hot path) ─────────────────────────────────────────────────

    def recall(
        self, patient_id: int, pharmacist_id: int, fingerprints: list[str]
    ) -> dict[str, dict]:
        """
        Return the most recent review per fingerprint for this pharmacist and
        patient, plus how many times each has been reviewed.

        Scoped to the reviewing pharmacist on purpose: one pharmacist accepting
        a risk is not a decision another pharmacist has made.
        """
        if not fingerprints:
            return {}
        with self._connect() as conn, conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (fingerprint)
                       fingerprint, decision, note, severity, reviewed_at,
                       count(*) OVER (PARTITION BY fingerprint) AS times_seen
                  FROM alert_reviews
                 WHERE patient_id = %s
                   AND pharmacist_id = %s
                   AND fingerprint = ANY(%s)
                 ORDER BY fingerprint, reviewed_at DESC
                """,
                (patient_id, pharmacist_id, list(fingerprints)),
            )
            return {row["fingerprint"]: dict(row) for row in cur.fetchall()}

    # ── Writes ────────────────────────────────────────────────────────────────

    def record_scan(
        self, patient_id: int | None, pharmacist_id: int | None, report: dict
    ) -> int:
        """Log one scan and the alerts it displayed; returns the scan id."""
        summary = report.get("summary", {})
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prescription_scans
                    (patient_id, pharmacist_id, prescribed, alerts, alert_count,
                     overall_risk, recommended_action, latency_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    patient_id, pharmacist_id,
                    json.dumps(report.get("prescription", []), default=str),
                    json.dumps(report.get("alerts", []), default=str),
                    summary.get("alert_count", 0),
                    summary.get("overall_risk"),
                    summary.get("recommended_action"),
                    report.get("latency_ms"),
                ),
            )
            return cur.fetchone()[0]

    def record_decision(
        self,
        patient_id: int,
        pharmacist_id: int,
        alert: dict,
        decision: str,
        *,
        note: str | None = None,
        scan_id: int | None = None,
        fingerprint_of=None,
    ) -> int:
        """
        Record a pharmacist's ruling on one finding.

        Append-only: a new decision never overwrites the previous one, so the
        audit trail and the "how often has this come up" count both survive.
        """
        if decision not in DECISIONS:
            raise ValueError(f"unknown decision {decision!r}; expected one of {DECISIONS}")

        if fingerprint_of is None:
            from .fingerprint import fingerprint as fingerprint_of

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alert_reviews
                    (patient_id, pharmacist_id, scan_id, fingerprint, alert_type,
                     severity, title, drugs, decision, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    patient_id, pharmacist_id, scan_id,
                    fingerprint_of(alert),
                    alert.get("type"),
                    alert.get("severity"),
                    alert.get("title"),
                    [str(d) for d in (alert.get("drugs_involved") or [])],
                    decision,
                    note,
                ),
            )
            return cur.fetchone()[0]

    # ── History / patterns ────────────────────────────────────────────────────

    def patient_history(self, patient_id: int, limit: int = 50) -> list[dict]:
        """Every recorded decision for a patient, most recent first."""
        with self._connect() as conn, conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                """
                SELECT ar.*, p.code AS pharmacist_code
                  FROM alert_reviews ar
                  JOIN pharmacists p ON p.id = ar.pharmacist_id
                 WHERE ar.patient_id = %s
                 ORDER BY ar.reviewed_at DESC
                 LIMIT %s
                """,
                (patient_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def recurring_findings(self, patient_id: int, min_times: int = 2) -> list[dict]:
        """
        Findings that keep coming back for this patient.

        A finding reviewed repeatedly is a pattern worth surfacing: it usually
        means the prescription keeps being written the same way.
        """
        with self._connect() as conn, conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                """
                SELECT fingerprint, alert_type, max(title) AS title,
                       count(*) AS times_seen, max(reviewed_at) AS last_reviewed
                  FROM alert_reviews
                 WHERE patient_id = %s
                 GROUP BY fingerprint, alert_type
                HAVING count(*) >= %s
                 ORDER BY count(*) DESC, max(reviewed_at) DESC
                """,
                (patient_id, min_times),
            )
            return [dict(row) for row in cur.fetchall()]
