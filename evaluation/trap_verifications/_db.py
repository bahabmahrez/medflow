"""Shared DB connection helper for trap verification scripts."""
import os
import psycopg2

def connect():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "medflow"),
        user=os.getenv("POSTGRES_USER", "medflow"),
        password=os.getenv("POSTGRES_PASSWORD", "medflow"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
    )

def pass_(msg=""):
    print(f"PASS  {msg}")
    raise SystemExit(0)

def fail(msg=""):
    print(f"FAIL  {msg}")
    raise SystemExit(1)
