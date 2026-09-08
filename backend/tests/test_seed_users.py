import os
import shutil
import tempfile
import sqlite3
import unittest

import importlib
from backend.app.config.settings import settings
from backend.security.auth import verify_password

seed_module = importlib.import_module("scripts.seed-users")
seed_demo_users = seed_module.seed_demo_users
DEMO_ACCOUNTS = seed_module.DEMO_ACCOUNTS

TEST_TEMP_DIR = tempfile.mkdtemp(prefix="aegis_seed_test_")
TEST_SEED_DB_PATH = os.path.join(TEST_TEMP_DIR, "aegis_seed_test.db")

class TestSeedUsers(unittest.TestCase):
    """Unit test verification suite for persistent demo user account seeding."""

    @classmethod
    def setUpClass(cls):
        cls.original_db_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = TEST_SEED_DB_PATH

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls.original_db_path
        shutil.rmtree(TEST_TEMP_DIR, ignore_errors=True)

    def setUp(self):
        from backend.security.database import init_db
        init_db()
        conn = sqlite3.connect(TEST_SEED_DB_PATH)
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()

    def test_seed_demo_users_creates_all_six_accounts(self):
        """1, 2, 3, 4. Verify seed operation creates 10 active accounts (5 admin, 5 user)."""
        res = seed_demo_users(db_path=TEST_SEED_DB_PATH)
        self.assertEqual(res["created"], len(DEMO_ACCOUNTS))
        self.assertEqual(res["existing"], 0)

        conn = sqlite3.connect(TEST_SEED_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users ORDER BY id ASC")
        users = cursor.fetchall()
        self.assertEqual(len(users), len(DEMO_ACCOUNTS))

        admin_users = [u for u in users if u["role"] == "admin"]
        user_users = [u for u in users if u["role"] == "user"]

        self.assertEqual(len(admin_users), 5)
        admin_names = sorted([u["username"] for u in admin_users])
        self.assertEqual(admin_names, ["aegis_admin", "engineering_admin", "hse_admin", "operations_admin", "procurement_admin"])

        self.assertEqual(len(user_users), 5)
        user_names = [u["username"] for u in user_users]
        self.assertEqual(user_names, ["operator1", "operator2", "operator3", "operator4", "operator5"])

        # Verify all accounts are active
        for u in users:
            self.assertEqual(u["is_active"], 1)

        conn.close()

    def test_seed_passwords_are_securely_hashed_and_authenticate(self):
        """5, 6. Verify passwords are stored as bcrypt hashes and authenticate properly."""
        seed_demo_users(db_path=TEST_SEED_DB_PATH)

        conn = sqlite3.connect(TEST_SEED_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        for item in DEMO_ACCOUNTS:
            username, role, plain_password = item[0], item[1], item[2]
            cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            self.assertIsNotNone(row)

            stored_hash = row["password_hash"]
            # Plaintext password is never stored
            self.assertNotEqual(stored_hash, plain_password)
            self.assertTrue(stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$"))

            # Authentication check
            self.assertTrue(verify_password(plain_password, stored_hash))
            # Wrong password check
            self.assertFalse(verify_password("WrongPassword123!", stored_hash))

        conn.close()

    def test_idempotent_reexecution_preserves_existing_users(self):
        """7, 8. Verify running seed operation twice does not duplicate records or overwrite passwords/roles."""
        res1 = seed_demo_users(db_path=TEST_SEED_DB_PATH)
        self.assertEqual(res1["created"], len(DEMO_ACCOUNTS))

        # Re-execution
        res2 = seed_demo_users(db_path=TEST_SEED_DB_PATH)
        self.assertEqual(res2["created"], 0)
        self.assertEqual(res2["existing"], len(DEMO_ACCOUNTS))

        conn = sqlite3.connect(TEST_SEED_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        total_count = cursor.fetchone()[0]
        self.assertEqual(total_count, len(DEMO_ACCOUNTS))

        conn.close()

    def test_database_is_local_sqlite(self):
        """9. Verify database file remains local SQLite file."""
        seed_demo_users(db_path=TEST_SEED_DB_PATH)
        self.assertTrue(os.path.exists(TEST_SEED_DB_PATH))

        conn = sqlite3.connect(TEST_SEED_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT sqlite_version()")
        ver = cursor.fetchone()
        self.assertIsNotNone(ver)
        self.assertIsNotNone(ver[0])
        conn.close()

if __name__ == "__main__":
    unittest.main()
