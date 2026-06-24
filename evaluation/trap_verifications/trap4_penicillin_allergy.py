"""
Trap 4 — Penicillin Allergy + Amoxicillin (cross-reactivity detection)
Expected:
  - amoxicillin linked to a penicillin allergy group
  - penicillin allergy group has cross-reactivity with cephalosporins
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _db import connect, pass_, fail

cur = connect().cursor()

# Check 1: amoxicillin belongs to penicillin allergy group
cur.execute("""
    SELECT ag.name
    FROM drug_allergy_groups dag
    JOIN drugs d ON d.id = dag.drug_id
    JOIN molecules m ON m.id = d.molecule_id AND m.inn = 'amoxicillin'
    JOIN allergy_groups ag ON ag.id = dag.allergy_group_id
""")
amox_groups = [r[0] for r in cur.fetchall()]

if not any("penicillin" in g.lower() for g in amox_groups):
    fail(f"amoxicillin not linked to a penicillin allergy group (found: {amox_groups})")

# Check 2: penicillin <-> cephalosporin cross-reactivity exists
cur.execute("""
    SELECT ag1.name, ag2.name
    FROM allergy_cross_reactivities acr
    JOIN allergy_groups ag1 ON ag1.id = acr.group_a_id
    JOIN allergy_groups ag2 ON ag2.id = acr.group_b_id
    WHERE ag1.name ILIKE '%penicillin%' OR ag2.name ILIKE '%penicillin%'
""")
cross = cur.fetchall()

if not cross:
    fail("no penicillin <-> cephalosporin cross-reactivity entry found")

has_ceph = any(
    "cephalosporin" in r[0].lower() or "cephalosporin" in r[1].lower()
    for r in cross
)
if not has_ceph:
    fail(f"penicillin cross-reactivity exists but not with cephalosporins: {cross}")

pass_(f"amoxicillin in {amox_groups}  cross-reactivity with cephalosporins confirmed")
