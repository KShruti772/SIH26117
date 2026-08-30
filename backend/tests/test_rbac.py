import os
import unittest
import sqlite3
from fastapi import status
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.security.database import get_db, get_db_path, init_db
from backend.security.auth import create_access_token, hash_password
from backend.agents.conversations import ConversationManager
from backend.security.audit import AuditLogger

class TestAegisRBAC(unittest.TestCase):
    """Suite to verify all RBAC authorization controls, conversation ownership, and audit logging."""

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username IN ('user_a', 'user_b', 'admin_user', 'demoted_user')")
        cursor.execute("DELETE FROM conversations WHERE username IN ('user_a', 'user_b', 'admin_user', 'demoted_user')")
        cursor.execute("DELETE FROM audit_logs WHERE username IN ('user_a', 'user_b', 'admin_user', 'demoted_user')")
        conn.commit()
        conn.close()

        # Provision Test Users
        self.user_a_id = self._create_test_user("user_a", "password123", "user")
        self.user_b_id = self._create_test_user("user_b", "password123", "user")
        self.admin_id = self._create_test_user("admin_user", "password123", "admin")

        self.user_a_token = create_access_token("user_a", "user")
        self.user_b_token = create_access_token("user_b", "user")
        self.admin_token = create_access_token("admin_user", "admin")

    def _create_test_user(self, username: str, password: str, role: str) -> int:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        hashed = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, 1)",
            (username, hashed, role)
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id

    def test_user_cannot_select_model(self):
        """TEST 1: Standard user receives HTTP 403 on POST /models/select."""
        res = self.client.post(
            "/models/select",
            json={"model_id": "qwen3:4b"},
            headers={"Authorization": f"Bearer {self.user_a_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_select_model(self):
        """TEST 2: Admin receives authorized response on POST /models/select."""
        res = self.client.post(
            "/models/select",
            json={"model_id": "gemma3:4b"},
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertIn(res.status_code, (status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE))

    def test_user_cannot_access_other_user_conversation(self):
        """TEST 3: User B receiving HTTP 403 when requesting User A's conversation."""
        conv = ConversationManager.create_conversation("User A Private Conv", user_id=self.user_a_id, username="user_a")
        res = self.client.get(
            f"/conversations/{conv['id']}",
            headers={"Authorization": f"Bearer {self.user_b_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Access denied", res.json()["detail"])

    def test_user_cannot_delete_other_user_conversation(self):
        """TEST 4: User B receiving HTTP 403 when attempting to delete User A's conversation."""
        conv = ConversationManager.create_conversation("User A Retained Conv", user_id=self.user_a_id, username="user_a")
        res = self.client.delete(
            f"/conversations/{conv['id']}",
            headers={"Authorization": f"Bearer {self.user_b_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        
        # Verify conversation was not deleted
        fetched = ConversationManager.get_conversation_owner(conv['id'])
        self.assertIsNotNone(fetched)

    def test_user_can_access_own_conversation(self):
        """TEST 5: User A successfully fetches own conversation session."""
        conv = ConversationManager.create_conversation("User A Session", user_id=self.user_a_id, username="user_a")
        res = self.client.get(
            f"/conversations/{conv['id']}",
            headers={"Authorization": f"Bearer {self.user_a_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["id"], conv['id'])

    def test_user_can_delete_own_conversation(self):
        """TEST 6: User A successfully deletes own conversation session."""
        conv = ConversationManager.create_conversation("User A To Delete", user_id=self.user_a_id, username="user_a")
        res = self.client.delete(
            f"/conversations/{conv['id']}",
            headers={"Authorization": f"Bearer {self.user_a_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["status"], "success")

    def test_admin_can_access_other_user_conversation(self):
        """TEST 7: Admin successfully fetches User A's conversation session."""
        conv = ConversationManager.create_conversation("User A Session For Admin", user_id=self.user_a_id, username="user_a")
        res = self.client.get(
            f"/conversations/{conv['id']}",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["id"], conv['id'])

    def test_admin_can_delete_other_user_conversation(self):
        """TEST 8: Admin successfully deletes User A's conversation session."""
        conv = ConversationManager.create_conversation("User A Session For Admin Delete", user_id=self.user_a_id, username="user_a")
        res = self.client.delete(
            f"/conversations/{conv['id']}",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["status"], "success")

    def test_immediate_role_demotion_blocks_model_selection(self):
        """TEST 9: Changing user role from admin to user in DB immediately blocks admin endpoints."""
        demoted_id = self._create_test_user("demoted_user", "password123", "admin")
        token = create_access_token("demoted_user", "admin")

        # Confirm initial access works
        r1 = self.client.get("/audit/summary", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        # Update role to user in DB
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE users SET role = 'user' WHERE username = 'demoted_user'")
        conn.commit()
        conn.close()

        # Immediate request with same token must fail with 403
        r2 = self.client.get("/audit/summary", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r2.status_code, status.HTTP_403_FORBIDDEN)

    def test_authorization_denied_is_audited(self):
        """TEST 10: Failed role checks generate AUTHORIZATION_DENIED audit events in SQLite database."""
        self.client.post(
            "/models/select",
            json={"model_id": "qwen3:4b"},
            headers={"Authorization": f"Bearer {self.user_a_token}"}
        )
        
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action = 'AUTHORIZATION_DENIED' AND username = 'user_a' ORDER BY id DESC LIMIT 1")
        log = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(log)
        self.assertEqual(log["action"], "AUTHORIZATION_DENIED")
        self.assertEqual(log["status"], "failure")

    def test_cross_user_conversation_denial_is_audited(self):
        """TEST 11: Cross-user conversation attempts generate AUTHORIZATION_DENIED audit log events."""
        conv = ConversationManager.create_conversation("User A Private Conv 2", user_id=self.user_a_id, username="user_a")
        self.client.get(
            f"/conversations/{conv['id']}",
            headers={"Authorization": f"Bearer {self.user_b_token}"}
        )

        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action = 'AUTHORIZATION_DENIED' AND username = 'user_b' ORDER BY id DESC LIMIT 1")
        log = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(log)
        self.assertEqual(log["action"], "AUTHORIZATION_DENIED")
        self.assertEqual(log["username"], "user_b")

    def test_admin_authorization_still_works(self):
        """TEST 12: Admin role can access admin endpoints cleanly."""
        r_users = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_users.status_code, status.HTTP_200_OK)

        r_audit = self.client.get("/audit", headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_audit.status_code, status.HTTP_200_OK)

if __name__ == "__main__":
    unittest.main()
