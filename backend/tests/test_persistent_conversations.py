import os
import shutil
import tempfile
import sqlite3
import unittest
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.security.auth import create_access_token, hash_password
from backend.agents.conversations import ConversationManager, generate_deterministic_title
from backend.app.main import app

class TestPersistentConversations(unittest.TestCase):
    """Comprehensive test suite for persistent, isolated, RBAC-protected AI Assistant conversations."""

    @classmethod
    def setUpClass(cls):
        cls.orig_db_path = settings.AUTH_DB_PATH
        cls.test_dir = tempfile.mkdtemp(prefix="aegis_conv_test_")
        cls.db_path = os.path.join(cls.test_dir, "test_conversations.db")
        settings.AUTH_DB_PATH = cls.db_path
        init_db()

        # Provision test users
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("operator_alpha", hash_password("AlphaPass123!"), "user", 1)
        )
        cls.user_alpha_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("operator_beta", hash_password("BetaPass123!"), "user", 1)
        )
        cls.user_beta_id = cursor.lastrowid

        conn.commit()
        conn.close()

        cls.token_alpha = create_access_token("operator_alpha", "user")
        cls.token_beta = create_access_token("operator_beta", "user")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls.orig_db_path
        init_db()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_empty_user_returns_zero_conversations(self):
        """1. New user has zero conversations initially."""
        res = self.client.get("/conversations", headers={"Authorization": f"Bearer {self.token_alpha}"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_02_create_conversation_persists_in_sqlite(self):
        """2. POST /conversations creates persistent record in SQLite."""
        res = self.client.post(
            "/conversations",
            json={"title": "New Conversation"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        self.assertEqual(res.status_code, 200)
        conv = res.json()
        self.assertTrue(conv["id"].startswith("conv_"))
        self.assertEqual(conv["username"], "operator_alpha")
        self.assertEqual(conv["user_id"], self.user_alpha_id)

        # Direct SQLite inspection
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv["id"],)).fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_03_title_auto_derives_from_first_user_message(self):
        """3. Sending first prompt updates 'New Conversation' title deterministically."""
        res_c = self.client.post(
            "/conversations",
            json={"title": "New Conversation"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        sid = res_c.json()["id"]

        # Add message
        ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="What is the emergency shutdown procedure for unit 3?",
            user_id=self.user_alpha_id,
            username="operator_alpha"
        )

        conv = ConversationManager.get_conversation(sid)
        self.assertNotEqual(conv["title"], "New Conversation")
        self.assertIn("Emergency Shutdown Procedure", conv["title"])

    def test_04_message_persistence_and_chronological_ordering(self):
        """4. User and assistant messages persist and load in chronological sequence."""
        res_c = self.client.post(
            "/conversations",
            json={"title": "Reactor Telemetry"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        sid = res_c.json()["id"]

        ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="Check core pressure limits",
            user_id=self.user_alpha_id,
            username="operator_alpha"
        )
        ConversationManager.add_message(
            session_id=sid,
            role="assistant",
            content="Core pressure is within nominal 4.2 bar envelope.",
            user_id=self.user_alpha_id,
            username="operator_alpha",
            model_id="gemma3:4b",
            rag_used=True,
            verification="GROUNDED"
        )

        res = self.client.get(f"/conversations/{sid}", headers={"Authorization": f"Bearer {self.token_alpha}"})
        self.assertEqual(res.status_code, 200)
        messages = res.json()["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Check core pressure limits")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["model_id"], "gemma3:4b")
        self.assertTrue(messages[1]["rag_used"])
        self.assertEqual(messages[1]["verification"], "GROUNDED")

    def test_05_multi_tenant_user_isolation(self):
        """5. Operator Beta cannot list, read, or post into Operator Alpha's conversation."""
        res_c = self.client.post(
            "/conversations",
            json={"title": "Alpha Confidential Session"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        sid_alpha = res_c.json()["id"]

        # Beta lists conversations -> Must NOT see Alpha's session
        res_beta_list = self.client.get("/conversations", headers={"Authorization": f"Bearer {self.token_beta}"})
        self.assertEqual(res_beta_list.status_code, 200)
        beta_ids = [c["id"] for c in res_beta_list.json()]
        self.assertNotIn(sid_alpha, beta_ids)

        # Beta attempts direct GET on Alpha's conversation -> 403 Forbidden
        res_unauth_get = self.client.get(
            f"/conversations/{sid_alpha}",
            headers={"Authorization": f"Bearer {self.token_beta}"}
        )
        self.assertEqual(res_unauth_get.status_code, 403)

        # Beta attempts direct POST /messages into Alpha's conversation -> 403 Forbidden
        res_unauth_post = self.client.post(
            f"/conversations/{sid_alpha}/messages",
            json={"message": "Malicious injected prompt"},
            headers={"Authorization": f"Bearer {self.token_beta}"}
        )
        self.assertEqual(res_unauth_post.status_code, 403)

        # Beta attempts DELETE on Alpha's conversation -> 403 Forbidden
        res_unauth_del = self.client.delete(
            f"/conversations/{sid_alpha}",
            headers={"Authorization": f"Bearer {self.token_beta}"}
        )
        self.assertEqual(res_unauth_del.status_code, 403)

    def test_06_delete_conversation_cascades(self):
        """6. DELETE /conversations/{id} permanently removes conversation and all associated messages."""
        res_c = self.client.post(
            "/conversations",
            json={"title": "Temporary Session"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        sid = res_c.json()["id"]

        ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="Disposable prompt",
            user_id=self.user_alpha_id,
            username="operator_alpha"
        )

        res_del = self.client.delete(f"/conversations/{sid}", headers={"Authorization": f"Bearer {self.token_alpha}"})
        self.assertEqual(res_del.status_code, 200)

        # Verify not found in SQLite
        conn = sqlite3.connect(self.db_path)
        conv_row = conn.execute("SELECT * FROM conversations WHERE id = ?", (sid,)).fetchone()
        msg_rows = conn.execute("SELECT * FROM messages WHERE conversation_id = ?", (sid,)).fetchall()
        conn.close()

        self.assertIsNone(conv_row)
        self.assertEqual(len(msg_rows), 0)

        # Verify 404 on subsequent GET
        res_get_after = self.client.get(f"/conversations/{sid}", headers={"Authorization": f"Bearer {self.token_alpha}"})
        self.assertEqual(res_get_after.status_code, 404)

    def test_07_conversations_ordered_by_updated_at_desc(self):
        """7. Most recently active conversation appears first in list."""
        c1 = self.client.post("/conversations", json={"title": "Session Older"}, headers={"Authorization": f"Bearer {self.token_alpha}"}).json()
        c2 = self.client.post("/conversations", json={"title": "Session Newer"}, headers={"Authorization": f"Bearer {self.token_alpha}"}).json()

        # Update c1 with new message
        ConversationManager.add_message(
            session_id=c1["id"],
            role="user",
            content="Bumping session older to top",
            user_id=self.user_alpha_id,
            username="operator_alpha"
        )

        res = self.client.get("/conversations", headers={"Authorization": f"Bearer {self.token_alpha}"})
        items = res.json()
        self.assertEqual(items[0]["id"], c1["id"])

    def test_08_invalid_session_id_format_rejected(self):
        """8. Malformed session IDs with illegal characters or excessive length return HTTP 400."""
        malformed_ids = [
            "conv;drop_table",
            "conv space 123",
            "conv<script>",
            "conv$*@!",
            "a" * 100
        ]
        for sid in malformed_ids:
            res_get = self.client.get(f"/conversations/{sid}", headers={"Authorization": f"Bearer {self.token_alpha}"})
            self.assertEqual(res_get.status_code, 400)

            res_del = self.client.delete(f"/conversations/{sid}", headers={"Authorization": f"Bearer {self.token_alpha}"})
            self.assertEqual(res_del.status_code, 400)

    def test_09_nonexistent_conversation_returns_404(self):
        """9. Querying nonexistent valid session ID returns HTTP 404."""
        res = self.client.get("/conversations/conv_nonexistent_9999", headers={"Authorization": f"Bearer {self.token_alpha}"})
        self.assertEqual(res.status_code, 404)

    def test_10_custom_title_preserved_on_message(self):
        """10. Explicitly set custom conversation title is not overwritten by auto-title derivation."""
        res_c = self.client.post(
            "/conversations",
            json={"title": "Project Orion Custom Title"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        sid = res_c.json()["id"]

        ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="What is the chemical composition of alloy 718?",
            user_id=self.user_alpha_id,
            username="operator_alpha"
        )

        conv = ConversationManager.get_conversation(sid)
        self.assertEqual(conv["title"], "Project Orion Custom Title")

    def test_11_message_metadata_and_document_ids_persisted(self):
        """11. Rich metadata (task_type, document_ids, model_id) persists and returns accurately."""
        res_c = self.client.post(
            "/conversations",
            json={"title": "Telemetry Analysis"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        sid = res_c.json()["id"]

        meta = {
            "task_type": "DOCUMENT_QA",
            "document_ids": ["manual_v2.pdf", "specs.docx"],
            "selected_model": "gemma3:4b",
            "grounding_status": "GROUNDED"
        }

        ConversationManager.add_message(
            session_id=sid,
            role="assistant",
            content="Found nominal parameters in manual_v2.pdf.",
            user_id=self.user_alpha_id,
            username="operator_alpha",
            model_id="gemma3:4b",
            rag_used=True,
            verification="GROUNDED",
            metadata=meta
        )

        conv = ConversationManager.get_conversation(sid)
        msg = conv["messages"][0]
        self.assertEqual(msg["task_type"], "DOCUMENT_QA")
        self.assertEqual(msg["document_ids"], ["manual_v2.pdf", "specs.docx"])
        self.assertEqual(msg["model_id"], "gemma3:4b")
        self.assertTrue(msg["rag_used"])
        self.assertEqual(msg["verification"], "GROUNDED")

    def test_12_test_database_isolation(self):
        """12. Verify this test suite operates strictly on its isolated temporary SQLite database."""
        self.assertTrue(self.db_path.endswith("test_conversations.db"))
        self.assertNotEqual(self.db_path, self.orig_db_path)
        self.assertTrue(os.path.exists(self.db_path))

if __name__ == "__main__":
    unittest.main()
