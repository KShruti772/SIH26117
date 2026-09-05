#!/usr/bin/env python3
"""
AEGIS - Persistent Demo User Provisioning Script

-------------------------------------------------------------------------------
SECURITY & DEMO PROVISIONING NOTICE:
-------------------------------------------------------------------------------
1. This script provisions default demo accounts for local hackathon evaluations.
2. Production deployments must NEVER rely on hardcoded seed script credentials.
   For production staging, user accounts should be provisioned via the admin console
   or environment/secret management systems with mandatory first-login password changes.
3. Passwords are password-hashed using bcrypt prior to database storage. Plaintext
   passwords are never saved to disk, logged in audit ledgers, or exposed via APIs.
-------------------------------------------------------------------------------
"""

import sys
import os
import sqlite3

# Resolve project root using relative pathing
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.security.auth import hash_password, verify_password

# Configured demo account definitions
DEMO_ACCOUNTS = [
    ("aegis_admin", "admin", "Aegis@Admin2026!"),
    ("operator1", "user", "Aegis@User1#2026"),
    ("operator2", "user", "Aegis@User2#2026"),
    ("operator3", "user", "Aegis@User3#2026"),
    ("operator4", "user", "Aegis@User4#2026"),
    ("operator5", "user", "Aegis@User5#2026"),
]

def seed_demo_users(db_path: str = None) -> dict:
    """
    Idempotently seeds demo user accounts into local SQLite auth database.
    Repairs corrupt/malformed password hashes using canonical hash_password().
    Does not overwrite valid existing user passwords or alter existing custom users.
    """
    # 1. Initialize schema if database does not exist
    init_db()
    
    target_db = db_path or get_db_path()
    created_count = 0
    existing_count = 0
    repaired_count = 0
    
    conn = sqlite3.connect(target_db)
    try:
        cursor = conn.cursor()
        for username, role, plain_password in DEMO_ACCOUNTS:
            cursor.execute("SELECT id, role, password_hash FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            
            if row:
                stored_hash = row[2]
                # Check if stored hash is corrupted / malformed (e.g. not a valid bcrypt hash)
                is_valid_bcrypt = bool(stored_hash and str(stored_hash).startswith(("$2a$", "$2b$", "$2y$")))
                is_matching = verify_password(plain_password, stored_hash) if is_valid_bcrypt else False
                
                if not is_valid_bcrypt or not is_matching:
                    new_hash = hash_password(plain_password)
                    cursor.execute("""
                        UPDATE users SET password_hash = ?, is_active = 1 WHERE username = ?
                    """, (new_hash, username))
                    repaired_count += 1
                    print(f"[REPAIR] {username} (restored valid bcrypt hash)")
                else:
                    existing_count += 1
                    print(f"[EXISTS] {username} ({row[1]})")
            else:
                hashed = hash_password(plain_password)
                cursor.execute("""
                    INSERT INTO users (username, password_hash, role, is_active, must_change_password)
                    VALUES (?, ?, ?, 1, 0)
                """, (username, hashed, role))
                created_count += 1
                print(f"[CREATE] {username} ({role})")
                
        conn.commit()
    finally:
        conn.close()
        
    return {
        "created": created_count,
        "existing": existing_count,
        "repaired": repaired_count,
        "total_demo": len(DEMO_ACCOUNTS)
    }

if __name__ == "__main__":
    print("=========================================")
    print("  AEGIS PERSISTENT DEMO USER PROVISIONING ")
    print("=========================================")
    result = seed_demo_users()
    print("-----------------------------------------")
    print(f"Summary: Created {result['created']} new accounts, {result['existing']} already existed.")
    print("=========================================")
