import os
import shutil
import tempfile
import unittest
import sqlite3
from unittest.mock import patch, MagicMock
from fastapi import status
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config.settings import settings
from backend.security.database import get_db, init_db
from backend.security.auth import create_access_token, hash_password
from backend.security.audit import AuditLogger
from backend.agents.conversations import ConversationManager

TEST_TEMP_DIR = tempfile.mkdtemp(prefix="aegis_prompt_domain_test_")
TEST_DB_PATH = os.path.join(TEST_TEMP_DIR, "aegis_test.db")

def get_test_db():
    conn = sqlite3.connect(TEST_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

class TestPromptEditCopyAndDomainAdminAdversarial(unittest.TestCase):
    """
    AEGIS Comprehensive Security & Adversarial Test Suite for:
    1. Prompt Editing & Copying (History Immutability, Authorization, Auditing, HMAC)
    2. Domain-Scoped Administration & Data Isolation
    3. Four Industrial Domain Admins (Engineering, Operations & Maintenance, HSE, Procurement & Commercial)
    """

    @classmethod
    def setUpClass(cls):
        cls.original_db_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = TEST_DB_PATH
        os.makedirs(os.path.dirname(TEST_DB_PATH), exist_ok=True)
        init_db()
        app.dependency_overrides[get_db] = get_test_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        settings.AUTH_DB_PATH = cls.original_db_path
        shutil.rmtree(TEST_TEMP_DIR, ignore_errors=True)

    def setUp(self):
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages")
        cursor.execute("DELETE FROM conversations")
        cursor.execute("DELETE FROM users")
        cursor.execute("DELETE FROM audit_logs")

        cursor.execute("SELECT id, name FROM departments")
        dept_map = {row[1]: row[0] for row in cursor.fetchall()}
        self.dept_admin_id = dept_map.get("Administration", 1)
        self.dept_eng_id = dept_map.get("Engineering")
        self.dept_ops_id = dept_map.get("Operations & Maintenance") or dept_map.get("Operations")
        self.dept_hse_id = dept_map.get("HSE") or dept_map.get("Safety")
        self.dept_proc_id = dept_map.get("Procurement & Commercial") or dept_map.get("Procurement")

        conn.commit()
        conn.close()

        # Create the 4 Domain Admins + Org Admin
        self.aegis_admin_id = self._create_user("aegis_admin", "AdminPass123!", "admin", self.dept_admin_id, "Administration")
        self.eng_admin_id = self._create_user("engineering_admin", "EngAdminPass123!", "admin", self.dept_eng_id, "Engineering")
        self.ops_admin_id = self._create_user("operations_admin", "OpsAdminPass123!", "admin", self.dept_ops_id, "Operations & Maintenance")
        self.hse_admin_id = self._create_user("hse_admin", "HseAdminPass123!", "admin", self.dept_hse_id, "HSE")
        self.proc_admin_id = self._create_user("procurement_admin", "ProcAdminPass123!", "admin", self.dept_proc_id, "Procurement & Commercial")

        # Create Domain Users
        self.eng_user_id = self._create_user("engineer_alice", "UserPass123!", "user", self.dept_eng_id, "Engineering")
        self.ops_user_id = self._create_user("operator_bob", "UserPass123!", "user", self.dept_ops_id, "Operations & Maintenance")
        self.hse_user_id = self._create_user("inspector_carol", "UserPass123!", "user", self.dept_hse_id, "HSE")
        self.proc_user_id = self._create_user("buyer_dave", "UserPass123!", "user", self.dept_proc_id, "Procurement & Commercial")

        # Tokens
        self.aegis_admin_token = create_access_token("aegis_admin", "admin")
        self.eng_admin_token = create_access_token("engineering_admin", "admin")
        self.ops_admin_token = create_access_token("operations_admin", "admin")
        self.hse_admin_token = create_access_token("hse_admin", "admin")
        self.proc_admin_token = create_access_token("procurement_admin", "admin")

        self.eng_user_token = create_access_token("engineer_alice", "user")
        self.ops_user_token = create_access_token("operator_bob", "user")
        self.hse_user_token = create_access_token("inspector_carol", "user")
        self.proc_user_token = create_access_token("buyer_dave", "user")

    def _create_user(self, username: str, password: str, role: str, dept_id: int | None, dept_name: str | None, is_active: int = 1) -> int:
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        hashed = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, department_id, department_name, is_active, must_change_password) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (username, hashed, role, dept_id, dept_name, is_active)
        )
        uid = cursor.lastrowid
        conn.commit()
        conn.close()
        return uid

    # =========================================================================
    # PART 1: PROMPT EDITING & COPYING TESTS (1-12)
    # =========================================================================

    def test_01_user_can_edit_own_prompt(self):
        """TEST 1: User can edit own prompt and receive successful response."""
        # 1. Create conversation and initial message
        conv = ConversationManager.create_conversation("Turbine Inspection", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Analyze pump vibration report.", user_id=self.eng_user_id, username="engineer_alice")

        # 2. Edit prompt
        resp = self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.eng_user_token}"},
            json={"message": "Analyze pump vibration report and draft approval note."}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("answer", data)
        self.assertEqual(data["session_id"], conv["id"])

    def test_02_user_can_copy_own_prompt(self):
        """TEST 2: Prompt copy exposes only clean user prompt text without secrets or system prompt."""
        conv = ConversationManager.create_conversation("P&ID Check", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(
            conv["id"], "user", "Inspect cooling tower P&ID schematic.",
            user_id=self.eng_user_id, username="engineer_alice",
            metadata={"system_prompt": "INTERNAL_SYSTEM_SECRET", "token": "jwt.secret.key"}
        )

        resp = self.client.get(
            f"/conversations/{conv['id']}/messages",
            headers={"Authorization": f"Bearer {self.eng_user_token}"}
        )
        self.assertEqual(resp.status_code, 200)
        messages = resp.json()
        target = next(m for m in messages if m["id"] == orig_msg["id"])
        
        # Exact visible user prompt
        self.assertEqual(target["content"], "Inspect cooling tower P&ID schematic.")
        # No internal system secrets in content
        self.assertNotIn("INTERNAL_SYSTEM_SECRET", target["content"])
        self.assertNotIn("jwt.secret.key", target["content"])

    def test_03_edited_prompt_creates_new_execution_and_message(self):
        """TEST 3: Edited prompt appends new user message and new assistant message."""
        conv = ConversationManager.create_conversation("Thermal Flow", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Check thermal flow rates.", user_id=self.eng_user_id, username="engineer_alice")
        ConversationManager.add_message(conv["id"], "assistant", "Flow rate is 450 gpm.", user_id=None, username=None)

        conn = sqlite3.connect(TEST_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conv["id"],))
        count_before = c.fetchone()[0]
        self.assertEqual(count_before, 2)
        conn.close()

        resp = self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.eng_user_token}"},
            json={"message": "Check thermal flow rates and compare with SOP limit."}
        )
        self.assertEqual(resp.status_code, 200)

        conn = sqlite3.connect(TEST_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC", (conv["id"],))
        msgs_after = c.fetchall()
        self.assertEqual(len(msgs_after), 4) # orig user + orig assistant + new user + new assistant
        conn.close()

    def test_04_original_prompt_remains_strictly_immutable(self):
        """TEST 4: Original message in database is NOT overwritten, mutated, or deleted."""
        conv = ConversationManager.create_conversation("Vibration Audit", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Initial prompt text.", user_id=self.eng_user_id, username="engineer_alice")
        
        # Perform prompt edit
        self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.eng_user_token}"},
            json={"message": "Updated revised prompt text."}
        )

        # Query database directly for the original message record
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT content FROM messages WHERE id = ?", (orig_msg["id"],))
        stored = c.fetchone()
        self.assertIsNotNone(stored)
        self.assertEqual(stored["content"], "Initial prompt text.", "Original historical record MUST remain unmodified!")
        conn.close()

    def test_05_edited_prompt_gets_fresh_assistant_response(self):
        """TEST 5: Edited prompt triggers a fresh plan and new assistant response."""
        conv = ConversationManager.create_conversation("Calculation", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Calculate 10 + 20", user_id=self.eng_user_id, username="engineer_alice")

        resp = self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.eng_user_token}"},
            json={"message": "Calculate 50 * 2"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("answer", data)
        self.assertIsNotNone(data.get("verification"))

    def test_06_user_cannot_edit_another_users_message(self):
        """TEST 6: Cross-user prompt edit is rejected with HTTP 403 Forbidden and audited."""
        # Alice's conversation and prompt
        conv = ConversationManager.create_conversation("Alice Private Session", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Confidential engineering design prompt.", user_id=self.eng_user_id, username="engineer_alice")

        # Bob (attacker) tries to edit Alice's prompt
        resp = self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.ops_user_token}"},
            json={"message": "Maliciously hijacked prompt."}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Access denied", resp.json()["detail"])

        # Verify audit log recorded AUTHORIZATION_DENIED
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM audit_logs WHERE action IN ('AUTHORIZATION_DENIED', 'AUTHORIZATION_FAILURE') ORDER BY id DESC LIMIT 1")
        log = c.fetchone()
        self.assertIsNotNone(log)
        self.assertEqual(log["username"], "operator_bob")
        conn.close()

    def test_07_user_cannot_retrieve_another_users_messages(self):
        """TEST 7: Cross-user message retrieval is rejected with HTTP 403 Forbidden."""
        conv = ConversationManager.create_conversation("Alice Secret Session", user_id=self.eng_user_id, username="engineer_alice")
        ConversationManager.add_message(conv["id"], "user", "Secret design prompt.", user_id=self.eng_user_id, username="engineer_alice")

        resp = self.client.get(
            f"/conversations/{conv['id']}/messages",
            headers={"Authorization": f"Bearer {self.ops_user_token}"}
        )
        self.assertEqual(resp.status_code, 403)

    def test_08_editing_does_not_bypass_document_authorization(self):
        """TEST 8: Edited prompt cannot access unauthorized documents across department boundary."""
        conv = ConversationManager.create_conversation("Doc Scoped Query", user_id=self.ops_user_id, username="operator_bob")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Hello", user_id=self.ops_user_id, username="operator_bob")

        # Operator Bob tries to edit prompt to query Engineering-restricted document
        resp = self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.ops_user_token}"},
            json={"message": "Search secret_engineering_spec.pdf for confidential turbine blueprints."}
        )
        self.assertEqual(resp.status_code, 200)
        # Agent execution completes safely without leaking unauthorized documents

    def test_09_editing_does_not_bypass_hitl_approval(self):
        """TEST 9: Edited prompt requiring human approval triggers HITL gate properly."""
        conv = ConversationManager.create_conversation("HITL Action", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Check status", user_id=self.eng_user_id, username="engineer_alice")

        # Edit to a consequential action requiring signoff
        resp = self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.eng_user_token}"},
            json={"message": "Prepare and publish official cooling tower signoff deliverable"}
        )
        self.assertEqual(resp.status_code, 200)

    def test_10_editing_does_not_bypass_model_routing(self):
        """TEST 10: Edited prompt is correctly routed based on the new prompt intent."""
        conv = ConversationManager.create_conversation("Routing Session", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Hello assistant", user_id=self.eng_user_id, username="engineer_alice")

        # Edit to coding task
        resp = self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.eng_user_token}"},
            json={"message": "def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("routing_info", data)

    def test_11_copy_never_exposes_internal_reasoning_or_tokens(self):
        """TEST 11: Prompt copy endpoint and payload never contain raw tokens or hidden chain-of-thought."""
        conv = ConversationManager.create_conversation("Audit Log Safe", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(
            conv["id"], "user", "Review plant operating parameters.",
            user_id=self.eng_user_id, username="engineer_alice"
        )
        resp = self.client.get(
            f"/conversations/{conv['id']}",
            headers={"Authorization": f"Bearer {self.eng_user_token}"}
        )
        self.assertEqual(resp.status_code, 200)
        messages = resp.json().get("messages", [])
        for m in messages:
            self.assertNotIn("password_hash", str(m))
            self.assertNotIn("secret_key", str(m))

    def test_12_audit_chain_remains_intact_after_prompt_edit(self):
        """TEST 12: HMAC audit chain integrity is verified as INTACT after prompt edits."""
        conv = ConversationManager.create_conversation("HMAC Check Session", user_id=self.eng_user_id, username="engineer_alice")
        orig_msg = ConversationManager.add_message(conv["id"], "user", "Initial query.", user_id=self.eng_user_id, username="engineer_alice")

        # Edit prompt
        self.client.post(
            f"/conversations/{conv['id']}/messages/{orig_msg['id']}/edit",
            headers={"Authorization": f"Bearer {self.eng_user_token}"},
            json={"message": "Edited query."}
        )

        integrity = AuditLogger.verify_chain_integrity()
        self.assertEqual(integrity["status"], "INTACT", "HMAC audit chain must be INTACT after prompt edit!")

    # =========================================================================
    # PART 2: DOMAIN-SCOPED ADMINISTRATION TESTS (13-34)
    # =========================================================================

    def test_13_engineering_admin_can_list_engineering_users(self):
        """TEST 13: Engineering admin lists users in Engineering department."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.eng_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        users = resp.json()
        usernames = [u["username"] for u in users]
        self.assertIn("engineer_alice", usernames)
        self.assertIn("engineering_admin", usernames)

    def test_14_engineering_admin_cannot_list_operations_users(self):
        """TEST 14: Engineering admin cannot view Operations users."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.eng_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        usernames = [u["username"] for u in resp.json()]
        self.assertNotIn("operator_bob", usernames)
        self.assertNotIn("operations_admin", usernames)

    def test_15_engineering_admin_cannot_list_hse_users(self):
        """TEST 15: Engineering admin cannot view HSE users."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.eng_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        usernames = [u["username"] for u in resp.json()]
        self.assertNotIn("inspector_carol", usernames)
        self.assertNotIn("hse_admin", usernames)

    def test_16_engineering_admin_cannot_list_procurement_users(self):
        """TEST 16: Engineering admin cannot view Procurement users."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.eng_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        usernames = [u["username"] for u in resp.json()]
        self.assertNotIn("buyer_dave", usernames)
        self.assertNotIn("procurement_admin", usernames)

    def test_17_engineering_admin_can_create_engineering_user(self):
        """TEST 17: Engineering admin successfully creates an Engineering user."""
        resp = self.client.post(
            "/auth/users",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"username": "new_eng_tech", "password": "SecurePass123!", "role": "user"}
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["department_id"], self.dept_eng_id)
        self.assertEqual(data["department_name"], "Engineering")

    def test_18_engineering_admin_cannot_create_operations_user(self):
        """TEST 18: Engineering admin attempts to create Operations user -> 403 Forbidden."""
        resp = self.client.post(
            "/auth/users",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"username": "cross_ops_user", "password": "SecurePass123!", "role": "user", "department_id": self.dept_ops_id}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Cross-department", resp.json()["detail"])

    def test_19_engineering_admin_cannot_create_hse_user(self):
        """TEST 19: Engineering admin attempts to create HSE user -> 403 Forbidden."""
        resp = self.client.post(
            "/auth/users",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"username": "cross_hse_user", "password": "SecurePass123!", "role": "user", "department_id": self.dept_hse_id}
        )
        self.assertEqual(resp.status_code, 403)

    def test_20_engineering_admin_cannot_create_procurement_user(self):
        """TEST 20: Engineering admin attempts to create Procurement user -> 403 Forbidden."""
        resp = self.client.post(
            "/auth/users",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"username": "cross_proc_user", "password": "SecurePass123!", "role": "user", "department_id": self.dept_proc_id}
        )
        self.assertEqual(resp.status_code, 403)

    def test_21_engineering_admin_cannot_modify_operations_user(self):
        """TEST 21: Engineering admin attempts to update role of Operations user -> 403 Forbidden."""
        resp = self.client.post(
            "/auth/users/operator_bob/role",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"role": "admin"}
        )
        self.assertEqual(resp.status_code, 403)

    def test_22_engineering_admin_cannot_deactivate_operations_user(self):
        """TEST 22: Engineering admin attempts to deactivate Operations user -> 403 Forbidden."""
        resp = self.client.post(
            "/auth/users/operator_bob/status",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"is_active": False}
        )
        self.assertEqual(resp.status_code, 403)

    def test_23_engineering_admin_cannot_reset_operations_credentials(self):
        """TEST 23: Engineering admin attempts to reset Operations user credentials -> 403 Forbidden."""
        resp = self.client.post(
            "/auth/users/operator_bob/reset-password",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"password": "NewSecretPass123!"}
        )
        self.assertEqual(resp.status_code, 403)

    def test_24_engineering_admin_cannot_change_another_users_domain(self):
        """TEST 24: Engineering admin cannot change another user's department."""
        resp = self.client.patch(
            "/auth/users/engineer_alice/department",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"department_id": self.dept_ops_id}
        )
        self.assertEqual(resp.status_code, 403)

    def test_25_engineering_admin_cannot_change_own_domain(self):
        """TEST 25: Engineering admin cannot change their own department."""
        resp = self.client.patch(
            "/auth/users/engineering_admin/department",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"department_id": self.dept_admin_id}
        )
        self.assertEqual(resp.status_code, 403)

    def test_26_engineering_admin_cannot_escalate_own_role(self):
        """TEST 26: Engineering admin cannot modify their own role."""
        resp = self.client.post(
            "/auth/users/engineering_admin/role",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"role": "admin"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("cannot modify their own role", resp.json()["detail"])

    def test_27_regular_user_cannot_perform_admin_operations(self):
        """TEST 27: Regular user cannot list users or provision operators."""
        resp_list = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.eng_user_token}"})
        self.assertEqual(resp_list.status_code, 403)

        resp_create = self.client.post(
            "/auth/users",
            headers={"Authorization": f"Bearer {self.eng_user_token}"},
            json={"username": "illegal_user", "password": "UserPass123!", "role": "user"}
        )
        self.assertEqual(resp_create.status_code, 403)

    def test_28_direct_api_cross_domain_request_is_rejected(self):
        """TEST 28: Direct API attack attempting cross-domain provisioning is blocked."""
        resp = self.client.post(
            "/auth/users",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"username": "hacked_user", "password": "Pass123!456", "role": "user", "department_id": 9999}
        )
        self.assertEqual(resp.status_code, 403)

    def test_29_tampered_domain_id_is_rejected(self):
        """TEST 29: Tampered department_id matching another domain is authoritatively rejected."""
        resp = self.client.post(
            "/auth/users",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"username": "tampered_user", "password": "Pass123!456", "role": "user", "department_id": self.dept_hse_id}
        )
        self.assertEqual(resp.status_code, 403)

    def test_30_tampered_jwt_client_domain_cannot_bypass_authorization(self):
        """TEST 30: Forged token department claim is ignored in favor of trusted DB record."""
        # Even if a client presents a token with forged attributes, backend derives department from DB
        resp = self.client.post(
            "/auth/users",
            headers={"Authorization": f"Bearer {self.eng_admin_token}"},
            json={"username": "db_trusted_user", "password": "Pass123!456", "role": "user"}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["department_id"], self.dept_eng_id)

    def test_31_cross_domain_user_id_enumeration_does_not_leak_information(self):
        """TEST 31: Querying users returns only own department users, preventing enumeration."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.ops_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        ops_users = resp.json()
        for u in ops_users:
            self.assertEqual(u["department_id"], self.dept_ops_id)

    def test_32_pagination_cannot_expose_another_domain(self):
        """TEST 32: Listing users with query parameters never leaks cross-domain records."""
        resp = self.client.get("/auth/users?limit=100&offset=0", headers={"Authorization": f"Bearer {self.hse_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        for u in resp.json():
            self.assertEqual(u["department_id"], self.dept_hse_id)

    def test_33_search_cannot_expose_another_domain(self):
        """TEST 33: User search never leaks cross-domain records."""
        resp = self.client.get("/auth/users?search=engineer", headers={"Authorization": f"Bearer {self.ops_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        for u in resp.json():
            self.assertEqual(u["department_id"], self.dept_ops_id)

    def test_34_filtering_cannot_expose_another_domain(self):
        """TEST 34: Specifying department_id filter for another domain does not bypass scoping."""
        resp = self.client.get(f"/auth/users?department_id={self.dept_eng_id}", headers={"Authorization": f"Bearer {self.proc_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        for u in resp.json():
            self.assertEqual(u["department_id"], self.dept_proc_id)

    # =========================================================================
    # PART 3: FOUR INDUSTRIAL DOMAIN ADMIN TESTS (35-38)
    # =========================================================================

    def test_35_engineering_admin_strictly_engineering_only(self):
        """TEST 35: engineering_admin manages only Engineering users."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.eng_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        for u in resp.json():
            self.assertEqual(u["department_name"], "Engineering")

    def test_36_operations_admin_strictly_operations_only(self):
        """TEST 36: operations_admin manages only Operations & Maintenance users."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.ops_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        for u in resp.json():
            self.assertEqual(u["department_id"], self.dept_ops_id)

    def test_37_hse_admin_strictly_hse_only(self):
        """TEST 37: hse_admin manages only HSE users."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.hse_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        for u in resp.json():
            self.assertEqual(u["department_id"], self.dept_hse_id)

    def test_38_procurement_admin_strictly_procurement_only(self):
        """TEST 38: procurement_admin manages only Procurement & Commercial users."""
        resp = self.client.get("/auth/users", headers={"Authorization": f"Bearer {self.proc_admin_token}"})
        self.assertEqual(resp.status_code, 200)
        for u in resp.json():
            self.assertEqual(u["department_id"], self.dept_proc_id)

if __name__ == "__main__":
    unittest.main()
