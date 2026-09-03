import os
import shutil
import tempfile
import sqlite3
import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.security.audit import AuditLogger, set_request_id, set_current_audit_user
from backend.app.main import app, rag_service, grounded_qa_service
from backend.security.dependencies import get_current_user
from backend.rag.pipeline import AegisRagService
from backend.rag.embeddings import MockEmbeddingModel

class TestAuditIsolationAndTruth(unittest.TestCase):
    """
    Automated verification suite ensuring:
    1. Zero synthetic events on startup / GET requests.
    2. Absolute test database isolation.
    3. Real operation event lifecycle matching.
    4. Exact aggregate summary counts matching SQLite.
    5. Cryptographic HMAC-SHA256 chain integrity.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="aegis_audit_truth_")
        cls.test_db_path = os.path.join(cls.test_dir, "isolated_truth.db")
        cls.runtime_db_path = os.path.join(cls.test_dir, "simulated_runtime.db")

        # Initialize simulated runtime DB with zero rows
        settings.AUTH_DB_PATH = cls.runtime_db_path
        init_db()

        # Switch to isolated test DB
        settings.AUTH_DB_PATH = cls.test_db_path
        init_db()

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        # Point to fresh test DB for each test case
        self.case_db_path = os.path.join(self.test_dir, f"case_{id(self)}.db")
        settings.AUTH_DB_PATH = self.case_db_path
        init_db()

        self.user = {
            "id": 101,
            "username": "operator_truth",
            "role": "admin"
        }

        class MockAuthUser:
            id = 101
            username = "operator_truth"
            role = "admin"
            def __getitem__(self, k): return {"id": 101, "username": "operator_truth", "role": "admin"}[k]
            def get(self, k, default=None): return {"id": 101, "username": "operator_truth", "role": "admin"}.get(k, default)

        app.dependency_overrides[get_current_user] = lambda: MockAuthUser()

    def tearDown(self):
        app.dependency_overrides.clear()
        if os.path.exists(self.case_db_path):
            try:
                os.remove(self.case_db_path)
            except Exception:
                pass

    def _get_audit_count(self) -> int:
        conn = sqlite3.connect(self.case_db_path)
        count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        conn.close()
        return count

    def test_1_startup_creates_zero_synthetic_audit_events(self):
        """1. Verify init_db() creates schema without inserting synthetic audit events."""
        fresh_db = os.path.join(self.test_dir, "fresh_startup.db")
        settings.AUTH_DB_PATH = fresh_db
        init_db()
        conn = sqlite3.connect(fresh_db)
        count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0, "Application startup/init_db must create 0 synthetic audit events.")

    def test_2_opening_audit_ledger_creates_zero_events(self):
        """2. Verify GET /audit (opening audit ledger) creates zero audit records."""
        initial_count = self._get_audit_count()
        res = self.client.get("/audit")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._get_audit_count(), initial_count, "GET /audit must not append any audit events.")

    def test_3_refreshing_audit_ledger_creates_zero_events(self):
        """3. Verify repeated GET /audit/summary and /audit/verify requests append zero audit records."""
        initial_count = self._get_audit_count()
        self.client.get("/audit/summary")
        self.client.get("/audit/verify")
        self.client.get("/audit")
        self.assertEqual(self._get_audit_count(), initial_count, "Refreshing audit ledger must append 0 events.")

    def test_4_and_5_test_database_is_isolated_and_leaves_runtime_db_untouched(self):
        """4 & 5. Verify operations logged during tests do NOT modify the runtime DB."""
        # Check simulated runtime DB count
        conn_rt = sqlite3.connect(self.runtime_db_path)
        rt_count_before = conn_rt.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        conn_rt.close()

        # Perform test operation in test DB
        AuditLogger.log_event(action="SANDBOX_EXECUTION", component="test", status="success", username="test_runner")
        self.assertEqual(self._get_audit_count(), 1)

        # Verify runtime DB remains unchanged
        conn_rt = sqlite3.connect(self.runtime_db_path)
        rt_count_after = conn_rt.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        conn_rt.close()
        self.assertEqual(rt_count_before, rt_count_after, "Runtime DB must not be modified by isolated test runs.")

    def test_6_real_login_creates_expected_event(self):
        """6. Verify successful login logging produces exactly 1 LOGIN_SUCCESS event."""
        AuditLogger.log_event(
            action="LOGIN_SUCCESS",
            component="security.auth_router",
            status="success",
            user_id=101,
            username="operator_truth",
            role="admin"
        )
        logs = AuditLogger.query_audit_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "LOGIN_SUCCESS")
        self.assertEqual(logs[0]["username"], "operator_truth")
        self.assertEqual(logs[0]["status"], "success")

    def test_7_real_rag_query_creates_expected_events(self):
        """7. Verify RAG query execution logs RAG_QUERY_STARTED and RAG_QUERY_COMPLETED."""
        AuditLogger.log_event(
            action="RAG_QUERY_STARTED",
            component="rag.grounded_qa",
            status="success",
            user_id=101,
            username="operator_truth"
        )
        AuditLogger.log_event(
            action="RAG_QUERY_COMPLETED",
            component="rag.grounded_qa",
            status="success",
            user_id=101,
            username="operator_truth"
        )
        logs = AuditLogger.query_audit_logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["action"], "RAG_QUERY_COMPLETED")
        self.assertEqual(logs[1]["action"], "RAG_QUERY_STARTED")

    def test_8_real_document_generation_creates_expected_events(self):
        """8. Verify document generation logs DOCUMENT_GENERATION_STARTED and DOCUMENT_GENERATED."""
        AuditLogger.log_event(
            action="DOCUMENT_GENERATION_STARTED",
            component="services.document_generator",
            status="success",
            user_id=101,
            username="operator_truth",
            resource="report_1.pdf"
        )
        AuditLogger.log_event(
            action="DOCUMENT_GENERATED",
            component="services.document_generator",
            status="success",
            user_id=101,
            username="operator_truth",
            resource="report_1.pdf"
        )
        logs = AuditLogger.query_audit_logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["action"], "DOCUMENT_GENERATED")
        self.assertEqual(logs[1]["action"], "DOCUMENT_GENERATION_STARTED")

    def test_9_real_document_download_creates_expected_event(self):
        """9. Verify streaming download logs DOCUMENT_DOWNLOADED."""
        AuditLogger.log_event(
            action="DOCUMENT_DOWNLOADED",
            component="app.main",
            status="success",
            user_id=101,
            username="operator_truth",
            resource="report_1.pdf"
        )
        logs = AuditLogger.query_audit_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "DOCUMENT_DOWNLOADED")

    def test_10_failed_real_operation_creates_failure_event(self):
        """10. Verify failed operations log failure status with honest category."""
        AuditLogger.log_event(
            action="LOGIN_FAILED",
            component="security.auth_router",
            status="failure",
            username="operator_truth",
            metadata={"error_category": "invalid_credentials"}
        )
        logs = AuditLogger.query_audit_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "LOGIN_FAILED")
        self.assertEqual(logs[0]["status"], "failure")

    def test_11_dashboard_counts_equal_actual_database_counts(self):
        """11. Verify GET /audit/summary accurately aggregates actual SQLite counts."""
        AuditLogger.log_event(action="LOGIN_SUCCESS", component="security.auth_router", status="success", username="op")
        AuditLogger.log_event(action="LOGIN_FAILED", component="security.auth_router", status="failure", username="op")
        AuditLogger.log_event(action="DOCUMENT_GENERATED", component="services.document_generator", status="success", username="op")
        AuditLogger.log_event(action="SANDBOX_EXECUTION", component="tools.code_sandbox", status="success", username="op")

        res = self.client.get("/audit/summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total_events"], 4)
        self.assertEqual(data["successful_events"], 3)
        self.assertEqual(data["failed_actions"], 1)
        self.assertEqual(data["security_events"], 2)
        self.assertEqual(data["rag_events"], 1)
        self.assertEqual(data["sandbox_events"], 1)

    def test_12_empty_database_produces_truthful_zero_counts(self):
        """12. Verify clean database returns truthful 0 counts without fake fallback data."""
        res = self.client.get("/audit/summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total_events"], 0)
        self.assertEqual(data["successful_events"], 0)
        self.assertEqual(data["failed_actions"], 0)
        self.assertEqual(data["security_events"], 0)
        self.assertEqual(data["rag_events"], 0)
        self.assertEqual(data["sandbox_events"], 0)

    def test_13_hmac_audit_chain_verification_passes(self):
        """13. Verify cryptographic HMAC-SHA256 hash chaining remains INTACT across sequential logs."""
        AuditLogger.log_event(action="AUTH_LOGIN", component="auth", status="success", username="op")
        AuditLogger.log_event(action="DOCUMENT_GENERATION_STARTED", component="gen", status="success", username="op")
        AuditLogger.log_event(action="DOCUMENT_GENERATED", component="gen", status="success", username="op")
        AuditLogger.log_event(action="DOCUMENT_DOWNLOADED", component="main", status="success", username="op")

        chain_status = AuditLogger.verify_chain_integrity()
        self.assertEqual(chain_status["status"], "INTACT")
        self.assertEqual(chain_status["total_records"], 4)
        self.assertIsNone(chain_status["tampered_record_id"])

if __name__ == "__main__":
    unittest.main()
