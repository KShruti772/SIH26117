import os
import sqlite3
import unittest
import json
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import status
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.audit import (
    AuditLogger,
    request_id_var,
    current_user_var,
    get_request_id,
    set_request_id,
    set_current_audit_user
)
from backend.security.auth import create_access_token

TEST_DB_PATH = "data/private/aegis_audit_test.db"

def get_test_db():
    conn = sqlite3.connect(TEST_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

class TestAegisAudit(unittest.TestCase):
    """Unit and API integration verification suite for the Audit Logging Ledger."""
    
    @classmethod
    def setUpClass(cls):
        # Override DB settings to test file
        cls.original_db_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = TEST_DB_PATH
        
        # Initialize test DB tables
        from backend.security.database import init_db
        init_db()
        
        # Override FastAPI app DB dependency
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
        # Clear audit log entries before every test
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.execute("DELETE FROM audit_logs")
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()
        
        # Reset context variables
        request_id_var.set("")
        current_user_var.set(None)

    def test_event_insertion_and_retrieval(self):
        """1, 2, 3, 5. Verify log_event appends correct fields and auto-generates timestamp."""
        AuditLogger.log_event(
            action="MODEL_LOAD",
            component="models.loaders.manager",
            status="success",
            user_id=42,
            username="operator1",
            role="user",
            resource="qwen2.5-coder-1.5b-instruct",
            duration_ms=150,
            metadata={"model_id": "qwen2.5-coder-1.5b-instruct"}
        )
        
        logs = AuditLogger.query_audit_logs(action="MODEL_LOAD")
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log["action"], "MODEL_LOAD")
        self.assertEqual(log["component"], "models.loaders.manager")
        self.assertEqual(log["status"], "success")
        self.assertEqual(log["user_id"], 42)
        self.assertEqual(log["username"], "operator1")
        self.assertEqual(log["role"], "user")
        self.assertEqual(log["resource"], "qwen2.5-coder-1.5b-instruct")
        self.assertEqual(log["duration_ms"], 150)
        self.assertIsNotNone(log["timestamp"])
        
        meta = json.loads(log["metadata_json"])
        self.assertEqual(meta["model_id"], "qwen2.5-coder-1.5b-instruct")

    def test_request_id_correlation(self):
        """4. Verify thread-local context variables bind request correlation IDs."""
        set_request_id("correlation-1234-uuid")
        self.assertEqual(get_request_id(), "correlation-1234-uuid")
        
        AuditLogger.log_event(
            action="RAG_SEARCH",
            component="rag.pipeline",
            status="success"
        )
        
        logs = AuditLogger.query_audit_logs(action="RAG_SEARCH")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["request_id"], "correlation-1234-uuid")

    def test_invalid_action_rejection(self):
        """9. Verify logger ignores actions not conforming to defined taxonomy."""
        AuditLogger.log_event(action="INVALID_UNAPPROVED_ACTION", component="core", status="success")
        logs = AuditLogger.query_audit_logs()
        self.assertEqual(len(logs), 0)

    def test_invalid_status_rejection(self):
        """10. Verify logger ignores statuses outside taxonomy (success/failure)."""
        AuditLogger.log_event(action="AUTH_LOGIN", component="core", status="unverified")
        logs = AuditLogger.query_audit_logs()
        self.assertEqual(len(logs), 0)

    def test_metadata_size_limit(self):
        """11. Verify metadata serialization is truncated to 1000 characters."""
        long_val = "x" * 2000
        # Include allowed key but with a very long value
        AuditLogger.log_event(
            action="OCR_PROCESS",
            component="multimodal",
            status="success",
            metadata={"filename": long_val}
        )
        logs = AuditLogger.query_audit_logs(action="OCR_PROCESS")
        self.assertEqual(len(logs), 1)
        meta_str = logs[0]["metadata_json"]
        self.assertLessEqual(len(meta_str), 1000)
        self.assertTrue(meta_str.endswith("..."))

    def test_confidential_parameters_exclusion(self):
        """12, 13, 14, 15, 16, 17. Verify that prompt text and secrets are filtered out of logs."""
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="sandbox",
            status="success",
            metadata={
                "model_id": "gemma",  # allowed key
                "prompt": "SELECT * FROM secrets_db",  # forbidden key
                "password": "mypassword123",  # forbidden key
                "token": "bearer-jwt-jwt",  # forbidden key
                "retrieved_text": "Grounding paragraph..."  # forbidden key
            }
        )
        logs = AuditLogger.query_audit_logs(action="SANDBOX_EXECUTION")
        self.assertEqual(len(logs), 1)
        meta = json.loads(logs[0]["metadata_json"])
        
        # Verify allowed remains
        self.assertEqual(meta["model_id"], "gemma")
        # Verify forbidden keys are completely stripped
        self.assertNotIn("prompt", meta)
        self.assertNotIn("password", meta)
        self.assertNotIn("token", meta)
        self.assertNotIn("retrieved_text", meta)

    def test_parameterized_sql_behavior(self):
        """8. Verify parameterized variables protect database from SQL injection."""
        injection_username = "operator'; DROP TABLE audit_logs; --"
        AuditLogger.log_event(
            action="AUTH_LOGIN",
            component="core",
            status="success",
            username=injection_username
        )
        
        logs = AuditLogger.query_audit_logs(action="AUTH_LOGIN")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["username"], injection_username)
        
        # Confirm table still exists
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM audit_logs")
        self.assertGreaterEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_fail_safe_policy(self):
        """20. Verify failures in database connection yield error messages but don't crash threads."""
        # Override settings db path to an invalid directory boundary path (e.g. read-only folder or empty)
        original_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = "/invalid_directory/invalid_file.db"
        try:
            # Should resolve safely without raising exceptions
            AuditLogger.log_event(action="AUTH_LOGIN", component="core", status="success")
        finally:
            settings.AUTH_DB_PATH = original_path

    def test_concurrency_logging(self):
        """7. Verify database connection pools handle highly concurrent write demands without locks/crashes."""
        def log_task(idx: int):
            AuditLogger.log_event(
                action="AUTH_LOGIN",
                component="concurrency_test",
                status="success",
                username=f"thread_user_{idx}"
            )
            
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(log_task, range(50))
            
        logs = AuditLogger.query_audit_logs(action="AUTH_LOGIN")
        self.assertEqual(len(logs), 50)

    def test_ledger_immutability(self):
        """Confirm that audit logger does not expose deletion or modification APIs."""
        self.assertFalse(hasattr(AuditLogger, "delete_event"))
        self.assertFalse(hasattr(AuditLogger, "update_event"))

    def test_audit_api_endpoint_rbac(self):
        """18, 19. Verify that /audit is restricted to admin role only."""
        # 1. Register users in test DB
        self.client.post("/auth/register", json={"username": "normal_user", "password": "securepassword123"})
        self.client.post("/auth/register", json={"username": "system_admin", "password": "securepassword123"})
        
        # 2. Get tokens
        user_tok = self.client.post("/auth/login", json={"username": "normal_user", "password": "securepassword123"}).json()["access_token"]
        admin_tok = self.client.post("/auth/login", json={"username": "system_admin", "password": "securepassword123"}).json()["access_token"]
        
        # 3. Log a test event
        AuditLogger.log_event(action="AUTH_LOGIN", component="core", status="success")
        
        # 4. Standard user accesses GET /audit -> 403 Forbidden
        res_user = self.client.get("/audit", headers={"Authorization": f"Bearer {user_tok}"})
        self.assertEqual(res_user.status_code, status.HTTP_403_FORBIDDEN)
        
        # 5. Admin accesses GET /audit -> 200 OK and returns logs list
        res_admin = self.client.get("/audit", headers={"Authorization": f"Bearer {admin_tok}"})
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        logs = res_admin.json()
        self.assertGreaterEqual(len(logs), 1)

if __name__ == "__main__":
    unittest.main()
