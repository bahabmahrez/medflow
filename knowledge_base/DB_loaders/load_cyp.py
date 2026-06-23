import csv, psycopg2, os

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "medflow"),
    user=os.getenv("POSTGRES_USER", "medflow"),
    password=os.getenv("POSTGRES_PASSWORD", "medflow"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
)
cur = conn.cursor()

loaded = 0
# Data file lives under knowledge_base/sources/dataset/...
csv_path = os.path.join(os.path.dirname(__file__), "../sources/dataset/chembl_drug_data.csv")

with open(csv_path, newline="") as f:
    for row in csv.DictReader(f):
        if not row["cyp_relationships"]:
            continue
        cur.execute("SELECT id FROM molecules WHERE inn = %s", (row["inn_name"],))
        mol = cur.fetchone()
        if not mol:
            continue
        for entry in row["cyp_relationships"].split(" | "):
            parts = entry.split(":")
            if len(parts) < 2:
                continue
            enzyme, rel = parts[0].strip(), parts[1].strip().lower()
            cur.execute("""
                INSERT INTO cyp_relationships (molecule_id, enzyme, relationship)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (mol[0], enzyme, rel))
            loaded += 1

conn.commit()
print(f"Loaded {loaded} CYP rows")
cur.close()
conn.close()
