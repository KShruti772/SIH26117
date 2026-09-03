import os
import shutil
import tempfile
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

TEST_TEMP_DIR = tempfile.mkdtemp(prefix="aegis_audit_test_")
TEST_DB_PATH = os.path.join(TEST_TEMP_DIR, "aegis_audit_test.db")

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
        shutil.rmtree(TEST_TEMP_DIR, ignore_errors=True)

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
        """14, 15. Verify that /audit and /audit/summary are restricted to admin role only."""
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

        # Standard user accesses GET /audit/summary -> 403 Forbidden
        res_user_sum = self.client.get("/audit/summary", headers={"Authorization": f"Bearer {user_tok}"})
        self.assertEqual(res_user_sum.status_code, status.HTTP_403_FORBIDDEN)
        
        # 5. Admin accesses GET /audit -> 200 OK and returns logs list
        res_admin = self.client.get("/audit", headers={"Authorization": f"Bearer {admin_tok}"})
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        logs = res_admin.json()
        self.assertGreaterEqual(len(logs), 1)

        # Admin accesses GET /audit/summary -> 200 OK
        res_admin_sum = self.client.get("/audit/summary", headers={"Authorization": f"Bearer {admin_tok}"})
        self.assertEqual(res_admin_sum.status_code, status.HTTP_200_OK)

    def test_no_audit_mutation_endpoint_exists(self):
        """16. Verify no application API exists for updating or deleting audit logs."""
        self.assertFalse(hasattr(AuditLogger, "delete_event"))
        self.assertFalse(hasattr(AuditLogger, "update_event"))

        # Verify API route table has no PUT/PATCH/DELETE endpoints for /audit
        from backend.app.main import app
        audit_mutation_routes = [
            route for route in app.routes
            if hasattr(route, "path") and route.path.startswith("/audit") and any(m in route.methods for m in ["PUT", "PATCH", "DELETE"])
        ]
        self.assertEqual(len(audit_mutation_routes), 0)

    def test_empty_audit_ledger_returns_empty_list(self):
        """18. Verify empty audit ledger returns clean empty list []."""
        logs = AuditLogger.query_audit_logs()
        self.assertEqual(logs, [])

    def test_login_events_audited(self):
        """1, 2. Verify successful and failed logins create LOGIN_SUCCESS and LOGIN_FAILED events."""
        self.client.post("/auth/register", json={"username": "login_test_user", "password": "securepassword123"})
        
        # Failed login
        self.client.post("/auth/login", json={"username": "login_test_user", "password": "wrongpassword"})
        logs_failed = AuditLogger.query_audit_logs(action="LOGIN_FAILED")
        self.assertGreaterEqual(len(logs_failed), 1)
        self.assertEqual(logs_failed[0]["status"], "failure")

        # Successful login
        self.client.post("/auth/login", json={"username": "login_test_user", "password": "securepassword123"})
        logs_success = AuditLogger.query_audit_logs(action="LOGIN_SUCCESS")
        self.assertGreaterEqual(len(logs_success), 1)
        self.assertEqual(logs_success[0]["status"], "success")

    def test_each_login_attempt_creates_one_canonical_event(self):
        """A login attempt must not create duplicate legacy and canonical rows."""
        self.client.post("/auth/register", json={"username": "one_event_user", "password": "securepassword123"})

        self.client.post("/auth/login", json={"username": "one_event_user", "password": "wrongpassword"})
        failed = AuditLogger.query_audit_logs(action="LOGIN_FAILED", username="one_event_user")
        self.assertEqual(len(failed), 1)

        self.client.post("/auth/login", json={"username": "one_event_user", "password": "securepassword123"})
        successful = AuditLogger.query_audit_logs(action="LOGIN_SUCCESS", username="one_event_user")
        self.assertEqual(len(successful), 1)

    def test_logout_event_audited(self):
        """3. Verify logout creates LOGOUT audit event."""
        self.client.post("/auth/register", json={"username": "logout_test_user", "password": "securepassword123"})
        tok = self.client.post("/auth/login", json={"username": "logout_test_user", "password": "securepassword123"}).json()["access_token"]
        
        self.client.post("/auth/logout", headers={"Authorization": f"Bearer {tok}"})
        logs = AuditLogger.query_audit_logs(action="AUTH_LOGOUT")
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]["username"], "logout_test_user")

    def test_password_change_audited(self):
        """4. Verify password change creates PASSWORD_CHANGED audit event."""
        self.client.post("/auth/register", json={"username": "pwd_test_user", "password": "securepassword123"})
        tok = self.client.post("/auth/login", json={"username": "pwd_test_user", "password": "securepassword123"}).json()["access_token"]
        
        self.client.post(
            "/auth/change-password",
            json={"old_password": "securepassword123", "new_password": "newsecurepassword123"},
            headers={"Authorization": f"Bearer {tok}"}
        )
        logs = AuditLogger.query_audit_logs(action="AUTH_CHANGE_PASSWORD")
        self.assertGreaterEqual(len(logs), 1)

    def test_model_operations_audited(self):
        """9, 10. Verify model select and model test create MODEL_SELECTED and MODEL_TESTED audit events."""
        self.client.post("/auth/register", json={"username": "admin_model_user", "password": "securepassword123"})
        admin_tok = self.client.post("/auth/login", json={"username": "admin_model_user", "password": "securepassword123"}).json()["access_token"]
        
        # Model select
        self.client.post("/models/select", json={"model_id": "gemma3:4b"}, headers={"Authorization": f"Bearer {admin_tok}"})
        logs_sel = AuditLogger.query_audit_logs(action="MODEL_SELECTED")
        self.assertGreaterEqual(len(logs_sel), 1)

        # Model test
        self.client.post("/models/test", json={"model_id": "gemma3:4b"}, headers={"Authorization": f"Bearer {admin_tok}"})
        logs_test = AuditLogger.query_audit_logs(action="MODEL_TESTED")
        self.assertGreaterEqual(len(logs_test), 1)

    def test_rag_and_sandbox_audited(self):
        """12, 13. Verify RAG query and sandbox execution create RAG_QUERY and SANDBOX_EXECUTION audit events."""
        self.client.post("/auth/register", json={"username": "rag_user", "password": "securepassword123"})
        tok = self.client.post("/auth/login", json={"username": "rag_user", "password": "securepassword123"}).json()["access_token"]

        # RAG Query
        self.client.post("/documents/query", json={"query": "test query", "top_k": 2}, headers={"Authorization": f"Bearer {tok}"})
        logs_rag = AuditLogger.query_audit_logs(action="RAG_QUERY")
        self.assertGreaterEqual(len(logs_rag), 1)

        # Sandbox Execution
        self.client.post("/sandbox/execute", json={"code": "print('hello')", "timeout_seconds": 5}, headers={"Authorization": f"Bearer {tok}"})
        logs_sb = AuditLogger.query_audit_logs(action="SANDBOX_EXECUTION")
        self.assertGreaterEqual(len(logs_sb), 1)

    def test_sandbox_audit_contains_actual_result(self):
        """The route audit event records the subprocess result, not placeholders."""
        self.client.post("/auth/register", json={"username": "sandbox_audit_user", "password": "securepassword123"})
        tok = self.client.post("/auth/login", json={"username": "sandbox_audit_user", "password": "securepassword123"}).json()["access_token"]

        response = self.client.post("/sandbox/execute", json={"code": "print('actual output')"}, headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(response.status_code, 200)
        event = AuditLogger.query_audit_logs(action="SANDBOX_EXECUTION", username="sandbox_audit_user")[0]
        metadata = json.loads(event["metadata_json"])
        self.assertEqual(metadata["stdout"], "actual output\n")
        self.assertEqual(metadata["stderr"], "")
        self.assertEqual(metadata["sandbox_exit_code"], 0)
        self.assertEqual(event["status"], "success")

if __name__ == "__main__":
    unittest.main()
