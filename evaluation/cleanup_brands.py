"""
One-time script to ensure Kardegic (aspirin) and Depakine (valproate) brand
names exist in the drugs table.

These are already handled in knowledge_base/DB_loaders/load_pct_brands.py
as FALLBACKS, but if the DB hasn't been re-loaded since that fix was added,
they may be missing. This script checks and inserts them if absent.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import psycopg2
except ImportError:
    try:
        import psycopg2_binary as psycopg2  # type: ignore[import-not-found]
    except ImportError:
        print("psycopg2 is required. Install: pip install psycopg2-binary")
        sys.exit(1)

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)
cur = conn.cursor()

FALLBACKS = [
    ("aspirin",   "Kardegic", "Kardegic", "B01AC06", "tablet"),
    ("valproate", "Depakine", "Depakine", "N03AG01", "tablet"),
]

inserted = skipped = 0

for inn, brand_name, brand_name_tn, atc_code, dosage_form in FALLBACKS:
    cur.execute("SELECT id FROM molecules WHERE inn = %s", (inn,))
    mol = cur.fetchone()
    if not mol:
        print(f"  SKIP {inn}: molecule not found in DB — run loaders first")
        skipped += 1
        continue

    mol_id = mol[0]

    # Check if a drugs row with this brand_name already exists
    cur.execute(
        "SELECT id FROM drugs WHERE molecule_id = %s AND brand_name ILIKE %s",
        (mol_id, brand_name),
    )
    if cur.fetchone():
        print(f"  OK  {inn} / {brand_name}: already present")
        skipped += 1
        continue

    cur.execute("""
        INSERT INTO drugs (molecule_id, brand_name, brand_name_tn, atc_code, dosage_form)
        VALUES (%s, %s, %s, %s, %s)
    """, (mol_id, brand_name, brand_name_tn, atc_code, dosage_form))
    print(f"  INSERTED {inn:20s} -> {brand_name}")
    inserted += 1

conn.commit()
print(f"\nDone. {inserted} inserted, {skipped} skipped")
cur.close()
conn.close()

