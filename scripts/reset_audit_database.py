#!/usr/bin/env python3
"""Safely inspect or reset the development audit ledger."""

import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.config.settings import settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="Delete all audit rows after checking development mode.")
    args = parser.parse_args()

    if settings.APP_ENV == "production":
        parser.error("Refusing to reset the audit ledger in production.")

    import sqlite3
    from backend.security.database import get_db_path

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        print(f"Audit records: {count}")
        if not args.confirm:
            print("Dry run only. Re-run with --confirm in development to remove audit rows.")
            return 0
        conn.execute("DELETE FROM audit_logs")
        conn.commit()
        print(f"Removed {count} audit records from {db_path}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())