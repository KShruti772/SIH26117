import os
import shutil
import sqlite3
import tempfile
import unittest
import socket
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.app.main import app
from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.security.dependencies import get_current_user
from backend.security.audit import AuditLogger
from backend.models.loaders.manager import ModelLoaderManager
from backend.rag.embeddings import get_local_embedding_model


class MockUser(dict):
    def __init__(self, data):
        super().__init__(data)
        self.__dict__.update(data)

    def get(self, key, default=None):
        return super().get(key, default)


class TestAirGappedOperationValidation(unittest.TestCase):
    """Rigorous air-gapped operation and zero-egress network validation test suite."""

    @classmethod
    def setUpClass(cls):
        cls.orig_auth_db = settings.AUTH_DB_PATH
        cls.orig_vector_db = settings.VECTOR_DB_PATH
        cls.test_dir = tempfile.mkdtemp(prefix="aegis_airgap_val_")
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
        self.observed_external_connections = []
        self.observed_dns_lookups = []

        # Hook socket.socket.connect and socket.getaddrinfo to monitor all network activity
        self.real_connect = socket.socket.connect
        self.real_getaddrinfo = socket.getaddrinfo

        def monitored_connect(sock_self, address):
            host = address[0] if isinstance(address, tuple) else str(address)
            # Local loopback addresses
            if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0", "testserver"):
                self.observed_external_connections.append(address)
            return self.real_connect(sock_self, address)

        def monitored_getaddrinfo(host, port, *args, **kwargs):
            if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0", "testserver", None):
                self.observed_dns_lookups.append(host)
            return self.real_getaddrinfo(host, port, *args, **kwargs)

        self.connect_patch = patch.object(socket.socket, "connect", monitored_connect)
        self.dns_patch = patch.object(socket, "getaddrinfo", monitored_getaddrinfo)
        self.connect_patch.start()
        self.dns_patch.start()

        # Seed standard offline users
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM users WHERE username LIKE 'airgap_%'")
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
                "VALUES (501, 'airgap_admin', '$2b$12$e6k.s9V7UeHkZ8UuQ9v5eO7eH1e3oOqC5t9oD5s9l1yZ.5e9l1yZ.', 'admin', 1, 'Administration', 1)"
            )
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) "
                "VALUES (502, 'airgap_user', '$2b$12$e6k.s9V7UeHkZ8UuQ9v5eO7eH1e3oOqC5t9oD5s9l1yZ.5e9l1yZ.', 'user', 3, 'Engineering', 1)"
            )
            conn.commit()

        self.user = MockUser({
            "id": 502, "username": "airgap_user", "role": "user",
            "department_id": 3, "department_name": "Engineering"
        })
        self.admin = MockUser({
            "id": 501, "username": "airgap_admin", "role": "admin",
            "department_id": 1, "department_name": "Administration"
        })

    def tearDown(self):
        self.dns_patch.stop()
        self.connect_patch.stop()
        app.dependency_overrides.clear()

    def test_01_static_and_runtime_embeddings_are_local(self):
        """Verify embedding model is loaded from local disk without downloading from internet."""
        local_emb = get_local_embedding_model("./models/all-MiniLM-L6-v2")
        self.assertIsNotNone(local_emb)
        vec = local_emb.embed_query("Air-gap local embedding test")
        self.assertEqual(len(vec), 384)
        self.assertEqual(self.observed_external_connections, [])
        self.assertEqual(self.observed_dns_lookups, [])

    def test_02_login_runs_completely_offline(self):
        """Verify authentication runs locally against SQLite bcrypt without cloud auth."""
        resp = self.client.post(
            "/auth/login",
            data={"username": "airgap_admin", "password": "AdminPassword123!"}
        )
        # Auth route handles login locally
        self.assertIn(resp.status_code, (200, 401))
        self.assertEqual(self.observed_external_connections, [])
        self.assertEqual(self.observed_dns_lookups, [])

    def test_03_document_upload_indexing_and_rag_runs_offline(self):
        """Verify RAG document upload, universal extraction, vector indexing, and search operate offline."""
        app.dependency_overrides[get_current_user] = lambda: self.user

        doc_content = b"AIRGAP INDUSTRIAL SPECIFICATION: Primary coolant pump operating speed is 1850 RPM at 6.2 bar."
        upload_resp = self.client.post(
            "/documents/upload",
            files={"file": ("airgap_pump_spec.txt", doc_content, "text/plain")},
            data={"visibility": "PRIVATE"}
        )
        self.assertEqual(upload_resp.status_code, 200, f"Upload failed: {upload_resp.text}")
        doc_id = upload_resp.json()["document_id"]

        # Search documents
        query_resp = self.client.post(
            "/documents/query",
            json={"query": "coolant pump operating speed", "limit": 3}
        )
        self.assertEqual(query_resp.status_code, 200)
        results = query_resp.json().get("results", [])
        self.assertGreater(len(results), 0)
        self.assertIn("1850 RPM", results[0]["text"])

        self.assertEqual(self.observed_external_connections, [])
        self.assertEqual(self.observed_dns_lookups, [])

    def test_04_sandbox_execution_blocks_outbound_network(self):
        """Verify code sandbox enforces strict offline network policy."""
        app.dependency_overrides[get_current_user] = lambda: self.user

        # Safe math code executes
        resp_safe = self.client.post(
            "/sandbox/execute",
            json={"code": "res = sum(i**2 for i in range(10))\nprint(f'SUM={res}')"}
        )
        self.assertEqual(resp_safe.status_code, 200)
        self.assertEqual(resp_safe.json()["exit_code"], 0)
        self.assertIn("SUM=285", resp_safe.json()["stdout"])

        # Code attempting network socket is strictly blocked
        resp_net = self.client.post(
            "/sandbox/execute",
            json={"code": "import socket\ns = socket.socket()\ns.connect(('1.1.1.1', 80))"}
        )
        self.assertEqual(resp_net.status_code, 200)
        self.assertNotEqual(resp_net.json()["exit_code"], 0)
        self.assertTrue(
            "Forbidden module" in resp_net.json()["stderr"] or 
            "PermissionError" in resp_net.json()["stderr"] or
            "Security Violation" in resp_net.json()["stderr"]
        )

        self.assertEqual(self.observed_external_connections, [])

    def test_05_report_generation_and_download_runs_offline(self):
        """Verify physical report deliverable generation (DOCX/PDF) operates locally."""
        app.dependency_overrides[get_current_user] = lambda: self.user

        doc_content = b"PUMP TEST REPORT DATA: Temperature 65C, Vibration 0.12 mm/s, Status Nominal."
        upload_resp = self.client.post(
            "/documents/upload",
            files={"file": ("pump_test_data.txt", doc_content, "text/plain")},
            data={"visibility": "PRIVATE"}
        )
        doc_id = upload_resp.json()["document_id"]

        gen_resp = self.client.post(
            "/documents/generate",
            json={
                "title": "Offline Pump Analysis Report",
                "format": "docx",
                "document_id": doc_id
            }
        )
        self.assertEqual(gen_resp.status_code, 200)
        report_id = gen_resp.json()["id"]

        # Download physical file
        down_resp = self.client.get(f"/documents/generated/{report_id}/download")
        self.assertEqual(down_resp.status_code, 200)
        self.assertGreater(len(down_resp.content), 100)

        self.assertEqual(self.observed_external_connections, [])
        self.assertEqual(self.observed_dns_lookups, [])

    def test_06_audit_logging_and_hmac_chain_integrity_offline(self):
        """Verify tamper-evident audit logging functions with zero external dependencies."""
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="sandbox.subprocess",
            status="success",
            user_id=501,
            username="airgap_admin",
            role="admin",
            resource="sb_airgap_run",
            metadata={"result": "offline_verified"}
        )
        chain_res = AuditLogger.verify_chain_integrity()
        self.assertEqual(chain_res["status"], "INTACT")
        self.assertEqual(self.observed_external_connections, [])
        self.assertEqual(self.observed_dns_lookups, [])

    def test_07_model_routing_and_inference_offline(self):
        """Verify deterministic task classification and model routing operate without cloud AI calls."""
        from backend.models.router import classify_task_from_prompt, TaskType
        task_gen = classify_task_from_prompt("Explain the thermodynamic Brayton cycle")
        self.assertEqual(task_gen, TaskType.GENERAL_TEXT)

        task_code = classify_task_from_prompt("Write a python script to calculate PID controller constants")
        self.assertEqual(task_code, TaskType.CODING)

        task_vis = classify_task_from_prompt("Analyze this diagram", has_image=True)
        self.assertEqual(task_vis, TaskType.VISION_ANALYSIS)

        self.assertEqual(self.observed_external_connections, [])
        self.assertEqual(self.observed_dns_lookups, [])

    def test_08_conversation_persistence_offline(self):
        """Verify conversation sessions and message history persist locally in SQLite without cloud sync."""
        app.dependency_overrides[get_current_user] = lambda: self.user
        conv_resp = self.client.post("/conversations", json={"title": "Air-Gap Turbomachinery Chat"})
        self.assertEqual(conv_resp.status_code, 200)
        conv_id = conv_resp.json()["id"]

        msg_resp = self.client.post(
            f"/conversations/{conv_id}/messages",
            json={"message": "What is the primary exhaust temperature?"}
        )
        self.assertEqual(msg_resp.status_code, 200)

        # Retrieve conversation
        get_conv = self.client.get(f"/conversations/{conv_id}")
        self.assertEqual(get_conv.status_code, 200)
        self.assertEqual(get_conv.json()["title"], "Air-Gap Turbomachinery Chat")

        self.assertEqual(self.observed_external_connections, [])
        self.assertEqual(self.observed_dns_lookups, [])


if __name__ == "__main__":
    unittest.main()
