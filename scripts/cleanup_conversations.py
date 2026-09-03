#!/usr/bin/env python3
"""
AEGIS - Safe Conversation & Message Cleanup Migration Script
Removes synthetic/test/demo conversations generated during test runs while strictly preserving real operator data.
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.config.settings import settings
from backend.security.database import get_db_path

def cleanup_synthetic_conversations(dry_run: bool = True) -> dict:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Known test usernames from test suites
    test_usernames = (
        "testuser", "phase4_qa_a", "phase4_qa_b", "safety_lead",
        "analyst_1", "operator_a", "operator_b", "usera", "user_a",
        "user_b", "normal_user", "system_admin", "registered_user",
        "me_user", "login_user", "duplicate_user", "unknown_user",
        "inactive_user", "valid_user", "admin_test", "operator1"
    )

    placeholders = ", ".join(["?"] * len(test_usernames))

    cursor = conn.cursor()

    # Identify test conversations
    cursor.execute(f"""
        SELECT id, user_id, username, title, created_at 
        FROM conversations 
        WHERE username IN ({placeholders}) 
           OR username IS NULL 
           OR title LIKE '%Compute Array Sum%'
           OR title LIKE '%Test Session%'
           OR title LIKE '%Operator A%'
           OR title LIKE '%Operator B%'
           OR title LIKE '%Secret Session%'
           OR title LIKE '%Safety Review%'
    """, test_usernames)
    synthetic_convs = cursor.fetchall()

    # Real conversations
    cursor.execute(f"""
        SELECT id, user_id, username, title, created_at 
        FROM conversations 
        WHERE username NOT IN ({placeholders}) 
          AND username IS NOT NULL
          AND title NOT LIKE '%Compute Array Sum%'
          AND title NOT LIKE '%Test Session%'
          AND title NOT LIKE '%Operator A%'
          AND title NOT LIKE '%Operator B%'
          AND title NOT LIKE '%Secret Session%'
          AND title NOT LIKE '%Safety Review%'
    """, test_usernames)
    real_convs = cursor.fetchall()

    synthetic_ids = [c["id"] for c in synthetic_convs]

    print(f"Total conversations in DB: {len(synthetic_convs) + len(real_convs)}")
    print(f"Synthetic/test conversations identified for removal: {len(synthetic_convs)}")
    print(f"Real operator conversations preserved: {len(real_convs)}")

    if dry_run:
        print("\n[DRY RUN] No database records modified.")
        conn.close()
        return {
            "synthetic_identified": len(synthetic_convs),
            "real_preserved": len(real_convs),
            "deleted": 0
        }

    # Execute deletion of synthetic conversations & associated messages
    if synthetic_ids:
        id_placeholders = ", ".join(["?"] * len(synthetic_ids))
        cursor.execute(f"DELETE FROM messages WHERE conversation_id IN ({id_placeholders})", synthetic_ids)
        cursor.execute(f"DELETE FROM conversations WHERE id IN ({id_placeholders})", synthetic_ids)
        conn.commit()

    total_remaining = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    total_messages_remaining = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()

    print(f"\n[CLEANUP COMPLETED] Removed {len(synthetic_ids)} conversations.")
    print(f"Remaining conversations: {total_remaining}")
    print(f"Remaining messages: {total_messages_remaining}")

    return {
        "synthetic_identified": len(synthetic_convs),
        "real_preserved": len(real_convs),
        "deleted": len(synthetic_ids),
        "remaining_conversations": total_remaining,
        "remaining_messages": total_messages_remaining
    }

if __name__ == "__main__":
    is_dry_run = "--execute" not in sys.argv
    cleanup_synthetic_conversations(dry_run=is_dry_run)
