import unittest
import os
import tempfile
import sqlite3
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.security.auth import hash_password, create_access_token
from backend.security.audit import AuditLogger
from backend.security.models import ApprovalStatus
from backend.security.access_control import can_access_generated_document


class TestHitlDownloadAuthorization(unittest.TestCase):
    """
    Comprehensive verification suite for HITL deliverable download authorization,
    requester ownership preservation, reviewer/requester separation, RBAC enforcement,
    and binary stream integrity.
    """

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_download_auth.db")
        cls.outputs_dir = os.path.join(cls.temp_dir.name, "outputs")
        os.makedirs(cls.outputs_dir, exist_ok=True)

        cls._orig_db_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = cls.test_db_path

        init_db()

        # Seed test users across departments
        conn = sqlite3.connect(cls.test_db_path)
        cursor = conn.cursor()

        users_to_seed = [
            ("alice_ops", hash_password("AlicePass123!"), "user", 2, "Operations"),
            ("bob_ops", hash_password("BobPass123!"), "user", 2, "Operations"),
            ("carol_eng", hash_password("CarolPass123!"), "user", 3, "Engineering"),
            ("reviewer_dave", hash_password("DavePass123!"), "reviewer", 2, "Operations"),
            ("admin_eve", hash_password("EvePass123!"), "admin", 1, "Administration")
        ]

        for uname, pwd_hash, role, dept_id, dept_name in users_to_seed:
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, department_id, department_name, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                (uname, pwd_hash, role, dept_id, dept_name)
            )

        conn.commit()

        cursor.execute("SELECT id, username, role, department_id FROM users")
        cls.user_map = {row[1]: {"id": row[0], "username": row[1], "role": row[2], "department_id": row[3]} for row in cursor.fetchall()}
        conn.close()

        # Generate access tokens
        cls.token_alice = create_access_token("alice_ops", "user")
        cls.token_bob = create_access_token("bob_ops", "user")
        cls.token_carol = create_access_token("carol_eng", "user")
        cls.token_reviewer = create_access_token("reviewer_dave", "reviewer")
        cls.token_admin = create_access_token("admin_eve", "admin")

        from backend.app.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls._orig_db_path
        cls.temp_dir.cleanup()

    def setUp(self):
        # Create physical test artifact file
        self.sample_pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Title (Cooling Tower Inspection) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        self.test_pdf_path = os.path.join(self.outputs_dir, "test_inspection_report.pdf")
        with open(self.test_pdf_path, "wb") as f:
            f.write(self.sample_pdf_content)

        # Setup test conversation and generated document
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()

        self.conv_id = "conv_test_download_001"
        cursor.execute(
            "INSERT OR REPLACE INTO conversations (id, user_id, username, title, feature, status) VALUES (?, ?, ?, ?, 'chat', 'active')",
            (self.conv_id, self.user_map["alice_ops"]["id"], "alice_ops", "Cooling Tower Inspection Task")
        )

        self.doc_id = "gen_doc_test_001"
        cursor.execute("""
            INSERT OR REPLACE INTO generated_documents (
                id, owner_id, owner_username, owner_department_id, owner_department_name,
                visibility, filename, title, format, file_size, mime_type,
                conversation_id, status, file_path, source_document_ids, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            self.doc_id, self.user_map["alice_ops"]["id"], "alice_ops", 2, "Operations",
            "PRIVATE", "cooling_tower_inspection_note.pdf", "Cooling Tower Inspection Note", "pdf",
            len(self.sample_pdf_content), "application/pdf",
            self.conv_id, "completed", self.test_pdf_path, json.dumps(["src_doc_001"])
        ))

        # Setup approval request showing reviewer Dave approved Alice's task
        self.appr_id = "appr_test_download_001"
        cursor.execute("""
            INSERT OR REPLACE INTO approval_requests (
                id, plan_id, conversation_id, requester_id, requester_username,
                department_id, action_type, status, reviewer_id, reviewer_username, reviewer_role
            ) VALUES (?, ?, ?, ?, ?, ?, 'GENERATE_REPORT', 'APPROVED', ?, 'reviewer_dave', 'reviewer')
        """, (
            self.appr_id, "plan_test_001", self.conv_id,
            self.user_map["alice_ops"]["id"], "alice_ops", 2,
            self.user_map["reviewer_dave"]["id"]
        ))

        conn.commit()
        conn.close()

    def test_01_authenticated_requester_can_download_own_document(self):
        """TEST 1: Original requester (Alice) can download her own generated document."""
        headers = {"Authorization": f"Bearer {self.token_alice}"}
        resp = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, self.sample_pdf_content)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertIn('filename="cooling_tower_inspection_note.pdf"', resp.headers.get("content-disposition", ""))

    def test_02_reviewer_approval_does_not_transfer_ownership(self):
        """TEST 2: Reviewer (Dave) approving the task does not become owner of document."""
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT owner_id, owner_username FROM generated_documents WHERE id = ?", (self.doc_id,))
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row[0], self.user_map["alice_ops"]["id"])
        self.assertEqual(row[1], "alice_ops")

    def test_03_admin_can_download_according_to_policy(self):
        """TEST 3: System Administrator (Eve) can download generated report."""
        headers = {"Authorization": f"Bearer {self.token_admin}"}
        resp = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.content), len(self.sample_pdf_content))

    def test_04_unauthorized_cross_user_download_returns_403(self):
        """TEST 4: Cross-user (Bob in same dept but not owner, nor cited source access) gets 403."""
        headers = {"Authorization": f"Bearer {self.token_bob}"}
        resp = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Access denied", resp.json().get("detail", ""))

    def test_05_missing_authentication_returns_401(self):
        """TEST 5: Unauthenticated request without Bearer token returns 401 Unauthorized."""
        resp = self.client.get(f"/documents/generated/{self.doc_id}/download")
        self.assertEqual(resp.status_code, 401)

    def test_06_cross_department_user_download_returns_403(self):
        """TEST 6: Cross-department user (Carol in Engineering) gets 403."""
        headers = {"Authorization": f"Bearer {self.token_carol}"}
        resp = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
        self.assertEqual(resp.status_code, 403)

    def test_07_downloaded_binary_has_non_zero_size(self):
        """TEST 7: Downloaded payload is non-empty and matches actual disk bytes."""
        headers = {"Authorization": f"Bearer {self.token_alice}"}
        resp = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.content), 0)
        self.assertEqual(len(resp.content), len(self.sample_pdf_content))

    def test_08_correct_filename_in_content_disposition(self):
        """TEST 8: Valid Content-Disposition header with filename is returned."""
        headers = {"Authorization": f"Bearer {self.token_alice}"}
        resp = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
        self.assertEqual(resp.status_code, 200)
        cd = resp.headers.get("content-disposition", "")
        self.assertIn("attachment;", cd)
        self.assertIn("cooling_tower_inspection_note.pdf", cd)

    def test_09_correct_mime_type_returned(self):
        """TEST 9: Correct Content-Type header (application/pdf) is returned."""
        headers = {"Authorization": f"Bearer {self.token_alice}"}
        resp = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")

    def test_10_api_route_alias_supported(self):
        """TEST 10: Both /documents/generated/... and /api/documents/generated/... routes work identically."""
        headers = {"Authorization": f"Bearer {self.token_alice}"}
        resp1 = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
        resp2 = self.client.get(f"/api/documents/generated/{self.doc_id}/download", headers=headers)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.content, resp2.content)

    def test_11_repeated_downloads_are_idempotent(self):
        """TEST 11: Repeated downloads do not alter file or state."""
        headers = {"Authorization": f"Bearer {self.token_alice}"}
        for _ in range(3):
            resp = self.client.get(f"/documents/generated/{self.doc_id}/download", headers=headers)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.content, self.sample_pdf_content)

    def test_12_nonexistent_document_returns_404(self):
        """TEST 12: Requesting unknown document returns 404 Not Found."""
        headers = {"Authorization": f"Bearer {self.token_alice}"}
        resp = self.client.get("/documents/generated/gen_nonexistent_999/download", headers=headers)
        self.assertEqual(resp.status_code, 404)

    def test_13_audit_chain_integrity_remains_intact(self):
        """TEST 13: Cryptographic HMAC audit chain integrity is verified intact."""
        chain_res = AuditLogger.verify_chain_integrity()
        self.assertEqual(chain_res.get("status"), "INTACT")


if __name__ == "__main__":
    unittest.main()
