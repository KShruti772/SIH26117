import os
import sqlite3
import unittest
import hmac
import hashlib
from fastapi import status
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.audit import AuditLogger, request_id_var, current_user_var
from backend.security.auth import create_access_token, revoke_token, is_token_revoked
from backend.tools.code_sandbox.sandbox import SubprocessSandbox

TEST_DB_PATH = "data/private/aegis_phase7c_test.db"

def get_test_db():
    conn = sqlite3.connect(TEST_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

class TestPhase7CHardening(unittest.TestCase):
    """Unit test suite for Phase 7C security, cryptographic audit chaining, sandbox hardening, and token revocation."""
    
    @classmethod
    def setUpClass(cls):
        cls.original_db_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = TEST_DB_PATH
        
        from backend.security.database import init_db
        init_db()
        
        from backend.app.main import app
        from backend.security.database import get_db
        app.dependency_overrides[get_db] = get_test_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        from backend.app.main import app
        app.dependency_overrides.clear()
        settings.AUTH_DB_PATH = cls.original_db_path
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def setUp(self):
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.execute("DELETE FROM audit_logs")
        conn.execute("DELETE FROM revoked_tokens")
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()
        
        request_id_var.set("")
        current_user_var.set(None)

    def test_audit_hmac_hash_chaining_and_verification(self):
        """1. Verify audit logs record HMAC-SHA256 previous_hash/entry_hash and verify_chain_integrity returns INTACT."""
        AuditLogger.log_event(action="AUTH_LOGIN", component="test", status="success", username="user1")
        AuditLogger.log_event(action="CHAT_REQUEST", component="test", status="success", username="user1")

        logs = AuditLogger.query_audit_logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[1]["previous_hash"], "GENESIS_ROOT_HASH")
        self.assertIsNotNone(logs[1]["entry_hash"])

        res = AuditLogger.verify_chain_integrity()
        self.assertEqual(res["status"], "INTACT")
        self.assertEqual(res["total_records"], 2)

    def test_audit_tamper_detection(self):
        """2. Verify direct database record alteration breaks HMAC chain and triggers TAMPERED status."""
        AuditLogger.log_event(action="AUTH_LOGIN", component="test", status="success", username="user1")
        AuditLogger.log_event(action="CHAT_REQUEST", component="test", status="success", username="user1")

        # Mutate second record directly in SQLite
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.execute("UPDATE audit_logs SET status = 'failure' WHERE id = (SELECT MAX(id) FROM audit_logs)")
        conn.commit()
        conn.close()

        res = AuditLogger.verify_chain_integrity()
        self.assertEqual(res["status"], "TAMPERED")
        self.assertIsNotNone(res["tampered_record_id"])

    def test_token_revocation_on_logout(self):
        """3. Verify token revocation places token hash in blacklist and get_current_user rejects revoked token."""
        self.client.post("/auth/register", json={"username": "revoke_test_user", "password": "securepassword123"})
        tok = self.client.post("/auth/login", json={"username": "revoke_test_user", "password": "securepassword123"}).json()["access_token"]

        # Valid before logout
        res_before = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(res_before.status_code, status.HTTP_200_OK)

        # Logout
        self.client.post("/auth/logout", headers={"Authorization": f"Bearer {tok}"})
        self.assertTrue(is_token_revoked(tok))

        # Invalid after logout -> 401 Unauthorized
        res_after = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(res_after.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sandbox_ast_forbidden_imports(self):
        """4. Verify AST pre-execution inspection rejects code importing forbidden modules."""
        sandbox = SubprocessSandbox()
        forbidden_codes = [
            "import ctypes",
            "import subprocess",
            "import winreg",
            "from socket import socket",
            "import importlib"
        ]
        for code in forbidden_codes:
            res = sandbox.execute(code)
            self.assertFalse(res["success"])
            self.assertTrue("Security Rejection" in res["error"])

    def test_sandbox_socket_creation_blocked(self):
        """5. Verify runtime attempt to create a network socket inside sandbox is blocked with PermissionError."""
        sandbox = SubprocessSandbox()
        code = "import socket\ns = socket.socket()\n"
        res = sandbox.execute(code)
        self.assertFalse(res["success"])
        self.assertTrue("PermissionError" in res["stderr"] or "Security Rejection" in res["error"])

    def test_audit_verify_admin_only_rbac(self):
        """6. Verify /audit/verify endpoint requires admin role."""
        self.client.post("/auth/register", json={"username": "plain_user", "password": "securepassword123"})
        self.client.post("/auth/register", json={"username": "admin_audit_user", "password": "securepassword123"})

        user_tok = self.client.post("/auth/login", json={"username": "plain_user", "password": "securepassword123"}).json()["access_token"]
        admin_tok = self.client.post("/auth/login", json={"username": "admin_audit_user", "password": "securepassword123"}).json()["access_token"]

        # Plain user -> 403 Forbidden
        res_user = self.client.get("/audit/verify", headers={"Authorization": f"Bearer {user_tok}"})
        self.assertEqual(res_user.status_code, status.HTTP_403_FORBIDDEN)

        # Admin user -> 200 OK
        res_admin = self.client.get("/audit/verify", headers={"Authorization": f"Bearer {admin_tok}"})
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        self.assertEqual(res_admin.json()["status"], "INTACT")

if __name__ == "__main__":
    unittest.main()
