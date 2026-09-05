import unittest
import os
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.security.dependencies import get_current_user
from backend.security.database import init_db, get_db_path
from backend.security.access_control import (
    can_access_document,
    get_accessible_document_ids,
    can_access_generated_document
)

def get_db_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn
from backend.app.config.settings import settings
from backend.rag.pipeline import DuplicateIngestionError, AegisRagService


class MockUser(dict):
    """Mock user object providing both dict and attribute/item access."""
    def __init__(self, data):
        super().__init__(data)
        self.__dict__.update(data)

    def get(self, key, default=None):
        return super().get(key, default)


class TestEnterpriseDocumentAccessControl(unittest.TestCase):
    """Comprehensive Enterprise Multi-Tenant Access Control & Deduplication Test Suite."""

    @classmethod
    def setUpClass(cls):
        cls.original_db_path = settings.AUTH_DB_PATH
        cls.test_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.test_dir, "test_enterprise_auth.db")
        settings.AUTH_DB_PATH = cls.db_path
        init_db()

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls.original_db_path
        for f in os.listdir(cls.test_dir):
            try:
                os.remove(os.path.join(cls.test_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(cls.test_dir)
        except Exception:
            pass

    def setUp(self):
        self.client = TestClient(app)
        
        # Setup 3 departments and users in test database
        with get_db_connection() as conn:
            # Seed users
            conn.execute("DELETE FROM document_permissions")
            conn.execute("DELETE FROM generated_documents")
            conn.execute("DELETE FROM documents")
            conn.execute("DELETE FROM users WHERE username LIKE 'test_%'")
            
            # User 1: Engineering dept (id=3)
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
                "VALUES (201, 'test_eng_user', 'hash', 'user', 3, 'Engineering', 1)"
            )
            # User 2: Operations dept (id=2)
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
                "VALUES (202, 'test_ops_user', 'hash', 'user', 2, 'Operations', 1)"
            )
            # User 3: Engineering dept colleague (id=3)
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
                "VALUES (203, 'test_eng_colleague', 'hash', 'user', 3, 'Engineering', 1)"
            )
            # Admin User
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
                "VALUES (200, 'test_admin', 'hash', 'admin', 1, 'Administration', 1)"
            )
            conn.commit()

        self.user_eng = MockUser({
            "id": 201, "username": "test_eng_user", "role": "user",
            "department_id": 3, "department_name": "Engineering"
        })
        self.user_ops = MockUser({
            "id": 202, "username": "test_ops_user", "role": "user",
            "department_id": 2, "department_name": "Operations"
        })
        self.user_eng2 = MockUser({
            "id": 203, "username": "test_eng_colleague", "role": "user",
            "department_id": 3, "department_name": "Engineering"
        })
        self.admin = MockUser({
            "id": 200, "username": "test_admin", "role": "admin",
            "department_id": 1, "department_name": "Administration"
        })

    def tearDown(self):
        app.dependency_overrides.clear()

    # =========================================================================
    # 1. DEPARTMENT MANAGEMENT & PROVISIONING TESTS
    # =========================================================================
    def test_department_listing_and_admin_creation(self):
        """Verify department listing and admin department creation."""
        app.dependency_overrides[get_current_user] = lambda: self.admin
        
        # 1. List departments
        res = self.client.get("/departments")
        self.assertEqual(res.status_code, 200)
        depts = res.json()
        self.assertGreaterEqual(len(depts), 8)
        dept_names = [d["name"] for d in depts]
        self.assertIn("Engineering", dept_names)
        self.assertIn("Operations", dept_names)

        # 2. Create custom department (Admin)
        res = self.client.post("/departments", json={
            "name": "Quality Assurance",
            "description": "Plant QA testing department"
        })
        self.assertEqual(res.status_code, 201)
        created = res.json()
        self.assertEqual(created["name"], "Quality Assurance")
        self.assertEqual(created["description"], "Plant QA testing department")

    def test_non_admin_cannot_create_department(self):
        """Verify non-admin users cannot create or edit departments."""
        app.dependency_overrides[get_current_user] = lambda: self.user_eng
        res = self.client.post("/departments", json={
            "name": "Unauthorized Dept",
            "code": "UNAUTH"
        })
        self.assertEqual(res.status_code, 403)

    def test_admin_update_user_department(self):
        """Verify admin can reassign a user's department."""
        app.dependency_overrides[get_current_user] = lambda: self.admin
        res = self.client.patch("/users/test_ops_user/department", json={
            "department_id": 3
        })
        self.assertEqual(res.status_code, 200)
        updated_user = res.json()
        self.assertEqual(updated_user["department_id"], 3)
        self.assertEqual(updated_user["department_name"], "Engineering")

    # =========================================================================
    # 2. ACCESS CONTROL ENGINE TESTS (can_access_document)
    # =========================================================================
    def test_access_control_policies_private_dept_org(self):
        """Verify access control decisions for PRIVATE, DEPARTMENT, and ORGANIZATION visibility."""
        doc_private = {
            "id": "doc_priv_1",
            "owner_id": 201,
            "owner_username": "test_eng_user",
            "owner_department_id": 3,
            "owner_department_name": "Engineering",
            "visibility": "PRIVATE"
        }
        doc_dept = {
            "id": "doc_dept_1",
            "owner_id": 201,
            "owner_username": "test_eng_user",
            "owner_department_id": 3,
            "owner_department_name": "Engineering",
            "visibility": "DEPARTMENT"
        }
        doc_org = {
            "id": "doc_org_1",
            "owner_id": 201,
            "owner_username": "test_eng_user",
            "owner_department_id": 3,
            "owner_department_name": "Engineering",
            "visibility": "ORGANIZATION"
        }

        # 1. Owner has full access to PRIVATE doc
        self.assertTrue(can_access_document(self.user_eng, doc_private, "READ"))
        self.assertTrue(can_access_document(self.user_eng, doc_private, "DELETE"))
        self.assertTrue(can_access_document(self.user_eng, doc_private, "DOWNLOAD"))

        # 2. Admin has full access
        self.assertTrue(can_access_document(self.admin, doc_private, "READ"))
        self.assertTrue(can_access_document(self.admin, doc_private, "DELETE"))

        # 3. Colleague in same department CANNOT access PRIVATE doc by default
        self.assertFalse(can_access_document(self.user_eng2, doc_private, "READ"))

        # 4. Colleague in same department CAN access DEPARTMENT doc for READ and DOWNLOAD
        self.assertTrue(can_access_document(self.user_eng2, doc_dept, "READ"))
        self.assertTrue(can_access_document(self.user_eng2, doc_dept, "DOWNLOAD"))
        self.assertTrue(can_access_document(self.user_eng2, doc_dept, "USE_IN_RAG"))
        # But cannot DELETE department doc
        self.assertFalse(can_access_document(self.user_eng2, doc_dept, "DELETE"))

        # 5. User in different department CANNOT access DEPARTMENT doc
        self.assertFalse(can_access_document(self.user_ops, doc_dept, "READ"))

        # 6. Any user CAN access ORGANIZATION doc for READ and USE_IN_RAG
        self.assertTrue(can_access_document(self.user_ops, doc_org, "READ"))
        self.assertTrue(can_access_document(self.user_ops, doc_org, "USE_IN_RAG"))
        # But non-owner cannot DELETE organization doc
        self.assertFalse(can_access_document(self.user_ops, doc_org, "DELETE"))

    # =========================================================================
    # 3. EXPLICIT ACL SHARING & REVOCATION
    # =========================================================================
    def test_explicit_acl_sharing_and_revocation(self):
        """Verify explicit user and department ACL sharing grants and revocation."""
        # Insert a private document owned by test_eng_user
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, source_path, content_hash, file_size, status, owner_id, owner_username, owner_department_id, owner_department_name, visibility) "
                "VALUES ('doc_acl_test', 'confidential.pdf', '/tmp/test.pdf', 'hash123', 1024, 'indexed', 201, 'test_eng_user', 3, 'Engineering', 'PRIVATE')"
            )
            conn.commit()

        # Before sharing: user_ops cannot access
        self.assertFalse(can_access_document(self.user_ops, "doc_acl_test", "READ"))

        # Owner shares doc_acl_test with user_ops (User 202) via API
        app.dependency_overrides[get_current_user] = lambda: self.user_eng
        share_res = self.client.post("/documents/doc_acl_test/share", json={
            "user_id": 202,
            "permission": "READ"
        })
        self.assertEqual(share_res.status_code, 200)
        perm = share_res.json()
        perm_id = perm["id"]
        self.assertEqual(perm["user_id"], 202)
        self.assertEqual(perm["permission"], "READ")

        # After sharing: user_ops CAN access
        self.assertTrue(can_access_document(self.user_ops, "doc_acl_test", "READ"))
        self.assertTrue(can_access_document(self.user_ops, "doc_acl_test", "USE_IN_RAG"))
        # But cannot DELETE
        self.assertFalse(can_access_document(self.user_ops, "doc_acl_test", "DELETE"))

        # List permissions
        list_res = self.client.get("/documents/doc_acl_test/permissions")
        self.assertEqual(list_res.status_code, 200)
        perms = list_res.json()
        self.assertEqual(len(perms), 1)

        # Owner revokes permission
        del_res = self.client.delete(f"/documents/doc_acl_test/share/{perm_id}")
        self.assertEqual(del_res.status_code, 200)

        # After revocation: user_ops can no longer access
        self.assertFalse(can_access_document(self.user_ops, "doc_acl_test", "READ"))

    # =========================================================================
    # 4. PRE-RETRIEVAL VECTOR FILTERING TESTS (get_accessible_document_ids)
    # =========================================================================
    def test_get_accessible_document_ids_filtering(self):
        """Verify pre-retrieval vector filtering computes exact document IDs."""
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, source_path, content_hash, file_size, status, owner_id, owner_username, owner_department_id, owner_department_name, visibility) VALUES "
                "('d_eng_priv', 'f1.txt', '/tmp/f1', 'h1', 10, 'indexed', 201, 'test_eng_user', 3, 'Engineering', 'PRIVATE'), "
                "('d_eng_dept', 'f2.txt', '/tmp/f2', 'h2', 10, 'indexed', 201, 'test_eng_user', 3, 'Engineering', 'DEPARTMENT'), "
                "('d_ops_dept', 'f3.txt', '/tmp/f3', 'h3', 10, 'indexed', 202, 'test_ops_user', 2, 'Operations', 'DEPARTMENT'), "
                "('d_org_wide', 'f4.txt', '/tmp/f4', 'h4', 10, 'indexed', 202, 'test_ops_user', 2, 'Operations', 'ORGANIZATION')"
            )
            conn.commit()

        # Engineering Owner (user_eng) sees: d_eng_priv (owner), d_eng_dept (owner), d_org_wide (org)
        eng_ids = get_accessible_document_ids(self.user_eng, "READ")
        self.assertIn("d_eng_priv", eng_ids)
        self.assertIn("d_eng_dept", eng_ids)
        self.assertIn("d_org_wide", eng_ids)
        self.assertNotIn("d_ops_dept", eng_ids)

        # Engineering Colleague (user_eng2) sees: d_eng_dept (dept match), d_org_wide (org)
        # Does NOT see d_eng_priv or d_ops_dept
        colleague_ids = get_accessible_document_ids(self.user_eng2, "READ")
        self.assertIn("d_eng_dept", colleague_ids)
        self.assertIn("d_org_wide", colleague_ids)
        self.assertNotIn("d_eng_priv", colleague_ids)
        self.assertNotIn("d_ops_dept", colleague_ids)

        # Operations user (user_ops) sees: d_ops_dept (owner/dept), d_org_wide (owner/org)
        ops_ids = get_accessible_document_ids(self.user_ops, "READ")
        self.assertIn("d_ops_dept", ops_ids)
        self.assertIn("d_org_wide", ops_ids)
        self.assertNotIn("d_eng_priv", ops_ids)
        self.assertNotIn("d_eng_dept", ops_ids)

        # Admin sees ALL documents
        admin_ids = get_accessible_document_ids(self.admin, "READ")
        self.assertIn("d_eng_priv", admin_ids)
        self.assertIn("d_eng_dept", admin_ids)
        self.assertIn("d_ops_dept", admin_ids)
        self.assertIn("d_org_wide", admin_ids)

    # =========================================================================
    # 5. DEDUPLICATION SECURITY (HASH MATCH != ACCESS GRANTED)
    # =========================================================================
    def test_deduplication_security_unauthorized_vs_authorized(self):
        """Verify HASH MATCH != ACCESS GRANTED deduplication behavior."""
        rag_svc = AegisRagService(embedding_model=MagicMock())
        
        kb_dir = os.path.abspath("data/knowledge_base")
        os.makedirs(kb_dir, exist_ok=True)
        test_file_path = os.path.join(kb_dir, "test_secret_schematic.txt")
        test_content = b"CRITICAL PLANT BLUEPRINT AND AUTOMATION LOGIC"
        with open(test_file_path, "wb") as f:
            f.write(test_content)
        
        import hashlib
        computed_hash = hashlib.sha256(test_content).hexdigest()

        try:
            # Setup initial document by user_eng
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO documents (id, filename, source_path, content_hash, file_size, status, owner_id, owner_username, owner_department_id, owner_department_name, visibility) "
                    "VALUES ('doc_canon_1', 'secret_schematic.txt', ?, ?, 500, 'indexed', 201, 'test_eng_user', 3, 'Engineering', 'PRIVATE')",
                    (test_file_path, computed_hash)
                )
                conn.commit()

            # Case 1: Unauthorized user (user_ops) attempts to upload exact same file (same hash)
            # Must raise DuplicateIngestionError (HTTP 400) without leaking document metadata
            with self.assertRaises(DuplicateIngestionError) as ctx:
                rag_svc.ingest_document(
                    file_path=test_file_path,
                    owner_id=202,
                    owner_username="test_ops_user",
                    owner_department_id=2,
                    owner_department_name="Operations",
                    visibility="PRIVATE",
                    original_filename="secret_schematic.txt",
                    current_user=self.user_ops
                )
            self.assertIn("A document with identical content already exists", str(ctx.exception))
            # Ensure no owner information was leaked in the exception message
            self.assertNotIn("test_eng_user", str(ctx.exception))
            self.assertNotIn("doc_canon_1", str(ctx.exception))

            # Case 2: Authorized user (user_eng, the owner) uploads exact same file (same hash)
            # Must raise DuplicateIngestionError indicating document is already indexed
            with self.assertRaises(DuplicateIngestionError) as ctx2:
                rag_svc.ingest_document(
                    file_path=test_file_path,
                    owner_id=201,
                    owner_username="test_eng_user",
                    owner_department_id=3,
                    owner_department_name="Engineering",
                    visibility="PRIVATE",
                    original_filename="secret_schematic.txt",
                    current_user=self.user_eng
                )
            self.assertIn("already indexed", str(ctx2.exception))
            self.assertIn("secret_schematic.txt", str(ctx2.exception))
        finally:
            if os.path.exists(test_file_path):
                try:
                    os.remove(test_file_path)
                except Exception:
                    pass

    # =========================================================================
    # 6. SECURE DOCUMENT DOWNLOAD & PREVIEW
    # =========================================================================
    def test_document_download_authorization(self):
        """Verify document download enforces strict access control."""
        # Create physical dummy file within safe directory
        kb_dir = os.path.abspath("data/knowledge_base")
        os.makedirs(kb_dir, exist_ok=True)
        test_file_path = os.path.join(kb_dir, "test_download.txt")
        with open(test_file_path, "w") as f:
            f.write("CONFIDENTIAL REFINERY DATA")

        try:
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO documents (id, filename, source_path, content_hash, file_size, status, owner_id, owner_username, owner_department_id, owner_department_name, visibility) "
                    "VALUES ('doc_dl_test', 'download_me.txt', ?, 'dl_hash', 26, 'indexed', 201, 'test_eng_user', 3, 'Engineering', 'PRIVATE')",
                    (test_file_path,)
                )
                conn.commit()

            # User ops tries to download User eng's private doc -> 403 Forbidden
            app.dependency_overrides[get_current_user] = lambda: self.user_ops
            res = self.client.get("/documents/doc_dl_test/download")
            self.assertEqual(res.status_code, 403)

            # User eng (owner) downloads -> 200 OK with correct content
            app.dependency_overrides[get_current_user] = lambda: self.user_eng
            res = self.client.get("/documents/doc_dl_test/download")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.text, "CONFIDENTIAL REFINERY DATA")
        finally:
            if os.path.exists(test_file_path):
                try:
                    os.remove(test_file_path)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
