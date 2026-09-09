import os
import json
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.security.models import ApprovalStatus, ApprovalActionType
from backend.security.audit import AuditLogger, VALID_ACTIONS, ALLOWED_METADATA_KEYS

class TestHitlDatabaseAuditFoundation(unittest.TestCase):
    """
    Focused verification suite for AEGIS Phase 1:
    Secure HITL Database Schema, State Representation, Action Types, and Cryptographic Audit Foundation.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aegis_hitl_test_")
        self.test_db = os.path.join(self.test_dir, "aegis_hitl_test.db")
        self.orig_db_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = self.test_db

    def tearDown(self):
        settings.AUTH_DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # =========================================================================
    # TEST 1: Fresh Database Initialization Creates approval_requests Table & Indexes
    # =========================================================================
    def test_01_fresh_database_initialization(self):
        """Verify that init_db() creates approval_requests with all required columns and performance indexes."""
        init_db()

        self.assertTrue(os.path.exists(self.test_db), "Database file must be created.")

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()

        # Verify table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='approval_requests'")
        self.assertIsNotNone(cursor.fetchone(), "Table 'approval_requests' must exist.")

        # Verify column schema
        cursor.execute("PRAGMA table_info(approval_requests)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        required_columns = {
            "id": "TEXT",
            "plan_id": "TEXT",
            "conversation_id": "TEXT",
            "step_id": "TEXT",
            "requester_id": "INTEGER",
            "requester_username": "TEXT",
            "reviewer_id": "INTEGER",
            "reviewer_username": "TEXT",
            "reviewer_role": "TEXT",
            "department_id": "INTEGER",
            "department_name": "TEXT",
            "status": "TEXT",
            "action_type": "TEXT",
            "proposed_payload_json": "TEXT",
            "modified_payload_json": "TEXT",
            "rejection_reason": "TEXT",
            "created_at": "TEXT",
            "reviewed_at": "TEXT",
            "expires_at": "TEXT"
        }

        for col_name in required_columns:
            self.assertIn(col_name, columns, f"Column '{col_name}' must exist in approval_requests.")

        # Verify indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='approval_requests'")
        index_names = [r[0] for r in cursor.fetchall()]

        expected_indexes = [
            "idx_approval_status",
            "idx_approval_requester",
            "idx_approval_reviewer",
            "idx_approval_department",
            "idx_approval_conversation",
            "idx_approval_plan"
        ]

        for idx in expected_indexes:
            self.assertIn(idx, index_names, f"Index '{idx}' must exist on approval_requests.")

        # Verify table is initialized completely empty (zero mock/seeded records)
        cursor.execute("SELECT COUNT(*) FROM approval_requests")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 0, "approval_requests must be completely empty on initialization.")

        conn.close()

    # =========================================================================
    # TEST 2: Existing Database Initialization Does Not Destroy Existing Data
    # =========================================================================
    def test_02_existing_database_backward_compatibility(self):
        """Verify that running init_db() against an existing database preserves existing users, documents, and audit logs."""
        # 1. Initialize fresh DB and populate sample user and document records
        init_db()

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, department_name, is_active)
            VALUES ('existing_operator', 'hashed_pw_xyz', 'user', 'Operations', 1)
        """)
        user_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO documents (id, filename, source_path, content_hash, owner_id, owner_username, status)
            VALUES ('doc_existing_1', 'cooling_tower.pdf', '/data/cooling_tower.pdf', 'hash_abc123', ?, 'existing_operator', 'indexed')
        """, (user_id,))
        conn.commit()
        conn.close()

        # Log an audit event
        AuditLogger.log_event(
            action="USER_PROVISIONED",
            component="test",
            status="success",
            user_id=user_id,
            username="existing_operator",
            role="user"
        )

        # 2. Re-run init_db() (simulating server restart or migration pass)
        init_db()

        # 3. Confirm all original data persists completely intact
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()

        cursor.execute("SELECT username, role, department_name FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        self.assertIsNotNone(user_row)
        self.assertEqual(user_row[0], "existing_operator")

        cursor.execute("SELECT filename, owner_username FROM documents WHERE id = 'doc_existing_1'")
        doc_row = cursor.fetchone()
        self.assertIsNotNone(doc_row)
        self.assertEqual(doc_row[0], "cooling_tower.pdf")

        cursor.execute("SELECT action FROM audit_logs WHERE username = 'existing_operator'")
        audit_row = cursor.fetchone()
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row[0], "USER_PROVISIONED")

        conn.close()

    # =========================================================================
    # TEST 3: Canonical Valid Approval States
    # =========================================================================
    def test_03_canonical_approval_states(self):
        """Verify all canonical approval states defined in ApprovalStatus enum."""
        expected_states = {
            "PENDING",
            "WAITING_FOR_HUMAN",
            "APPROVED",
            "MODIFIED",
            "REJECTED",
            "EXPIRED",
            "FAILED"
        }

        actual_states = {s.value for s in ApprovalStatus}
        self.assertEqual(expected_states, actual_states)

        # Confirm all enum states can be persisted to SQLite
        init_db()
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()

        for idx, state_val in enumerate(ApprovalStatus):
            appr_id = f"appr_test_state_{idx}"
            cursor.execute("""
                INSERT INTO approval_requests (
                    id, requester_id, requester_username, status, action_type, proposed_payload_json
                ) VALUES (?, 1, 'lead_eng', ?, 'DOCUMENT_APPROVAL', '{}')
            """, (appr_id, state_val.value))

        conn.commit()

        cursor.execute("SELECT status FROM approval_requests")
        persisted_states = {r[0] for r in cursor.fetchall()}
        self.assertEqual(expected_states, persisted_states)
        conn.close()

    # =========================================================================
    # TEST 4: Invalid Approval States Are Rejected
    # =========================================================================
    def test_04_invalid_approval_states_rejected(self):
        """Verify that non-canonical state strings are rejected by enum validation."""
        invalid_states = ["UNKNOWN", "AUTONOMOUSLY_APPROVED", "SKIPPED", "BYPASSED", "FREE_TEXT_STATE", ""]

        for bad_state in invalid_states:
            with self.assertRaises(ValueError, msg=f"State '{bad_state}' should be rejected"):
                ApprovalStatus(bad_state)

    # =========================================================================
    # TEST 5: Canonical Valid Action Types
    # =========================================================================
    def test_05_canonical_action_types(self):
        """Verify all canonical action types defined in ApprovalActionType enum."""
        expected_actions = {
            "DOCUMENT_APPROVAL",
            "SANDBOX_EXECUTION_APPROVAL",
            "CRITICAL_ACTION_APPROVAL"
        }

        actual_actions = {a.value for a in ApprovalActionType}
        self.assertEqual(expected_actions, actual_actions)

        # Confirm all action types can be persisted to SQLite
        init_db()
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()

        for idx, action_val in enumerate(ApprovalActionType):
            appr_id = f"appr_test_act_{idx}"
            cursor.execute("""
                INSERT INTO approval_requests (
                    id, requester_id, requester_username, status, action_type, proposed_payload_json
                ) VALUES (?, 1, 'lead_eng', 'WAITING_FOR_HUMAN', ?, '{}')
            """, (appr_id, action_val.value))

        conn.commit()

        cursor.execute("SELECT action_type FROM approval_requests")
        persisted_actions = {r[0] for r in cursor.fetchall()}
        self.assertEqual(expected_actions, persisted_actions)
        conn.close()

    # =========================================================================
    # TEST 6: Invalid Action Types Are Rejected
    # =========================================================================
    def test_06_invalid_action_types_rejected(self):
        """Verify that non-canonical action type strings are rejected by enum validation."""
        invalid_actions = ["ARBITRARY_ACTION", "EXECUTE_ANYTHING", "RUN_UNRESTRICTED", ""]

        for bad_act in invalid_actions:
            with self.assertRaises(ValueError, msg=f"Action type '{bad_act}' should be rejected"):
                ApprovalActionType(bad_act)

    # =========================================================================
    # TEST 7: Approval Audit Events Are Recognized by AuditLogger
    # =========================================================================
    def test_07_approval_audit_events_accepted(self):
        """Verify that all HITL approval action types are valid in VALID_ACTIONS and logged without rejection."""
        expected_audit_actions = [
            "APPROVAL_REQUESTED",
            "APPROVAL_GRANTED",
            "APPROVAL_MODIFIED",
            "APPROVAL_REJECTED",
            "APPROVAL_EXPIRED",
            "APPROVAL_FAILED"
        ]

        for act in expected_audit_actions:
            self.assertIn(act, VALID_ACTIONS, f"Action '{act}' must be defined in VALID_ACTIONS.")

        init_db()

        for idx, act in enumerate(expected_audit_actions):
            AuditLogger.log_event(
                action=act,
                component="hitl.service",
                status="success",
                user_id=100 + idx,
                username=f"engineer_{idx}",
                role="lead_engineer",
                resource=f"appr_req_{idx}",
                metadata={
                    "approval_id": f"appr_req_{idx}",
                    "approval_status": "WAITING_FOR_HUMAN" if "REQUESTED" in act else "APPROVED",
                    "action_type": "DOCUMENT_APPROVAL"
                }
            )

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT action FROM audit_logs WHERE component = 'hitl.service'")
        logged_actions = [r[0] for r in cursor.fetchall()]
        conn.close()

        self.assertEqual(logged_actions, expected_audit_actions)

    # =========================================================================
    # TEST 8: Approval Audit Events Participate in HMAC-SHA256 Chaining
    # =========================================================================
    def test_08_approval_events_participate_in_hmac_chain(self):
        """Verify that approval audit events automatically receive valid cryptographic entry_hash and previous_hash."""
        init_db()

        AuditLogger.log_event(
            action="APPROVAL_REQUESTED",
            component="hitl.service",
            status="success",
            user_id=1,
            username="operator1",
            role="user",
            resource="appr_001",
            metadata={"approval_id": "appr_001", "approval_status": "WAITING_FOR_HUMAN"}
        )

        AuditLogger.log_event(
            action="APPROVAL_GRANTED",
            component="hitl.service",
            status="success",
            user_id=2,
            username="lead_reviewer",
            role="lead_engineer",
            resource="appr_001",
            metadata={"approval_id": "appr_001", "reviewer_id": 2, "approval_status": "APPROVED"}
        )

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT id, action, previous_hash, entry_hash FROM audit_logs ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()

        self.assertEqual(len(rows), 2)
        row1, row2 = rows[0], rows[1]

        self.assertEqual(row1[2], "GENESIS_ROOT_HASH")
        self.assertIsNotNone(row1[3])
        self.assertEqual(len(row1[3]), 64, "entry_hash must be a 64-char SHA256 hex string.")

        self.assertEqual(row2[2], row1[3], "Second record's previous_hash must match first record's entry_hash.")
        self.assertIsNotNone(row2[3])

    # =========================================================================
    # TEST 9: Existing Audit Chain Integrity Remains Intact After Approval Events
    # =========================================================================
    def test_09_audit_chain_integrity_verification(self):
        """Verify that AuditLogger.verify_chain_integrity() confirms INTACT status across mixed events."""
        init_db()

        # Log typical system actions
        AuditLogger.log_event(action="AUTH_LOGIN", component="auth", status="success", user_id=1, username="admin", role="admin")
        AuditLogger.log_event(action="DOCUMENT_UPLOADED", component="rag", status="success", user_id=1, username="admin", role="admin", metadata={"filename": "inspection.pdf"})
        AuditLogger.log_event(action="PLAN_CREATED", component="planner", status="success", user_id=1, username="admin", role="admin", metadata={"plan_id": "plan_100"})

        # Log HITL approval events
        AuditLogger.log_event(action="APPROVAL_REQUESTED", component="hitl", status="success", user_id=1, username="admin", role="admin", metadata={"approval_id": "appr_100", "approval_status": "WAITING_FOR_HUMAN"})
        AuditLogger.log_event(action="APPROVAL_MODIFIED", component="hitl", status="success", user_id=2, username="reviewer1", role="lead_engineer", metadata={"approval_id": "appr_100", "approval_status": "MODIFIED"})
        AuditLogger.log_event(action="APPROVAL_GRANTED", component="hitl", status="success", user_id=2, username="reviewer1", role="lead_engineer", metadata={"approval_id": "appr_100", "approval_status": "APPROVED"})
        AuditLogger.log_event(action="DOCUMENT_GENERATED", component="docgen", status="success", user_id=1, username="admin", role="admin", metadata={"filename": "approval_note.docx"})

        res = AuditLogger.verify_chain_integrity()
        self.assertEqual(res["status"], "INTACT", f"Audit chain must be INTACT. Result: {res}")
        self.assertEqual(res["total_records"], 7)
        self.assertIsNone(res["tampered_record_id"])

    # =========================================================================
    # TEST 10: Forbidden Confidential Metadata Is Sanitized & Rejected
    # =========================================================================
    def test_10_confidential_metadata_protection(self):
        """Verify that passwords, tokens, API keys, and private keys are never stored in audit metadata."""
        init_db()

        AuditLogger.log_event(
            action="APPROVAL_REJECTED",
            component="hitl.service",
            status="success",
            user_id=2,
            username="security_lead",
            role="admin",
            resource="appr_sec_001",
            metadata={
                "approval_id": "appr_sec_001",
                "approval_status": "REJECTED",
                "rejection_reason": "Parameters exceed safe pressure boundary limits.",
                # Malicious / confidential injections:
                "password": "secret_password_123",
                "access_token": "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "api_key": "sk-1234567890abcdef",
                "private_key": "-----BEGIN RSA PRIVATE KEY-----"
            }
        )

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT metadata_json FROM audit_logs WHERE resource = 'appr_sec_001'")
        raw_meta = cursor.fetchone()[0]
        conn.close()

        self.assertIsNotNone(raw_meta)
        meta_dict = json.loads(raw_meta)

        # Allowed safe keys must exist
        self.assertEqual(meta_dict.get("approval_id"), "appr_sec_001")
        self.assertEqual(meta_dict.get("approval_status"), "REJECTED")
        self.assertEqual(meta_dict.get("rejection_reason"), "Parameters exceed safe pressure boundary limits.")

        # Confidential forbidden keys must be completely stripped
        self.assertNotIn("password", meta_dict)
        self.assertNotIn("access_token", meta_dict)
        self.assertNotIn("api_key", meta_dict)
        self.assertNotIn("private_key", meta_dict)

    # =========================================================================
    # TEST 11: Approval Records Can Remain WAITING_FOR_HUMAN Without reviewed_at
    # =========================================================================
    def test_11_pending_approval_nullable_review_fields(self):
        """Verify that approval records in WAITING_FOR_HUMAN state permit NULL reviewed_at, reviewer_id, and rejection_reason."""
        init_db()

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO approval_requests (
                id, plan_id, conversation_id, step_id,
                requester_id, requester_username,
                department_id, department_name,
                status, action_type,
                proposed_payload_json,
                modified_payload_json,
                rejection_reason,
                reviewed_at, expires_at
            ) VALUES (
                'appr_pending_001', 'plan_xyz', 'conv_abc', 'step_4',
                1, 'operator_alpha',
                3, 'Engineering',
                'WAITING_FOR_HUMAN', 'DOCUMENT_APPROVAL',
                '{"title": "Cooling Tower Approval Note", "efficiency": 64.14}',
                NULL, NULL, NULL, NULL
            )
        """)
        conn.commit()

        cursor.execute("SELECT status, reviewer_id, reviewed_at, modified_payload_json, rejection_reason FROM approval_requests WHERE id = 'appr_pending_001'")
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row[0], "WAITING_FOR_HUMAN")
        self.assertIsNone(row[1], "reviewer_id must be None before review.")
        self.assertIsNone(row[2], "reviewed_at must be None before review.")
        self.assertIsNone(row[3], "modified_payload_json must be None when unmodified.")
        self.assertIsNone(row[4], "rejection_reason must be None when not rejected.")

    # =========================================================================
    # TEST 12: Reviewed Records Can Contain Full Reviewer Details and Edits
    # =========================================================================
    def test_12_reviewed_approval_record_persistence(self):
        """Verify that reviewed records properly store reviewer metadata, timestamps, and modified payloads."""
        init_db()

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()

        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO approval_requests (
                id, plan_id, conversation_id, step_id,
                requester_id, requester_username,
                reviewer_id, reviewer_username, reviewer_role,
                department_id, department_name,
                status, action_type,
                proposed_payload_json,
                modified_payload_json,
                rejection_reason,
                created_at, reviewed_at, expires_at
            ) VALUES (
                'appr_reviewed_002', 'plan_xyz', 'conv_abc', 'step_4',
                1, 'operator_alpha',
                2, 'lead_engineer_bob', 'lead_engineer',
                3, 'Engineering',
                'MODIFIED', 'DOCUMENT_APPROVAL',
                '{"title": "Initial Draft"}',
                '{"title": "Approved Revised Note", "condition": "60-day fill maintenance required"}',
                NULL,
                ?, ?, ?
            )
        """, (now_str, now_str, now_str))
        conn.commit()

        cursor.execute("SELECT status, reviewer_username, reviewer_role, modified_payload_json, reviewed_at FROM approval_requests WHERE id = 'appr_reviewed_002'")
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row[0], "MODIFIED")
        self.assertEqual(row[1], "lead_engineer_bob")
        self.assertEqual(row[2], "lead_engineer")
        self.assertIn("60-day fill maintenance required", row[3])
        self.assertEqual(row[4], now_str)


if __name__ == "__main__":
    unittest.main()
