import unittest
import os
import tempfile
import sqlite3
import json
from fastapi.testclient import TestClient
from backend.security import database
from backend.agents.conversations import ConversationManager, generate_deterministic_title
from backend.security.audit import AuditLogger, get_request_id, set_request_id
from backend.security.auth import create_access_token, hash_password
from backend.app.main import app

class TestConversationManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_aegis.db")
        database.settings.AUTH_DB_PATH = self.db_path
        database.init_db()
        self.client = TestClient(app)

        # Create test users
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("user_alpha", hash_password("PassAlpha123!"), "user", 1)
        )
        self.user_alpha_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("user_beta", hash_password("PassBeta123!"), "user", 1)
        )
        self.user_beta_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("admin_test", hash_password("AdminPass123!"), "admin", 1)
        )
        self.admin_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.token_alpha = create_access_token("user_alpha", "user")
        self.token_beta = create_access_token("user_beta", "user")
        self.token_admin = create_access_token("admin_test", "admin")

    def test_deterministic_title_generation(self):
        """Verify deterministic human-readable conversation titles without LLM dependency."""
        self.assertEqual(
            generate_deterministic_title("What is the emergency shutdown procedure?"),
            "Emergency Shutdown Procedure"
        )
        self.assertEqual(
            generate_deterministic_title("write a python factorial function"),
            "Factorial Function"
        )
        self.assertEqual(
            generate_deterministic_title("how to configure boiler pressure limits"),
            "Configure Boiler Pressure Limits"
        )
        self.assertEqual(
            generate_deterministic_title(""),
            "New Conversation"
        )

    def test_create_and_get_conversation(self):
        """Verify conversation creation with all metadata and retrieval."""
        conv = ConversationManager.create_conversation(
            title="Cooling System Ingestion",
            user_id=self.user_alpha_id,
            username="user_alpha",
            feature="chat"
        )
        self.assertIsNotNone(conv["id"])
        self.assertEqual(conv["title"], "Cooling System Ingestion")
        self.assertEqual(conv["user_id"], self.user_alpha_id)
        self.assertEqual(conv["username"], "user_alpha")
        self.assertEqual(conv["feature"], "chat")
        self.assertEqual(conv["status"], "active")

        fetched = ConversationManager.get_conversation(conv["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], conv["id"])
        self.assertEqual(fetched["title"], "Cooling System Ingestion")
        self.assertEqual(len(fetched["messages"]), 0)

    def test_conversation_persistence_across_reconnect(self):
        """Verify conversation and messages survive new database connections."""
        conv = ConversationManager.create_conversation(
            title="Persistent Session",
            user_id=self.user_alpha_id,
            username="user_alpha"
        )
        sid = conv["id"]

        ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="Check sensor status",
            user_id=self.user_alpha_id,
            username="user_alpha"
        )
        ConversationManager.add_message(
            session_id=sid,
            role="assistant",
            content="Sensors operational.",
            user_id=self.user_alpha_id,
            username="user_alpha",
            rag_used=True,
            sources=[{"filename": "sensors.pdf", "page": 1, "distance": 0.12}]
        )

        # Fresh query on new connection
        fetched = ConversationManager.get_conversation(sid)
        self.assertIsNotNone(fetched)
        self.assertEqual(len(fetched["messages"]), 2)
        self.assertEqual(fetched["messages"][0]["content"], "Check sensor status")
        self.assertEqual(fetched["messages"][1]["content"], "Sensors operational.")
        self.assertTrue(fetched["messages"][1]["rag_used"])
        self.assertEqual(len(fetched["messages"][1]["sources"]), 1)
        self.assertEqual(fetched["messages"][1]["sources"][0]["filename"], "sensors.pdf")

    def test_user_isolation_in_listing(self):
        """Verify User Alpha only sees User Alpha conversations and User Beta only sees User Beta conversations."""
        conv_a1 = ConversationManager.create_conversation(
            title="Alpha Conv 1", user_id=self.user_alpha_id, username="user_alpha"
        )
        conv_a2 = ConversationManager.create_conversation(
            title="Alpha Conv 2", user_id=self.user_alpha_id, username="user_alpha"
        )
        conv_b1 = ConversationManager.create_conversation(
            title="Beta Conv 1", user_id=self.user_beta_id, username="user_beta"
        )

        alpha_list = ConversationManager.list_conversations(user_id=self.user_alpha_id, username="user_alpha")
        alpha_ids = [c["id"] for c in alpha_list]
        self.assertIn(conv_a1["id"], alpha_ids)
        self.assertIn(conv_a2["id"], alpha_ids)
        self.assertNotIn(conv_b1["id"], alpha_ids)

        beta_list = ConversationManager.list_conversations(user_id=self.user_beta_id, username="user_beta")
        beta_ids = [c["id"] for c in beta_list]
        self.assertIn(conv_b1["id"], beta_ids)
        self.assertNotIn(conv_a1["id"], beta_ids)
        self.assertNotIn(conv_a2["id"], beta_ids)

    def test_api_list_conversations_user_isolated(self):
        """Verify GET /conversations returns strictly authenticated user's conversations."""
        ConversationManager.create_conversation(
            title="Alpha Secret", user_id=self.user_alpha_id, username="user_alpha"
        )
        ConversationManager.create_conversation(
            title="Beta Secret", user_id=self.user_beta_id, username="user_beta"
        )

        res_alpha = self.client.get("/conversations", headers={"Authorization": f"Bearer {self.token_alpha}"})
        self.assertEqual(res_alpha.status_code, 200)
        alpha_titles = [c["title"] for c in res_alpha.json()]
        self.assertIn("Alpha Secret", alpha_titles)
        self.assertNotIn("Beta Secret", alpha_titles)

        res_beta = self.client.get("/conversations", headers={"Authorization": f"Bearer {self.token_beta}"})
        self.assertEqual(res_beta.status_code, 200)
        beta_titles = [c["title"] for c in res_beta.json()]
        self.assertIn("Beta Secret", beta_titles)
        self.assertNotIn("Alpha Secret", beta_titles)

    def test_api_get_conversation_authorization_forbidden(self):
        """Verify GET /conversations/{id} returns 403 when User Beta tries to read User Alpha's session."""
        conv_a = ConversationManager.create_conversation(
            title="Alpha Private", user_id=self.user_alpha_id, username="user_alpha"
        )
        res = self.client.get(
            f"/conversations/{conv_a['id']}",
            headers={"Authorization": f"Bearer {self.token_beta}"}
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Access denied", res.json()["detail"])

    def test_api_patch_conversation_title(self):
        """Verify PATCH /conversations/{id} updates title with ownership verification."""
        conv_a = ConversationManager.create_conversation(
            title="Original Title", user_id=self.user_alpha_id, username="user_alpha"
        )

        # Unauthorized attempt by user_beta
        res_unauth = self.client.patch(
            f"/conversations/{conv_a['id']}",
            json={"title": "Hacked Title"},
            headers={"Authorization": f"Bearer {self.token_beta}"}
        )
        self.assertEqual(res_unauth.status_code, 403)

        # Authorized update by user_alpha
        res_auth = self.client.patch(
            f"/conversations/{conv_a['id']}",
            json={"title": "Updated Title Alpha"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        self.assertEqual(res_auth.status_code, 200)
        self.assertEqual(res_auth.json()["title"], "Updated Title Alpha")

        fetched = ConversationManager.get_conversation(conv_a["id"])
        self.assertEqual(fetched["title"], "Updated Title Alpha")

    def test_api_delete_conversation_cascades_messages(self):
        """Verify DELETE /conversations/{id} deletes conversation and all its messages."""
        conv = ConversationManager.create_conversation(
            title="To Delete", user_id=self.user_alpha_id, username="user_alpha"
        )
        sid = conv["id"]

        ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="Message 1",
            user_id=self.user_alpha_id,
            username="user_alpha"
        )

        res = self.client.delete(
            f"/conversations/{sid}",
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        self.assertEqual(res.status_code, 200)

        # Verify conversation and messages are gone
        self.assertIsNone(ConversationManager.get_conversation(sid))
        self.assertEqual(len(ConversationManager.get_messages(sid)), 0)

    def test_add_message_auto_updates_title_from_first_prompt(self):
        """Verify adding user message to 'New Conversation' updates title to deterministic title."""
        conv = ConversationManager.create_conversation(
            title="New Conversation",
            user_id=self.user_alpha_id,
            username="user_alpha"
        )
        sid = conv["id"]

        ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="What is the emergency shutdown procedure for reactor 4?",
            user_id=self.user_alpha_id,
            username="user_alpha"
        )

        fetched = ConversationManager.get_conversation(sid)
        self.assertNotEqual(fetched["title"], "New Conversation")
        self.assertIn("Emergency Shutdown Procedure", fetched["title"])

    def test_audit_event_logged_on_conversation_lifecycle(self):
        """Verify real audit events are logged for conversation operations without random fake entries."""
        res = self.client.post(
            "/conversations",
            json={"title": "Audited Session"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        self.assertEqual(res.status_code, 200)
        sid = res.json()["id"]

        # Check audit log in DB
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT action, resource, status, user_id, username FROM audit_logs WHERE resource = ?", (sid,))
        rows = cursor.fetchall()
        conn.close()

        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "CONVERSATION_CREATED")
        self.assertEqual(rows[0]["status"], "success")
        self.assertEqual(rows[0]["user_id"], self.user_alpha_id)
        self.assertEqual(rows[0]["username"], "user_alpha")

if __name__ == "__main__":
    unittest.main()
