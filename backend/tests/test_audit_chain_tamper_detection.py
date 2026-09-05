import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.app.config.settings import settings
from backend.security.audit import AuditLogger
from backend.security.database import init_db, get_db_path


class TestAuditChainTamperDetection(unittest.TestCase):
    """Comprehensive test suite validating HMAC-SHA256 audit chain integrity and tamper detection."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="aegis_audit_test_")
        self.db_path = os.path.join(self.temp_dir, "test_auth.db")
        self.db_patch = patch("backend.security.database.get_db_path", return_value=self.db_path)
        self.audit_db_patch = patch("backend.security.audit.get_db_path", return_value=self.db_path)
        self.db_patch.start()
        self.audit_db_patch.start()
        init_db()

        # Seed initial legitimate chain of events
        AuditLogger.log_event(
            action="LOGIN_SUCCESS",
            component="security.auth",
            status="success",
            user_id=1,
            username="admin_user",
            role="admin",
            resource="auth/login",
            metadata={"reason": "standard_login"}
        )
        AuditLogger.log_event(
            action="DOCUMENT_INGESTION_STARTED",
            component="rag.pipeline",
            status="success",
            user_id=1,
            username="admin_user",
            role="admin",
            resource="turbofan_schematics.pdf",
            metadata={"filename": "turbofan_schematics.pdf", "file_size": 1048576}
        )
        AuditLogger.log_event(
            action="DOCUMENT_GENERATION_STARTED",
            component="services.document_generator",
            status="success",
            user_id=2,
            username="operator1",
            role="user",
            resource="report_2026.docx",
            metadata={"document_id": "doc_rep_101", "output_format": "docx"}
        )
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="sandbox.subprocess",
            status="success",
            user_id=2,
            username="operator1",
            role="user",
            resource="sb_run_101",
            duration_ms=250,
            metadata={"run_id": "sb_run_101", "exit_code": 0, "result": "success"}
        )
        AuditLogger.log_event(
            action="LOGOUT",
            component="security.auth",
            status="success",
            user_id=2,
            username="operator1",
            role="user",
            resource="auth/session"
        )

    def tearDown(self):
        self.audit_db_patch.stop()
        self.db_patch.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_valid_chain_integrity(self):
        """1. Verify an untampered audit ledger passes verification with status INTACT."""
        result = AuditLogger.verify_chain_integrity()
        self.assertEqual(result["status"], "INTACT")
        self.assertEqual(result["total_records"], 5)
        self.assertIsNone(result["tampered_record_id"])
        self.assertIn("verified successfully", result["reason"])

    def test_02_modified_payload_tampering(self):
        """2. Verify tampering with any payload field (status, action, username, metadata) flags TAMPERED."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tamper record ID 3 by changing status from 'success' to 'failure'
        cursor.execute("UPDATE audit_logs SET status = 'failure' WHERE id = 3")
        conn.commit()
        conn.close()

        result = AuditLogger.verify_chain_integrity()
        self.assertEqual(result["status"], "TAMPERED")
        self.assertEqual(result["total_records"], 5)
        self.assertEqual(result["tampered_record_id"], 3)
        self.assertIn("Entry hash mismatch on record ID 3", result["reason"])

    def test_03_modified_hmac_tampering(self):
        """3. Verify modifying the HMAC entry_hash directly flags TAMPERED."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tamper record ID 2 HMAC entry_hash
        tampered_hash = "deadbeef" * 8
        cursor.execute("UPDATE audit_logs SET entry_hash = ? WHERE id = 2", (tampered_hash,))
        conn.commit()
        conn.close()

        result = AuditLogger.verify_chain_integrity()
        self.assertEqual(result["status"], "TAMPERED")
        self.assertEqual(result["total_records"], 5)
        self.assertEqual(result["tampered_record_id"], 2)
        self.assertIn("Entry hash mismatch on record ID 2", result["reason"])

    def test_04_broken_previous_hmac_linkage(self):
        """4. Verify modifying the previous_hash link flags TAMPERED."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Break previous_hash linkage on record ID 4
        broken_prev = "1234567890abcdef" * 4
        cursor.execute("UPDATE audit_logs SET previous_hash = ? WHERE id = 4", (broken_prev,))
        conn.commit()
        conn.close()

        result = AuditLogger.verify_chain_integrity()
        self.assertEqual(result["status"], "TAMPERED")
        self.assertEqual(result["total_records"], 5)
        self.assertEqual(result["tampered_record_id"], 4)
        self.assertIn("Previous hash mismatch on record ID 4", result["reason"])

    def test_05_missing_deleted_record_detection(self):
        """5. Verify deleting an intermediate record breaks the chain and is detected."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete record ID 3
        cursor.execute("DELETE FROM audit_logs WHERE id = 3")
        conn.commit()
        conn.close()

        # Record ID 4's previous_hash pointed to record ID 3's entry_hash, so record ID 4 will fail
        result = AuditLogger.verify_chain_integrity()
        self.assertEqual(result["status"], "TAMPERED")
        self.assertEqual(result["total_records"], 4)
        self.assertEqual(result["tampered_record_id"], 4)
        self.assertIn("Previous hash mismatch on record ID 4", result["reason"])

    def test_06_reordered_swapped_records_detection(self):
        """6. Verify swapping / reordering records breaks the cryptographic chain."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Fetch records 2 and 3
        cursor.execute("SELECT id, timestamp, action, previous_hash, entry_hash FROM audit_logs WHERE id IN (2, 3) ORDER BY id ASC")
        r2, r3 = cursor.fetchall()
        
        # Swap content between id=2 and id=3
        cursor.execute(
            "UPDATE audit_logs SET timestamp=?, action=?, previous_hash=?, entry_hash=? WHERE id=2",
            (r3[1], r3[2], r3[3], r3[4])
        )
        cursor.execute(
            "UPDATE audit_logs SET timestamp=?, action=?, previous_hash=?, entry_hash=? WHERE id=3",
            (r2[1], r2[2], r2[3], r2[4])
        )
        conn.commit()
        conn.close()

        result = AuditLogger.verify_chain_integrity()
        self.assertEqual(result["status"], "TAMPERED")
        self.assertEqual(result["total_records"], 5)
        self.assertEqual(result["tampered_record_id"], 2)
        self.assertIn("Previous hash mismatch on record ID 2", result["reason"])


if __name__ == "__main__":
    unittest.main()
