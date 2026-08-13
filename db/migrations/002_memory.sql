-- ============================================================================
-- MedFlow — Memory module (Week 6, Milestone 2)
--
-- What the agent remembers between interactions, and why:
--
--   pharmacists         WHO reviewed a finding. Memory is keyed by pharmacist
--                       as well as patient: one pharmacist accepting a risk is
--                       not a decision another pharmacist has made.
--
--   alert_reviews       The decisions themselves — append-only. Each row is one
--                       pharmacist's ruling on one finding for one patient at a
--                       point in time. Append-only rather than upsert so the
--                       history survives: it is a clinical audit trail, it
--                       supports "recurring pattern" questions, and a later
--                       decision must never erase the earlier one.
--
--   prescription_scans  What was screened and what was shown. Gives every alert
--                       a provenance ("this was on screen at 14:32"), and feeds
--                       latency/alert-volume reporting.
--
-- Findings are matched across scans by `fingerprint` — a stable, order-free
-- identity for a finding (see memory/fingerprint.py), NOT the per-run alert id.
-- ============================================================================

CREATE TABLE IF NOT EXISTS pharmacists (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(64) UNIQUE NOT NULL,   -- badge / login identifier
    name        VARCHAR(255),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE IF NOT EXISTS prescription_scans (
    id                  SERIAL PRIMARY KEY,
    patient_id          INT REFERENCES patients(id),
    pharmacist_id       INT REFERENCES pharmacists(id),
    prescribed          JSONB       NOT NULL,   -- prescription entries as scanned
    alerts              JSONB,                  -- the report shown to the pharmacist
    alert_count         INT         NOT NULL DEFAULT 0,
    overall_risk        VARCHAR(20),
    recommended_action  VARCHAR(30),
    latency_ms          NUMERIC,
    scanned_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scans_patient ON prescription_scans(patient_id);
CREATE INDEX IF NOT EXISTS idx_scans_pharmacist ON prescription_scans(pharmacist_id);
CREATE INDEX IF NOT EXISTS idx_scans_time ON prescription_scans(scanned_at DESC);


CREATE TABLE IF NOT EXISTS alert_reviews (
    id              SERIAL PRIMARY KEY,
    patient_id      INT REFERENCES patients(id)    NOT NULL,
    pharmacist_id   INT REFERENCES pharmacists(id) NOT NULL,
    scan_id         INT REFERENCES prescription_scans(id),

    fingerprint     VARCHAR(255) NOT NULL,  -- stable identity of the finding
    alert_type      VARCHAR(40)  NOT NULL,  -- interaction | cyp_competition | ...
    severity        VARCHAR(20)  NOT NULL,  -- clinical severity WHEN reviewed
    title           TEXT,                   -- readable snapshot for the audit trail
    drugs           TEXT[],                 -- canonical INNs involved

    -- acknowledged | overridden | prescriber_contacted | not_dispensed | dismissed
    decision        VARCHAR(30)  NOT NULL,
    note            TEXT,                   -- the pharmacist's justification
    reviewed_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- The hot path: "has THIS pharmacist already ruled on THIS finding for THIS
-- patient?" — asked once per scan for every fingerprint on screen.
CREATE INDEX IF NOT EXISTS idx_reviews_lookup
    ON alert_reviews(patient_id, pharmacist_id, fingerprint, reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_reviews_patient ON alert_reviews(patient_id);
CREATE INDEX IF NOT EXISTS idx_reviews_fingerprint ON alert_reviews(fingerprint);
