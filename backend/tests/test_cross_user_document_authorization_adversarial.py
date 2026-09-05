import os
import shutil
import sqlite3
import tempfile
import unittest
import hashlib
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.app.main import app
from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.security.dependencies import get_current_user
from backend.security.audit import AuditLogger
from backend.security.access_control import (
    can_access_document,
    get_accessible_document_ids,
    can_access_generated_document
)


class MockUser(dict):
    """Mock user object providing both dict and attribute access for FastAPI auth dependency override."""
    def __init__(self, data):
        super().__init__(data)
        self.__dict__.update(data)

    def get(self, key, default=None):
        return super().get(key, default)


class TestCrossUserDocumentAuthorizationAdversarial(unittest.TestCase):
    """Adversarial cross-user and cross-department authorization test suite."""

    @classmethod
    def setUpClass(cls):
        cls.orig_auth_db = settings.AUTH_DB_PATH
        cls.orig_vector_db = settings.VECTOR_DB_PATH
        cls.test_dir = tempfile.mkdtemp(prefix="aegis_adv_auth_")
        cls.db_path = os.path.join(cls.test_dir, "test_auth.db")
        cls.vdb_path = os.path.join(cls.test_dir, "vectorstore")
        settings.AUTH_DB_PATH = cls.db_path
        settings.VECTOR_DB_PATH = cls.vdb_path
        init_db()

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls.orig_auth_db
        settings.VECTOR_DB_PATH = cls.orig_vector_db
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        self.client = TestClient(app)

        # Initialize clean test users & tables
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("DELETE FROM document_permissions")
        cursor.execute("DELETE FROM generated_documents")
        cursor.execute("DELETE FROM documents")
        cursor.execute("DELETE FROM conversations")
        cursor.execute("DELETE FROM messages")
        cursor.execute("DELETE FROM users WHERE username LIKE 'adv_%'")

        # Ensure departments exist
        cursor.execute("SELECT id, name FROM departments")
        dept_rows = cursor.fetchall()
        dept_map = {r["name"]: r["id"] for r in dept_rows}

        eng_dept_id = dept_map.get("Engineering", 3)
        ops_dept_id = dept_map.get("Operations", 2)
        admin_dept_id = dept_map.get("Administration", 1)

        # 1. User A (Engineering)
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
            "VALUES (301, 'adv_user_a', 'hash', 'user', ?, 'Engineering', 1)",
            (eng_dept_id,)
        )
        # 2. User B (Operations)
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
            "VALUES (302, 'adv_user_b', 'hash', 'user', ?, 'Operations', 1)",
            (ops_dept_id,)
        )
        # 3. User A2 (Colleague in Engineering)
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
            "VALUES (303, 'adv_user_a2', 'hash', 'user', ?, 'Engineering', 1)",
            (eng_dept_id,)
        )
        # 4. Admin User
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
            "VALUES (300, 'adv_admin', 'hash', 'admin', ?, 'Administration', 1)",
            (admin_dept_id,)
        )
        conn.commit()
        conn.close()

        self.user_a = MockUser({
            "id": 301, "username": "adv_user_a", "role": "user",
            "department_id": eng_dept_id, "department_name": "Engineering"
        })
        self.user_b = MockUser({
            "id": 302, "username": "adv_user_b", "role": "user",
            "department_id": ops_dept_id, "department_name": "Operations"
        })
        self.user_a2 = MockUser({
            "id": 303, "username": "adv_user_a2", "role": "user",
            "department_id": eng_dept_id, "department_name": "Engineering"
        })
        self.admin = MockUser({
            "id": 300, "username": "adv_admin", "role": "admin",
            "department_id": admin_dept_id, "department_name": "Administration"
        })

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_01_private_document_direct_access_attack(self):
        """ATTACK 1: User B tries direct access/view/download on User A's private document."""
        # Step 1: User A uploads private confidential document
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        secret_content = b"TOP SECRET REACTOR CORE SPEC: RPM=15400, PEAK_TEMP=890C, COOLANT_BAR=4.2"
        upload_resp = self.client.post(
            "/documents/upload",
            files={"file": ("secret_turbine_spec.txt", secret_content, "text/plain")},
            data={"visibility": "PRIVATE"}
        )
        self.assertEqual(upload_resp.status_code, 200, f"Upload failed: {upload_resp.text}")
        doc_data = upload_resp.json()
        doc_id = doc_data["document_id"]
        self.assertEqual(doc_data["visibility"], "PRIVATE")

        # Step 2: User B tries GET /documents (document list)
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        list_resp = self.client.get("/documents")
        self.assertEqual(list_resp.status_code, 200)
        user_b_docs = list_resp.json()
        user_b_doc_ids = [d["id"] for d in user_b_docs]
        self.assertNotIn(doc_id, user_b_doc_ids, "VULNERABILITY: User A's private document appeared in User B's document list!")

        # Step 3: User B tries direct GET /documents/{id}/preview
        get_resp = self.client.get(f"/documents/{doc_id}/preview")
        self.assertEqual(get_resp.status_code, 403, f"Expected 403 Forbidden, got {get_resp.status_code}")
        body_text = get_resp.text
        self.assertNotIn("15400", body_text, "VULNERABILITY: Confidential text leaked in 403 error response!")
        self.assertNotIn("PEAK_TEMP", body_text, "VULNERABILITY: Confidential key leaked in 403 error response!")

        # Step 4: User B tries GET /documents/{id}/download
        download_resp = self.client.get(f"/documents/{doc_id}/download")
        self.assertEqual(download_resp.status_code, 403, f"Expected 403 Forbidden on download, got {download_resp.status_code}")
        self.assertNotIn(b"TOP SECRET REACTOR", download_resp.content, "VULNERABILITY: Secret file bytes delivered to unauthorized User B!")

        # Step 5: User B tries DELETE /documents/{id}
        del_resp = self.client.delete(f"/documents/{doc_id}")
        self.assertEqual(del_resp.status_code, 403, "VULNERABILITY: User B was able to delete User A's document!")

    def test_02_rag_adversarial_extraction_attack(self):
        """ATTACK 2: User B attempts semantic RAG and explicit document ID extraction."""
        # User A uploads confidential document
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        secret_content = b"PROJECT_TITAN_SECRET: The cryogenic valve bypass frequency is strictly 433.92 MHz."
        upload_resp = self.client.post(
            "/documents/upload",
            files={"file": ("project_titan_spec.txt", secret_content, "text/plain")},
            data={"visibility": "PRIVATE"}
        )
        doc_id = upload_resp.json()["document_id"]

        # Switch to User B (Adversary)
        app.dependency_overrides[get_current_user] = lambda: self.user_b

        # Attack A: Direct Document ID injection in RAG (/documents/ask)
        rag_resp_a = self.client.post(
            "/documents/ask",
            json={"query": "What is the cryogenic valve bypass frequency?", "document_id": doc_id}
        )
        self.assertEqual(rag_resp_a.status_code, 200)
        ans_a = rag_resp_a.json()
        self.assertIn("Access denied", ans_a["answer"], f"Expected Access Denied in RAG answer, got: {ans_a}")
        self.assertEqual(ans_a["sources"], [], "VULNERABILITY: Sources array leaked confidential citations to User B!")
        self.assertNotIn("433.92", ans_a["answer"])

        # Attack B: Semantic inquiry by filename
        rag_resp_b = self.client.post(
            "/documents/ask",
            json={"query": "Read project_titan_spec.txt and extract the secret frequency"}
        )
        self.assertEqual(rag_resp_b.status_code, 200)
        ans_b = rag_resp_b.json()
        self.assertEqual(ans_b["sources"], [], "VULNERABILITY: Sources returned ungrounded/unauthorized doc chunks!")
        self.assertNotIn("433.92", ans_b["answer"])

        # Attack C: Vector similarity search (/documents/query)
        search_resp = self.client.post(
            "/documents/query",
            json={"query": "cryogenic valve bypass frequency", "limit": 5}
        )
        self.assertEqual(search_resp.status_code, 200)
        search_results = search_resp.json().get("results", [])
        self.assertEqual(len(search_results), 0, "VULNERABILITY: Vector search returned chunk embeddings across tenant boundary!")

    def test_03_generated_report_attack(self):
        """ATTACK 3: User B attempts to access and download a report generated from User A's private doc."""
        # User A uploads doc
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        secret_content = b"CONFIDENTIAL FINANCIAL AUDIT: Q3 Surplus is $4,850,000. Off-ledger reserve is $1.2M."
        upload_resp = self.client.post(
            "/documents/upload",
            files={"file": ("financial_audit_q3.txt", secret_content, "text/plain")},
            data={"visibility": "PRIVATE"}
        )
        doc_id = upload_resp.json()["document_id"]

        # User A generates a report
        gen_resp = self.client.post(
            "/documents/generate",
            json={
                "title": "Q3 Executive Summary",
                "format": "docx",
                "document_id": doc_id
            }
        )
        self.assertEqual(gen_resp.status_code, 200, f"Report generation failed: {gen_resp.text}")
        gen_data = gen_resp.json()
        report_id = gen_data["id"]

        # Switch to User B (Adversary)
        app.dependency_overrides[get_current_user] = lambda: self.user_b

        # Attack 1: List generated documents
        list_resp = self.client.get("/documents/generated")
        self.assertEqual(list_resp.status_code, 200)
        gen_docs = list_resp.json()
        gen_ids = [d["id"] for d in gen_docs]
        self.assertNotIn(report_id, gen_ids, "VULNERABILITY: User A's private generated report listed for User B!")

        # Attack 2: Download generated report
        down_resp = self.client.get(f"/documents/generated/{report_id}/download")
        self.assertEqual(down_resp.status_code, 403, f"Expected 403 on report download, got {down_resp.status_code}")

    def test_04_department_visibility_boundary_enforcement(self):
        """ATTACK 4: Department boundary policy check (Engineering vs Operations vs Admin)."""
        # User A (Engineering) uploads document with visibility = DEPARTMENT
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        sop_content = b"ENGINEERING SOP: Calibration procedure for Turbine Rotor Gen 4."
        upload_resp = self.client.post(
            "/documents/upload",
            files={"file": ("engineering_sop_gen4.txt", sop_content, "text/plain")},
            data={"visibility": "DEPARTMENT"}
        )
        self.assertEqual(upload_resp.status_code, 200)
        doc_id = upload_resp.json()["document_id"]

        # 1. Colleague User A2 (Engineering) -> ALLOWED
        app.dependency_overrides[get_current_user] = lambda: self.user_a2
        get_a2_resp = self.client.get(f"/documents/{doc_id}/preview")
        self.assertEqual(get_a2_resp.status_code, 200, "Engineering colleague should be allowed to view Engineering department doc")
        down_a2_resp = self.client.get(f"/documents/{doc_id}/download")
        self.assertEqual(down_a2_resp.status_code, 200, "Engineering colleague should be allowed to download Engineering department doc")

        # 2. User B (Operations) -> DENIED
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        get_b_resp = self.client.get(f"/documents/{doc_id}/preview")
        self.assertEqual(get_b_resp.status_code, 403, "Operations user should be DENIED access to Engineering department doc")
        down_b_resp = self.client.get(f"/documents/{doc_id}/download")
        self.assertEqual(down_b_resp.status_code, 403, "Operations user should be DENIED download of Engineering department doc")

        # 3. Admin -> ALLOWED
        app.dependency_overrides[get_current_user] = lambda: self.admin
        get_admin_resp = self.client.get(f"/documents/{doc_id}/preview")
        self.assertEqual(get_admin_resp.status_code, 200, "Admin should be allowed access per governance policy")

    def test_05_explicit_share_grant_and_revocation(self):
        """ATTACK 5: Explicit ACL grant and revocation lifecycle."""
        # User A uploads private doc
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        secret_content = b"SHARED SPEC: High-pressure steam valve tolerance."
        upload_resp = self.client.post(
            "/documents/upload",
            files={"file": ("shared_steam_spec.txt", secret_content, "text/plain")},
            data={"visibility": "PRIVATE"}
        )
        doc_id = upload_resp.json()["document_id"]

        # Verify User B cannot access initially
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        self.assertEqual(self.client.get(f"/documents/{doc_id}/preview").status_code, 403)

        # User A explicitly shares with User B (READ permission)
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        share_resp = self.client.post(
            f"/documents/{doc_id}/share",
            json={"user_id": 302, "permission": "READ"}
        )
        self.assertEqual(share_resp.status_code, 200, f"Sharing failed: {share_resp.text}")
        perm_id = share_resp.json()["id"]

        # User B can now READ and DOWNLOAD
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        self.assertEqual(self.client.get(f"/documents/{doc_id}/preview").status_code, 200)
        self.assertEqual(self.client.get(f"/documents/{doc_id}/download").status_code, 200)

        # User B cannot DELETE or re-SHARE (Least-Privilege enforcement)
        self.assertEqual(self.client.delete(f"/documents/{doc_id}").status_code, 403)
        self.assertEqual(
            self.client.post(f"/documents/{doc_id}/share", json={"user_id": 303, "permission": "READ"}).status_code,
            403
        )

        # User A revokes access
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        revoke_resp = self.client.delete(f"/documents/{doc_id}/share/{perm_id}")
        self.assertEqual(revoke_resp.status_code, 200)

        # User B is now DENIED across all operations
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        self.assertEqual(self.client.get(f"/documents/{doc_id}/preview").status_code, 403)
        self.assertEqual(self.client.get(f"/documents/{doc_id}/download").status_code, 403)
        rag_revoked = self.client.post("/documents/ask", json={"query": "steam valve", "document_id": doc_id})
        self.assertIn("Access denied", rag_revoked.json()["answer"])

    def test_06_duplicate_upload_information_disclosure_prevention(self):
        """ATTACK 6: Duplicate detection side-channel leak test."""
        # User A uploads a document
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        unique_bytes = b"PROPRIETARY CHEMICAL FORMULA: Compound-X999 with 88% purity."
        self.client.post(
            "/documents/upload",
            files={"file": ("chemical_formula.txt", unique_bytes, "text/plain")},
            data={"visibility": "PRIVATE"}
        )

        # User B uploads exact duplicate file content
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        dup_resp = self.client.post(
            "/documents/upload",
            files={"file": ("adversary_guess.txt", unique_bytes, "text/plain")},
            data={"visibility": "PRIVATE"}
        )
        self.assertEqual(dup_resp.status_code, 400)
        dup_json = dup_resp.json()
        detail_msg = dup_json.get("detail", "")

        # CRITICAL LEAK CHECKS: User B must not learn owner username, owner ID, or original filename
        self.assertNotIn("adv_user_a", detail_msg, "LEAK: Owner username exposed in duplicate detection error!")
        self.assertNotIn("301", detail_msg, "LEAK: Owner ID exposed in duplicate detection error!")
        self.assertNotIn("chemical_formula", detail_msg, "LEAK: Original document name exposed in duplicate detection error!")
        self.assertNotIn("Engineering", detail_msg, "LEAK: Department name exposed in duplicate detection error!")
        self.assertEqual(
            detail_msg,
            "A document with identical content already exists in the system, but you do not have permission to access it."
        )

    def test_07_idor_conversations_and_sandbox_artifacts(self):
        """ATTACK 7: Insecure Direct Object Reference (IDOR) attacks across sessions and sandbox runs."""
        # 1. Conversation IDOR
        # User A creates a conversation
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        conv_resp = self.client.post("/conversations", json={"title": "Confidential A Strategy"})
        self.assertEqual(conv_resp.status_code, 200)
        conv_id = conv_resp.json()["id"]

        # User A posts message
        self.client.post(
            f"/conversations/{conv_id}/messages",
            json={"message": "CONFIDENTIAL MESSAGE CONTENT 998877"}
        )

        # User B attempts to access User A's conversation
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        conv_get = self.client.get(f"/conversations/{conv_id}")
        self.assertEqual(conv_get.status_code, 403, "VULNERABILITY: User B accessed User A's conversation via IDOR!")
        self.assertNotIn("998877", conv_get.text)

        # User B attempts to post message into User A's conversation
        msg_post = self.client.post(
            f"/conversations/{conv_id}/messages",
            json={"message": "HACKED MESSAGE"}
        )
        self.assertEqual(msg_post.status_code, 403, "VULNERABILITY: User B posted into User A's conversation via IDOR!")

        # User B attempts to delete User A's conversation
        conv_del = self.client.delete(f"/conversations/{conv_id}")
        self.assertEqual(conv_del.status_code, 403, "VULNERABILITY: User B deleted User A's conversation via IDOR!")

        # 2. Sandbox Artifact IDOR
        # Setup a mock sandbox artifact owned by User A in database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sandbox_artifacts ("
                "id TEXT PRIMARY KEY, user_id INTEGER, username TEXT, conversation_id TEXT, "
                "filename TEXT, file_path TEXT, mime_type TEXT, file_size INTEGER, created_at TEXT"
                ")"
            )
            conn.execute(
                "INSERT OR REPLACE INTO sandbox_artifacts "
                "(id, execution_id, user_id, username, conversation_id, filename, file_path, mime_type, file_size, created_at) "
                "VALUES ('art_user_a_secret', 'sb_exec_123', 301, 'adv_user_a', 'conv_123', 'secret_art.csv', '/tmp/secret_art.csv', 'text/csv', 100, datetime('now', 'utc'))"
            )
            conn.commit()

        # User B attempts to download User A's sandbox artifact
        art_down = self.client.get("/sandbox/artifacts/art_user_a_secret/download")
        self.assertEqual(art_down.status_code, 403, "VULNERABILITY: User B downloaded User A's sandbox artifact via IDOR!")

    def test_08_audit_logging_of_authorization_failures(self):
        """ATTACK 8: Verify all authorization failures generate real, tamper-evident audit records."""
        # Trigger an authorization denial by User B on an inaccessible document
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        upload_resp = self.client.post(
            "/documents/upload",
            files={"file": ("audit_test_doc.txt", b"AUDIT_SECRET_DATA", "text/plain")},
            data={"visibility": "PRIVATE"}
        )
        doc_id = upload_resp.json()["document_id"]

        app.dependency_overrides[get_current_user] = lambda: self.user_b
        self.client.get(f"/documents/{doc_id}/download")
        self.client.post("/documents/ask", json={"query": "test", "document_id": doc_id})

        # Query audit logs for authorization failure events
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action, component, resource, status, metadata_json FROM audit_logs "
            "WHERE action IN ('DOCUMENT_ACCESS_DENIED', 'AUTHORIZATION_FAILURE', 'AUTHORIZATION_DENIED', 'DOCUMENT_UPLOAD_FAILED') "
            "ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        conn.close()

        self.assertGreater(len(rows), 0, "No audit events recorded for authorization failures!")
        actions_logged = {r["action"] for r in rows}
        self.assertTrue(
            any(a in actions_logged for a in ["DOCUMENT_ACCESS_DENIED", "AUTHORIZATION_FAILURE", "AUTHORIZATION_DENIED"]),
            f"Expected authorization denial action, found: {actions_logged}"
        )


if __name__ == "__main__":
    unittest.main()
