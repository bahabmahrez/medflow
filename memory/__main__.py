"""
Create the memory tables.

    python -m memory            # apply db/migrations/002_memory.sql
    python -m memory --check    # report whether the tables exist

The migration is idempotent. It needs to be run explicitly because Postgres
only executes docker-entrypoint-initdb.d on a *fresh* volume, and this project's
volume already exists.
"""
import argparse
import sys

from .store import MemoryStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise the MedFlow memory schema")
    parser.add_argument("--check", action="store_true", help="only report status")
    args = parser.parse_args()

    store = MemoryStore()
    try:
        if args.check:
            ready = store.schema_ready()
            print("memory schema:", "ready" if ready else "MISSING")
            sys.exit(0 if ready else 1)

        store.init_schema()
        print("memory schema applied (pharmacists, prescription_scans, alert_reviews)")
    except Exception as exc:
        print(f"ERROR: {exc}")
        print("Is PostgreSQL running?  docker compose up -d")
        sys.exit(2)


if __name__ == "__main__":
    main()
