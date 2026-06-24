"""
Stress Test 5 — Unknown / Misspelled Drug Graceful Handling

Scenario: the engine receives a drug name that does not exist in the DB.
It must return empty results with no exception, no 500, and the query
must complete in under 500 ms.

What this tests: absence of data never crashes the lookup path; the system
fails gracefully with zero results rather than an error.

Inputs tested (all should return 0 rows):
  - 'fakedrugXYZ'         — completely fictional name
  - 'warfarinX'           — near-miss misspelling
  - ''                    — empty string
  - 'SELECT 1; --'        — SQL injection attempt
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

UNKNOWNS = [
    "fakedrugXYZ",
    "warfarinX",
    "",
    "SELECT 1; --",
]

TIMEOUT_MS = 500

conn = connect()
cur  = conn.cursor()

errors = []
for name in UNKNOWNS:
    t0 = time.monotonic()
    try:
        cur.execute("""
            SELECT di.severity_active
            FROM drug_interactions di
            JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = %s
            JOIN molecules b ON b.id = di.molecule_b_id
            UNION
            SELECT di.severity_active
            FROM drug_interactions di
            JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = %s
            JOIN molecules a ON a.id = di.molecule_a_id
        """, (name, name))
        rows = cur.fetchall()
        elapsed_ms = (time.monotonic() - t0) * 1000

        if rows:
            errors.append(f"input={name!r}: expected 0 rows, got {len(rows)} — possible injection or false match")
        if elapsed_ms > TIMEOUT_MS:
            errors.append(f"input={name!r}: query took {elapsed_ms:.0f} ms (limit {TIMEOUT_MS} ms)")

    except Exception as e:
        errors.append(f"input={name!r}: raised exception: {e}")

if errors:
    fail(" | ".join(errors))

pass_(f"all {len(UNKNOWNS)} unknown inputs returned 0 rows with no exception")
