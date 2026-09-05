import os
import json
import sqlite3
import unittest
from datetime import datetime, timezone

from backend.app.config.settings import settings
from backend.security.database import get_db_path, init_db
from backend.security.audit import (
    AuditLogger,
    set_request_id,
    get_request_id,
    set_current_audit_user,
    ALLOWED_METADATA_KEYS
)


class TestAuditForensicDetails(unittest.TestCase):
    """
    Test suite verifying forensic audit metadata creation, sensitive data filtering,
    request ID correlation preservation, and backward compatibility.
    """

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.db_path = get_db_path()

    def setUp(self):
        # Reset context variables
        set_request_id("")
        set_current_audit_user(None)

    def _get_latest_audit_log(self, action: str):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM audit_logs WHERE action = ? ORDER BY id DESC LIMIT 1",
                (action,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def test_01_document_generation_forensic_details(self):
        """Test DOCUMENT_GENERATION_STARTED and DOCUMENT_GENERATED forensic details."""
        req_id = "req_docgen_test_001"
        set_request_id(req_id)
        doc_id = "rep_test_doc_123"
        conv_id = "conv_test_session_456"

        # 1. Started event
        AuditLogger.log_event(
            action="DOCUMENT_GENERATION_STARTED",
            component="services.document_generator",
            status="success",
            user_id=1,
            username="analyst_user",
            resource="test_report.docx",
            metadata={
                "document_id": doc_id,
                "artifact_id": doc_id,
                "conversation_id": conv_id,
                "output_format": "docx",
                "format": "docx",
                "title": "Industrial Risk Assessment",
                "source_count": 3,
                "status": "started"
            }
        )

        started_log = self._get_latest_audit_log("DOCUMENT_GENERATION_STARTED")
        self.assertIsNotNone(started_log)
        self.assertEqual(started_log["request_id"], req_id)
        self.assertEqual(started_log["username"], "analyst_user")
        
        meta = json.loads(started_log["metadata_json"])
        self.assertEqual(meta["document_id"], doc_id)
        self.assertEqual(meta["conversation_id"], conv_id)
        self.assertEqual(meta["output_format"], "docx")
        self.assertEqual(meta["format"], "docx")

        # 2. Completed event with correlated request_id
        AuditLogger.log_event(
            action="DOCUMENT_GENERATED",
            component="services.document_generator",
            status="success",
            user_id=1,
            username="analyst_user",
            resource="test_report.docx",
            metadata={
                "document_id": doc_id,
                "artifact_id": doc_id,
                "conversation_id": conv_id,
                "output_format": "docx",
                "format": "docx",
                "file_size": 24500,
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "source_count": 3,
                "status": "success",
                "result": "success"
            }
        )

        gen_log = self._get_latest_audit_log("DOCUMENT_GENERATED")
        self.assertIsNotNone(gen_log)
        self.assertEqual(gen_log["request_id"], req_id)
        
        meta_gen = json.loads(gen_log["metadata_json"])
        self.assertEqual(meta_gen["document_id"], doc_id)
        self.assertEqual(meta_gen["artifact_id"], doc_id)
        self.assertEqual(meta_gen["format"], "docx")
        self.assertEqual(meta_gen["status"], "success")
        self.assertEqual(meta_gen["result"], "success")
        self.assertEqual(meta_gen["file_size"], 24500)

    def test_02_document_downloaded_forensic_details(self):
        """Test DOCUMENT_DOWNLOADED forensic details."""
        req_id = "req_download_test_002"
        set_request_id(req_id)
        artifact_id = "art_compliance_report_88"

        AuditLogger.log_event(
            action="DOCUMENT_DOWNLOADED",
            component="app.main",
            status="success",
            user_id=2,
            username="engineer_user",
            resource="compliance_report.docx",
            metadata={
                "artifact_id": artifact_id,
                "document_id": artifact_id,
                "format": "docx",
                "output_format": "docx",
                "filename": "compliance_report.docx",
                "file_size": 51200
            }
        )

        log = self._get_latest_audit_log("DOCUMENT_DOWNLOADED")
        self.assertIsNotNone(log)
        self.assertEqual(log["request_id"], req_id)
        
        meta = json.loads(log["metadata_json"])
        self.assertEqual(meta["artifact_id"], artifact_id)
        self.assertEqual(meta["format"], "docx")
        self.assertEqual(meta["file_size"], 51200)

    def test_03_document_duplicate_detected_forensic_details(self):
        """Test DOCUMENT_DUPLICATE_DETECTED forensic details."""
        req_id = "req_dup_test_003"
        set_request_id(req_id)
        content_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        AuditLogger.log_event(
            action="DOCUMENT_DUPLICATE_DETECTED",
            component="rag.pipeline",
            status="success",
            user_id=1,
            username="admin_user",
            resource="duplicate_spec.pdf",
            metadata={
                "content_hash": content_hash,
                "result": "duplicate_detected",
                "action": "reused_canonical",
                "document_id": "doc_canonical_999",
                "canonical_document_id": "doc_canonical_999",
                "filename": "duplicate_spec.pdf"
            }
        )

        log = self._get_latest_audit_log("DOCUMENT_DUPLICATE_DETECTED")
        self.assertIsNotNone(log)
        self.assertEqual(log["request_id"], req_id)
        
        meta = json.loads(log["metadata_json"])
        self.assertEqual(meta["content_hash"], content_hash)
        self.assertEqual(meta["result"], "duplicate_detected")
        self.assertEqual(meta["canonical_document_id"], "doc_canonical_999")

    def test_04_model_inference_forensic_details(self):
        """Test MODEL_INFERENCE forensic details."""
        req_id = "req_model_test_004"
        set_request_id(req_id)

        AuditLogger.log_event(
            action="MODEL_INFERENCE",
            component="models.loaders.manager",
            status="success",
            user_id=1,
            username="operator1",
            resource="gemma3:4b",
            duration_ms=450,
            metadata={
                "model": "gemma3:4b",
                "model_id": "gemma3:4b",
                "task_type": "general_reasoning",
                "duration_ms": 450,
                "result": "success",
                "status": "success"
            }
        )

        log = self._get_latest_audit_log("MODEL_INFERENCE")
        self.assertIsNotNone(log)
        self.assertEqual(log["request_id"], req_id)
        self.assertEqual(log["duration_ms"], 450)
        
        meta = json.loads(log["metadata_json"])
        self.assertEqual(meta["model"], "gemma3:4b")
        self.assertEqual(meta["task_type"], "general_reasoning")

    def test_05_sandbox_execution_forensic_details(self):
        """Test SANDBOX_EXECUTION forensic details."""
        req_id = "req_sandbox_test_005"
        set_request_id(req_id)
        run_id = "sb_run_999a_test"

        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="sandbox.subprocess",
            status="success",
            user_id=1,
            username="operator1",
            resource=run_id,
            duration_ms=320,
            metadata={
                "run_id": run_id,
                "execution_id": run_id,
                "exit_code": 0,
                "duration_ms": 320,
                "result": "success",
                "status": "success",
                "timed_out": False,
                "artifact_count": 1
            }
        )

        log = self._get_latest_audit_log("SANDBOX_EXECUTION")
        self.assertIsNotNone(log)
        self.assertEqual(log["request_id"], req_id)
        self.assertEqual(log["duration_ms"], 320)
        
        meta = json.loads(log["metadata_json"])
        self.assertEqual(meta["run_id"], run_id)
        self.assertEqual(meta["exit_code"], 0)
        self.assertEqual(meta["duration_ms"], 320)
        self.assertEqual(meta["result"], "success")

    def test_06_authorization_failure_forensic_details(self):
        """Test AUTHORIZATION_FAILURE forensic details."""
        req_id = "req_auth_fail_006"
        set_request_id(req_id)
        target_doc = "doc_secret_finance_2026"

        AuditLogger.log_event(
            action="AUTHORIZATION_FAILURE",
            component="app.main",
            status="failure",
            user_id=3,
            username="unauthorized_guest",
            resource=target_doc,
            metadata={
                "resource_type": "document",
                "resource_id": target_doc,
                "action": "download",
                "result": "denied",
                "reason": "forbidden"
            }
        )

        log = self._get_latest_audit_log("AUTHORIZATION_FAILURE")
        self.assertIsNotNone(log)
        self.assertEqual(log["request_id"], req_id)
        self.assertEqual(log["status"], "failure")
        
        meta = json.loads(log["metadata_json"])
        self.assertEqual(meta["resource_type"], "document")
        self.assertEqual(meta["resource_id"], target_doc)
        self.assertEqual(meta["action"], "download")
        self.assertEqual(meta["result"], "denied")

    def test_07_sensitive_data_filtering_security_guarantee(self):
        """Verify passwords, tokens, raw file contents, and API keys are strictly rejected."""
        req_id = "req_sec_filter_007"
        set_request_id(req_id)

        # Attempt to pass forbidden fields and values
        AuditLogger.log_event(
            action="LOGIN_FAILED",
            component="security.auth",
            status="failure",
            user_id=4,
            username="malicious_actor",
            resource="auth/login",
            metadata={
                "password": "SuperSecretPassword123!",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy",
                "api_key": "sk-local-test-secret-key-12345",
                "bearer_token": "Bearer secret_bearer_token_xyz",
                "raw_file_buffer": b"CONFIDENTIAL INDUSTRIAL DESIGN BLUEPRINT CONTENT".hex(),
                "full_confidential_prompt": "Confidential prompt with secret blueprints",
                # Allowed metadata:
                "reason": "INVALID_CREDENTIALS",
                "error_category": "auth_failure"
            }
        )

        log = self._get_latest_audit_log("LOGIN_FAILED")
        self.assertIsNotNone(log)
        
        # Verify metadata does NOT contain any secret keys
        raw_meta = log["metadata_json"]
        self.assertNotIn("SuperSecretPassword123!", raw_meta)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", raw_meta)
        self.assertNotIn("sk-local-test-secret-key", raw_meta)
        self.assertNotIn("password", raw_meta)
        self.assertNotIn("access_token", raw_meta)
        self.assertNotIn("api_key", raw_meta)
        self.assertNotIn("bearer_token", raw_meta)
        self.assertNotIn("raw_file_buffer", raw_meta)
        self.assertNotIn("full_confidential_prompt", raw_meta)

        # Verify allowed safe fields were preserved
        meta = json.loads(raw_meta)
        self.assertEqual(meta.get("reason"), "INVALID_CREDENTIALS")
        self.assertEqual(meta.get("error_category"), "auth_failure")

    def test_08_backward_compatibility_empty_metadata(self):
        """Test backward compatibility: events with empty or null metadata log and load cleanly."""
        req_id = "req_compat_008"
        set_request_id(req_id)

        AuditLogger.log_event(
            action="LOGOUT",
            component="security.auth",
            status="success",
            user_id=1,
            username="operator1",
            resource="session",
            metadata=None
        )

        log = self._get_latest_audit_log("LOGOUT")
        self.assertIsNotNone(log)
        self.assertIsNone(log["metadata_json"])

    def test_09_cryptographic_hmac_chain_integrity(self):
        """Verify HMAC-SHA256 hash chaining remains completely intact across all forensic events."""
        res = AuditLogger.verify_chain_integrity()
        self.assertEqual(res["status"], "INTACT")
        self.assertIsNone(res["tampered_record_id"])
        self.assertGreater(res["total_records"], 0)


if __name__ == "__main__":
    unittest.main()
