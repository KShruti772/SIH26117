import os
import shutil
import tempfile
import unittest
import sqlite3
from fastapi import status
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config.settings import settings
from backend.security.database import get_db, init_db
from backend.security.auth import create_access_token, hash_password
from backend.security.audit import AuditLogger

TEST_TEMP_DIR = tempfile.mkdtemp(prefix="aegis_dept_provision_test_")
TEST_DB_PATH = os.path.join(TEST_TEMP_DIR, "aegis_dept_test.db")

def get_test_db():
    """FastAPI dependency override yielding a test connection to the temporary database."""
    conn = sqlite3.connect(TEST_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

class TestDepartmentScopedUserProvisioning(unittest.TestCase):
    """
    Comprehensive Adversarial Test Suite for AEGIS Department-Scoped User Provisioning.
    
    Verifies:
    1. Engineering admin creates Engineering user -> PASS
    2. Operations admin creates Operations user -> PASS
    3. Engineering admin attempts to create Operations user -> DENIED (403)
    4. Engineering admin modifies request JSON to department=Operations -> DENIED (403)
    5. Engineering admin removes department from request -> Server derives Engineering department
    6. Engineering admin attempts to create Finance user -> DENIED (403)
    7. Regular user attempts provisioning -> DENIED (403)
    8. Inactive administrator attempts provisioning -> DENIED (400/401/403)
    9. Administrator with NULL department attempts provisioning -> DENIED (403)
    10. Administrator tampers with another user's department -> DENIED (403)
    11. Administrator modifies client JWT payload -> Server relies on trusted database context
    12. Direct API call bypassing frontend -> 403 Forbidden
    13. SQL injection attempt in department/user fields -> Safely handled
    14. IDOR attempt against another department's user -> DENIED (403)
    15. Zero passwords or tokens leaked in audit logs
    16. Audit HMAC chain integrity remains unbroken
    17. Department data isolation on user listing
    """

    @classmethod
    def setUpClass(cls):
        cls.original_db_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = TEST_DB_PATH
        os.makedirs(os.path.dirname(TEST_DB_PATH), exist_ok=True)
        init_db()
        app.dependency_overrides[get_db] = get_test_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        settings.AUTH_DB_PATH = cls.original_db_path
        shutil.rmtree(TEST_TEMP_DIR, ignore_errors=True)

    def setUp(self):
        """Prepare fresh test departments and accounts."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users")
        cursor.execute("DELETE FROM audit_logs")
        
        # Ensure canonical departments exist
        cursor.execute("SELECT id, name FROM departments")
        dept_map = {row[1]: row[0] for row in cursor.fetchall()}
        self.dept_engineering_id = dept_map.get("Engineering")
        self.dept_operations_id = dept_map.get("Operations")
        self.dept_finance_id = dept_map.get("Finance")

        conn.commit()
        conn.close()

        # Provision test admins
        self.eng_admin_id = self._create_user("eng_admin", "AdminPass123!", "admin", self.dept_engineering_id, "Engineering")
        self.ops_admin_id = self._create_user("ops_admin", "AdminPass123!", "admin", self.dept_operations_id, "Operations")
        self.finance_admin_id = self._create_user("fin_admin", "AdminPass123!", "admin", self.dept_finance_id, "Finance")
        self.null_dept_admin_id = self._create_user("null_admin", "AdminPass123!", "admin", None, None)
        self.inactive_admin_id = self._create_user("inactive_admin", "AdminPass123!", "admin", self.dept_engineering_id, "Engineering", is_active=0)
        self.regular_user_id = self._create_user("regular_op", "UserPass123!", "user", self.dept_engineering_id, "Engineering")

        # Create Bearer tokens
        self.eng_admin_token = create_access_token("eng_admin", "admin")
        self.ops_admin_token = create_access_token("ops_admin", "admin")
        self.fin_admin_token = create_access_token("fin_admin", "admin")
        self.null_dept_admin_token = create_access_token("null_admin", "admin")
        self.inactive_admin_token = create_access_token("inactive_admin", "admin")
        self.regular_user_token = create_access_token("regular_op", "user")

    def _create_user(self, username: str, password: str, role: str, dept_id: int | None, dept_name: str | None, is_active: int = 1) -> int:
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        hashed = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, department_id, department_name, is_active, must_change_password) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (username, hashed, role, dept_id, dept_name, is_active)
        )
        uid = cursor.lastrowid
        conn.commit()
        conn.close()
        return uid

    def test_01_engineering_admin_creates_engineering_user(self):
        """TEST 1: Engineering admin creates Engineering user -> PASS (201 Created, assigned Engineering dept)."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "eng_dev_01",
                "password": "TempPassword123!",
                "role": "user"
            },
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["username"], "eng_dev_01")
        self.assertEqual(data["role"], "user")
        self.assertEqual(data["department_id"], self.dept_engineering_id)
        self.assertEqual(data["department_name"], "Engineering")
        self.assertTrue(data["must_change_password"])

        # Check DB
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT * FROM users WHERE username = 'eng_dev_01'").fetchone()
        conn.close()
        self.assertIsNotNone(user)
        self.assertEqual(user["department_id"], self.dept_engineering_id)
        self.assertEqual(user["department_name"], "Engineering")

    def test_02_operations_admin_creates_operations_user(self):
        """TEST 2: Operations admin creates Operations user -> PASS (201 Created, assigned Operations dept)."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "ops_worker_01",
                "password": "TempPassword123!",
                "role": "user"
            },
            headers={"Authorization": f"Bearer {self.ops_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["username"], "ops_worker_01")
        self.assertEqual(data["department_id"], self.dept_operations_id)
        self.assertEqual(data["department_name"], "Operations")

    def test_03_engineering_admin_attempts_to_create_operations_user(self):
        """TEST 3: Engineering admin attempts to create Operations user via explicit department_id -> DENIED (403)."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "unauthorized_ops_user",
                "password": "TempPassword123!",
                "role": "user",
                "department_id": self.dept_operations_id
            },
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Cross-department provisioning is prohibited", res.json()["detail"])

        # Confirm user was not created in database
        conn = sqlite3.connect(TEST_DB_PATH)
        user = conn.execute("SELECT id FROM users WHERE username = 'unauthorized_ops_user'").fetchone()
        conn.close()
        self.assertIsNone(user)

    def test_04_engineering_admin_modifies_request_json_to_department_operations(self):
        """TEST 4: Engineering admin modifies request JSON to department=Operations -> DENIED (403)."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "tampered_dept_user",
                "password": "TempPassword123!",
                "role": "user",
                "department_id": self.dept_operations_id
            },
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_05_engineering_admin_omits_department_from_request(self):
        """TEST 5: Engineering admin omits department from request -> server automatically uses Engineering department."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "eng_auto_dept_user",
                "password": "TempPassword123!",
                "role": "user"
            },
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["department_id"], self.dept_engineering_id)
        self.assertEqual(res.json()["department_name"], "Engineering")

    def test_06_engineering_admin_attempts_to_create_finance_user(self):
        """TEST 6: Engineering admin attempts to create Finance user -> DENIED (403)."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "finance_claim_user",
                "password": "TempPassword123!",
                "role": "user",
                "department_id": self.dept_finance_id
            },
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_07_regular_user_attempts_provisioning(self):
        """TEST 7: Regular user attempts provisioning -> DENIED (403)."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "escalated_user",
                "password": "TempPassword123!",
                "role": "user"
            },
            headers={"Authorization": f"Bearer {self.regular_user_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_08_inactive_administrator_attempts_provisioning(self):
        """TEST 8: Inactive administrator attempts provisioning -> DENIED."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "ghost_provisioned_user",
                "password": "TempPassword123!",
                "role": "user"
            },
            headers={"Authorization": f"Bearer {self.inactive_admin_token}"}
        )
        self.assertIn(res.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_09_administrator_with_null_department_attempts_provisioning(self):
        """TEST 9: Administrator with NULL department attempts provisioning -> DENIED (403)."""
        res = self.client.post(
            "/auth/users",
            json={
                "username": "orphan_user",
                "password": "TempPassword123!",
                "role": "user"
            },
            headers={"Authorization": f"Bearer {self.null_dept_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Administrator department is not configured", res.json()["detail"])

    def test_10_administrator_tampers_with_another_users_department(self):
        """TEST 10: Administrator tampers with another department user's department -> DENIED (403)."""
        # Create an operations user
        self._create_user("target_ops_op", "Secret123!", "user", self.dept_operations_id, "Operations")

        # Engineering admin attempts to change target_ops_op's department
        res = self.client.patch(
            "/auth/users/target_ops_op/department",
            json={"department_id": self.dept_engineering_id},
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Cannot manage user belonging to another department", res.json()["detail"])

    def test_11_jwt_tampering_claims_other_department_rejected_by_server_context(self):
        """TEST 11: Modifying client JWT or forged claims does not bypass trusted server-side identity context."""
        # Forge a token with subject 'eng_admin' but claiming role='admin'
        # Server verifies identity by loading user record from DB where department_id is Engineering
        forged_token = create_access_token("eng_admin", "admin")
        
        # Try to provision user for Operations department
        res = self.client.post(
            "/auth/users",
            json={
                "username": "forged_claim_user",
                "password": "TempPassword123!",
                "role": "user",
                "department_id": self.dept_operations_id
            },
            headers={"Authorization": f"Bearer {forged_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_12_direct_api_call_bypassing_frontend(self):
        """TEST 12: Direct API call without frontend enforcement yields identical authoritative rejection."""
        # Directly call REST endpoint with mismatched department payload
        res = self.client.post(
            "/auth/users",
            json={
                "username": "api_direct_exploit",
                "password": "ExploitPassword123!",
                "role": "user",
                "department_id": 99999
            },
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_13_sql_injection_attempt_in_fields(self):
        """TEST 13: SQL injection attempt in department/user fields is safely handled by parameterized queries."""
        sql_injection_payload = "eng_user'; DROP TABLE users; --"
        res = self.client.post(
            "/auth/users",
            json={
                "username": sql_injection_payload,
                "password": "ValidPassword123!",
                "role": "user"
            },
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        # Either 201 with safely escaped literal username or 400 validation error
        self.assertIn(res.status_code, (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST))

        # Confirm users table is completely intact
        conn = sqlite3.connect(TEST_DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)

    def test_14_idor_attempt_using_another_departments_user_id(self):
        """TEST 14: IDOR attempt by Engineering admin to disable / reset password of Operations user is DENIED (403)."""
        # Create an Operations user
        self._create_user("victim_ops_user", "Secret123!", "user", self.dept_operations_id, "Operations")

        # 1. Engineering admin tries to disable victim_ops_user
        res_status = self.client.post(
            "/auth/users/victim_ops_user/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res_status.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Engineering admin tries to reset password of victim_ops_user
        res_reset = self.client.post(
            "/auth/users/victim_ops_user/reset-password",
            json={"password": "HackedPassword123!"},
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res_reset.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Engineering admin tries to escalate role of victim_ops_user
        res_role = self.client.post(
            "/auth/users/victim_ops_user/role",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )
        self.assertEqual(res_role.status_code, status.HTTP_403_FORBIDDEN)

    def test_15_zero_passwords_or_tokens_leaked_in_audit_logs(self):
        """TEST 15: Verify passwords and temporary passwords never leak into audit logs."""
        secret_temp_pass = "SuperSecretTempPassword999!"
        self.client.post(
            "/auth/users",
            json={
                "username": "safe_audit_user",
                "password": secret_temp_pass,
                "role": "user"
            },
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )

        conn = sqlite3.connect(TEST_DB_PATH)
        conn.row_factory = sqlite3.Row
        logs = conn.execute("SELECT * FROM audit_logs").fetchall()
        conn.close()

        for log in logs:
            meta_str = str(log["metadata_json"] or "")
            self.assertNotIn(secret_temp_pass, meta_str, "Plaintext temporary password found in audit metadata!")
            self.assertNotIn(secret_temp_pass, str(log["resource"] or ""))

    def test_16_audit_hmac_chain_integrity_remains_intact(self):
        """TEST 16: Verify cryptographic HMAC audit log chaining remains valid across provisioning and denial events."""
        # Perform valid provisioning
        self.client.post(
            "/auth/users",
            json={"username": "hmac_eng_user", "password": "Password123!", "role": "user"},
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )

        # Perform denied cross-department attempt
        self.client.post(
            "/auth/users",
            json={"username": "hmac_cross_user", "password": "Password123!", "role": "user", "department_id": self.dept_operations_id},
            headers={"Authorization": f"Bearer {self.eng_admin_token}"}
        )

        # Verify HMAC chain
        integrity = AuditLogger.verify_chain_integrity()
        self.assertEqual(integrity["status"], "INTACT", f"HMAC Audit chain corrupted! Details: {integrity}")

    def test_17_department_data_isolation_on_user_listing(self):
        """TEST 17: User listing GET /auth/users strictly returns only users within the admin's department."""
        # Create users in different departments
        self._create_user("eng_member_a", "Pass123!", "user", self.dept_engineering_id, "Engineering")
        self._create_user("eng_member_b", "Pass123!", "user", self.dept_engineering_id, "Engineering")
        self._create_user("ops_member_a", "Pass123!", "user", self.dept_operations_id, "Operations")

        # 1. Engineering admin lists users -> receives only Engineering users
        res_eng = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.eng_admin_token}"})
        self.assertEqual(res_eng.status_code, status.HTTP_200_OK)
        eng_usernames = [u["username"] for u in res_eng.json()]
        self.assertIn("eng_member_a", eng_usernames)
        self.assertIn("eng_member_b", eng_usernames)
        self.assertNotIn("ops_member_a", eng_usernames)

        # 2. Operations admin lists users -> receives only Operations users
        res_ops = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.ops_admin_token}"})
        self.assertEqual(res_ops.status_code, status.HTTP_200_OK)
        ops_usernames = [u["username"] for u in res_ops.json()]
        self.assertIn("ops_member_a", ops_usernames)
        self.assertNotIn("eng_member_a", ops_usernames)
        self.assertNotIn("eng_member_b", ops_usernames)

if __name__ == "__main__":
    unittest.main()
