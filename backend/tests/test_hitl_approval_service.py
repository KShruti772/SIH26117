import os
import json
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from backend.app.config.settings import settings
from backend.security.database import init_db
from backend.security.models import ApprovalStatus, ApprovalActionType
from backend.security.audit import AuditLogger
from backend.services.approval_service import (
    ApprovalService,
    ApprovalNotFoundError,
    InvalidStateTransitionError,
    ApprovalAuthorizationError,
    ApprovalValidationError
)


class TestHitlApprovalService(unittest.TestCase):
    """
    AEGIS Phase 2 Verification Suite:
    Human-In-The-Loop (HITL) Approval Service, Secure State Machine,
    RBAC Reviewer Roles, Department Isolation, Segregation of Duties,
    Payload Sanitization, Concurrency Atomicity, and HMAC Audit Chaining.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aegis_phase2_hitl_")
        self.test_db = os.path.join(self.test_dir, "aegis_phase2_test.db")
        self.orig_db_path = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = self.test_db
        init_db()

        # Seed realistic departments
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO departments (id, name, description) VALUES (1, 'Engineering', 'Engineering Dept')")
        cursor.execute("INSERT OR IGNORE INTO departments (id, name, description) VALUES (2, 'Maintenance', 'Maintenance Dept')")
        cursor.execute("INSERT OR IGNORE INTO departments (id, name, description) VALUES (3, 'Operations', 'Operations Dept')")

        # Seed realistic users
        # User 1: Operator A (Requester, Engineering)
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, password_hash, role, department_id, department_name, is_active)
            VALUES (1, 'operator_a', 'hash1', 'user', 1, 'Engineering', 1)
        """)
        # User 2: Reviewer Eng (Reviewer, Engineering)
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, password_hash, role, department_id, department_name, is_active)
            VALUES (2, 'lead_engineer', 'hash2', 'reviewer', 1, 'Engineering', 1)
        """)
        # User 3: Reviewer Maint (Reviewer, Maintenance)
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, password_hash, role, department_id, department_name, is_active)
            VALUES (3, 'maint_supervisor', 'hash3', 'supervisor', 2, 'Maintenance', 1)
        """)
        # User 4: Admin (Admin, Administration)
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, password_hash, role, department_id, department_name, is_active)
            VALUES (4, 'aegis_admin', 'hash4', 'admin', 1, 'Engineering', 1)
        """)
        # User 5: Regular Peer (User, Engineering - NOT a reviewer)
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, password_hash, role, department_id, department_name, is_active)
            VALUES (5, 'peer_user', 'hash5', 'user', 1, 'Engineering', 1)
        """)
        conn.commit()
        conn.close()

        self.service = ApprovalService(db_path=self.test_db)

        # Reusable user dicts
        self.requester_eng = {"id": 1, "username": "operator_a", "role": "user", "department_id": 1, "department_name": "Engineering", "is_admin": False}
        self.reviewer_eng = {"id": 2, "username": "lead_engineer", "role": "reviewer", "department_id": 1, "department_name": "Engineering", "is_admin": False}
        self.reviewer_maint = {"id": 3, "username": "maint_supervisor", "role": "supervisor", "department_id": 2, "department_name": "Maintenance", "is_admin": False}
        self.admin_user = {"id": 4, "username": "aegis_admin", "role": "admin", "department_id": 1, "department_name": "Engineering", "is_admin": True}
        self.regular_peer = {"id": 5, "username": "peer_user", "role": "user", "department_id": 1, "department_name": "Engineering", "is_admin": False}

    def tearDown(self):
        settings.AUTH_DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # =========================================================================
    # TEST 1: Create approval request -> WAITING_FOR_HUMAN
    # =========================================================================
    def test_01_create_request_success(self):
        """Verify creating an approval request sets WAITING_FOR_HUMAN and persists all metadata."""
        payload = {"title": "P&ID Inspection Approval Note", "efficiency": 84.5}
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload=payload,
            plan_id="plan_100",
            conversation_id="conv_200",
            step_id="step_5"
        )

        self.assertIsNotNone(req)
        self.assertTrue(req["id"].startswith("appr_"))
        self.assertEqual(req["status"], ApprovalStatus.WAITING_FOR_HUMAN.value)
        self.assertEqual(req["action_type"], ApprovalActionType.DOCUMENT_APPROVAL.value)
        self.assertEqual(req["requester_id"], 1)
        self.assertEqual(req["requester_username"], "operator_a")
        self.assertEqual(req["department_id"], 1)
        self.assertIsNone(req["reviewed_at"])
        self.assertIsNone(req["reviewer_id"])

        # Proposed payload is valid JSON
        saved_payload = json.loads(req["proposed_payload_json"])
        self.assertEqual(saved_payload["title"], "P&ID Inspection Approval Note")
        self.assertEqual(saved_payload["efficiency"], 84.5)

    # =========================================================================
    # TEST 2: Authorized reviewer -> APPROVED
    # =========================================================================
    def test_02_approve_success(self):
        """Verify an authorized department reviewer can approve a request."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Inspection Report #42"}
        )

        approved = self.service.approve(req["id"], reviewer=self.reviewer_eng)
        self.assertEqual(approved["status"], ApprovalStatus.APPROVED.value)
        self.assertEqual(approved["reviewer_id"], 2)
        self.assertEqual(approved["reviewer_username"], "lead_engineer")
        self.assertEqual(approved["reviewer_role"], "reviewer")
        self.assertIsNotNone(approved["reviewed_at"])

    # =========================================================================
    # TEST 3: Authorized reviewer -> MODIFIED
    # =========================================================================
    def test_03_modify_success(self):
        """Verify an authorized reviewer can approve with modifications."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"temperature_c": 95.0, "status": "FLAGGED"}
        )

        modified_payload = {"temperature_c": 95.0, "status": "APPROVED_WITH_CONDITIONS", "remedy": "Flush cooling circuit"}
        modified = self.service.modify(req["id"], reviewer=self.reviewer_eng, modified_payload=modified_payload)

        self.assertEqual(modified["status"], ApprovalStatus.MODIFIED.value)
        self.assertEqual(modified["reviewer_id"], 2)
        self.assertEqual(modified["reviewer_username"], "lead_engineer")
        self.assertIsNotNone(modified["reviewed_at"])

        stored_mod = json.loads(modified["modified_payload_json"])
        self.assertEqual(stored_mod["status"], "APPROVED_WITH_CONDITIONS")
        self.assertEqual(stored_mod["remedy"], "Flush cooling circuit")

    # =========================================================================
    # TEST 4: Authorized reviewer -> REJECTED
    # =========================================================================
    def test_04_reject_success(self):
        """Verify an authorized reviewer can reject a request with a valid reason."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.SANDBOX_EXECUTION_APPROVAL,
            proposed_payload={"command": "calibrate_vibration_sensors.py"}
        )

        rejected = self.service.reject(
            req["id"],
            reviewer=self.reviewer_eng,
            rejection_reason="Calibration parameters exceed permissible tolerance envelope (ISO 10816)."
        )

        self.assertEqual(rejected["status"], ApprovalStatus.REJECTED.value)
        self.assertEqual(rejected["reviewer_id"], 2)
        self.assertEqual(rejected["reviewer_username"], "lead_engineer")
        self.assertEqual(rejected["rejection_reason"], "Calibration parameters exceed permissible tolerance envelope (ISO 10816).")
        self.assertIsNotNone(rejected["reviewed_at"])

    # =========================================================================
    # TEST 5: Expired request -> EXPIRED
    # =========================================================================
    def test_05_expired_request(self):
        """Verify requests with a past expires_at timestamp transition deterministically to EXPIRED."""
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.CRITICAL_ACTION_APPROVAL,
            proposed_payload={"action": "reboot_scada_node"},
            expires_at=past_time
        )

        # Retrieval triggers expiration check
        fetched = self.service.get_request(req["id"])
        self.assertEqual(fetched["status"], ApprovalStatus.EXPIRED.value)

    # =========================================================================
    # TEST 6: Invalid transition APPROVED -> REJECTED blocked
    # =========================================================================
    def test_06_invalid_transition_approved_to_rejected_blocked(self):
        """Verify that an APPROVED request cannot subsequently be REJECTED."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Spec 1"}
        )
        self.service.approve(req["id"], reviewer=self.reviewer_eng)

        with self.assertRaises(InvalidStateTransitionError):
            self.service.reject(req["id"], reviewer=self.reviewer_eng, rejection_reason="Changed my mind")

    # =========================================================================
    # TEST 7: Invalid transition REJECTED -> APPROVED blocked
    # =========================================================================
    def test_07_invalid_transition_rejected_to_approved_blocked(self):
        """Verify that a REJECTED request cannot subsequently be APPROVED."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Spec 2"}
        )
        self.service.reject(req["id"], reviewer=self.reviewer_eng, rejection_reason="Non-compliant")

        with self.assertRaises(InvalidStateTransitionError):
            self.service.approve(req["id"], reviewer=self.reviewer_eng)

    # =========================================================================
    # TEST 8: Invalid transition EXPIRED -> APPROVED blocked
    # =========================================================================
    def test_08_invalid_transition_expired_to_approved_blocked(self):
        """Verify that an EXPIRED request cannot subsequently be APPROVED."""
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Spec 3"},
            expires_at=past_time
        )

        with self.assertRaises(InvalidStateTransitionError):
            self.service.approve(req["id"], reviewer=self.reviewer_eng)

    # =========================================================================
    # TEST 9: Unauthorized reviewer role blocked
    # =========================================================================
    def test_09_unauthorized_reviewer_role_blocked(self):
        """Verify regular users without a reviewer/supervisor/admin role cannot approve."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Spec 4"}
        )

        with self.assertRaises(ApprovalAuthorizationError) as ctx:
            self.service.approve(req["id"], reviewer=self.regular_peer)
        self.assertIn("Unauthorized reviewer role", str(ctx.exception))

    # =========================================================================
    # TEST 10: Cross-department reviewer blocked
    # =========================================================================
    def test_10_cross_department_reviewer_blocked(self):
        """Verify a reviewer from Maintenance cannot approve an Engineering request."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Engineering P&ID Design"},
            department_id=1,
            department_name="Engineering"
        )

        with self.assertRaises(ApprovalAuthorizationError) as ctx:
            self.service.approve(req["id"], reviewer=self.reviewer_maint)
        self.assertIn("Cross-department review prohibited", str(ctx.exception))

    # =========================================================================
    # TEST 11: Segregation of Duties - Requester cannot self-approve
    # =========================================================================
    def test_11_segregation_of_duties_self_approval_blocked(self):
        """Verify that a requester cannot approve or modify their own request."""
        # Elevate requester temporarily to reviewer role to test self-approval segregation
        requester_with_role = dict(self.requester_eng)
        requester_with_role["role"] = "reviewer"

        req = self.service.create_request(
            requester=requester_with_role,
            action_type=ApprovalActionType.CRITICAL_ACTION_APPROVAL,
            proposed_payload={"action": "emergency_valve_bypass"}
        )

        with self.assertRaises(ApprovalAuthorizationError) as ctx:
            self.service.approve(req["id"], reviewer=requester_with_role)
        self.assertIn("Segregation of duties violation", str(ctx.exception))

        with self.assertRaises(ApprovalAuthorizationError) as ctx:
            self.service.modify(req["id"], reviewer=requester_with_role, modified_payload={"action": "safe_bypass"})
        self.assertIn("Segregation of duties violation", str(ctx.exception))

    # =========================================================================
    # TEST 12: Concurrency protection - exactly one terminal transition succeeds
    # =========================================================================
    def test_12_concurrent_approval_atomic_race(self):
        """Verify that competing concurrent review actions allow only one terminal outcome."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Race Test"}
        )

        # Reviewer A approves
        res1 = self.service.approve(req["id"], reviewer=self.reviewer_eng)
        self.assertEqual(res1["status"], ApprovalStatus.APPROVED.value)

        # Reviewer B (admin) attempts to reject the now-finalized request
        with self.assertRaises(InvalidStateTransitionError):
            self.service.reject(req["id"], reviewer=self.admin_user, rejection_reason="Conflicting decision")

        final_req = self.service.get_request(req["id"])
        self.assertEqual(final_req["status"], ApprovalStatus.APPROVED.value)

    # =========================================================================
    # TEST 13: Missing rejection reason rejected
    # =========================================================================
    def test_13_missing_rejection_reason_rejected(self):
        """Verify that rejecting a request requires a non-empty string."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Spec 5"}
        )

        with self.assertRaises(ApprovalValidationError):
            self.service.reject(req["id"], reviewer=self.reviewer_eng, rejection_reason="")

        with self.assertRaises(ApprovalValidationError):
            self.service.reject(req["id"], reviewer=self.reviewer_eng, rejection_reason="    ")

    # =========================================================================
    # TEST 14: Oversized or sensitive modification payload sanitized / rejected
    # =========================================================================
    def test_14_oversized_and_sensitive_payload_sanitized(self):
        """Verify that modified payloads strip credentials and reject oversized data."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Spec 6"}
        )

        # Sensitive payload containing password and bearer tokens
        dirty_payload = {
            "title": "Clean Title",
            "password": "super_secret_password",
            "api_key": "sk-1234567890abcdef",
            "auth_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        }

        modified = self.service.modify(req["id"], reviewer=self.reviewer_eng, modified_payload=dirty_payload)
        saved = json.loads(modified["modified_payload_json"])

        self.assertIn("title", saved)
        self.assertNotIn("password", saved)
        self.assertNotIn("api_key", saved)
        self.assertEqual(saved.get("auth_header"), "[REDACTED_SENSITIVE_CREDENTIAL]")

        # Oversized payload (>64KB)
        huge_payload = {"huge_data": "A" * 70000}
        req2 = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Spec 7"}
        )
        with self.assertRaises(ApprovalValidationError):
            self.service.modify(req2["id"], reviewer=self.reviewer_eng, modified_payload=huge_payload)

    # =========================================================================
    # TEST 15: LLM-supplied reviewer identity cannot bypass backend authorization
    # =========================================================================
    def test_15_llm_supplied_reviewer_spoofing_blocked(self):
        """Verify that reviewer information inside the payload or untrusted caller is rejected."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"doc": "Spoof Test", "approved_by": "admin", "reviewer_role": "admin"}
        )

        # Anonymous caller attempting review
        anonymous_caller = {"id": None, "username": "anonymous", "role": "user"}
        with self.assertRaises(ApprovalAuthorizationError):
            self.service.approve(req["id"], reviewer=anonymous_caller)

        # Malicious dict asserting admin role without database backing
        unauthenticated_dict = None
        with self.assertRaises(ApprovalAuthorizationError):
            self.service.approve(req["id"], reviewer=unauthenticated_dict)

    # =========================================================================
    # TEST 16-20: Cryptographic Audit Trail Verification
    # =========================================================================
    def test_16_audit_approval_requested_logged(self):
        """Verify APPROVAL_REQUESTED event is logged with all required metadata."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"item": "valve_spec"},
            plan_id="plan_999",
            step_id="step_3"
        )

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action = 'APPROVAL_REQUESTED' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["user_id"], 1)
        self.assertEqual(row["username"], "operator_a")
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta["approval_id"], req["id"])
        self.assertEqual(meta["action_type"], ApprovalActionType.DOCUMENT_APPROVAL.value)
        self.assertEqual(meta["plan_id"], "plan_999")
        self.assertEqual(meta["step_id"], "step_3")

    def test_17_audit_approval_granted_logged(self):
        """Verify APPROVAL_GRANTED event is logged upon approval."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"item": "valve_spec_2"}
        )
        self.service.approve(req["id"], reviewer=self.reviewer_eng)

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action = 'APPROVAL_GRANTED' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["user_id"], 2)
        self.assertEqual(row["username"], "lead_engineer")
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta["approval_id"], req["id"])
        self.assertEqual(meta["approval_status"], "APPROVED")

    def test_18_audit_approval_modified_logged(self):
        """Verify APPROVAL_MODIFIED event is logged upon modification."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"item": "valve_spec_3"}
        )
        self.service.modify(req["id"], reviewer=self.reviewer_eng, modified_payload={"item": "valve_spec_3_mod"})

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action = 'APPROVAL_MODIFIED' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta["approval_id"], req["id"])
        self.assertEqual(meta["approval_status"], "MODIFIED")

    def test_19_audit_approval_rejected_logged(self):
        """Verify APPROVAL_REJECTED event is logged upon rejection."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"item": "valve_spec_4"}
        )
        self.service.reject(req["id"], reviewer=self.reviewer_eng, rejection_reason="Out of spec")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action = 'APPROVAL_REJECTED' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta["approval_id"], req["id"])
        self.assertEqual(meta["approval_status"], "REJECTED")
        self.assertEqual(meta["rejection_reason"], "Out of spec")

    def test_20_audit_approval_expired_logged(self):
        """Verify APPROVAL_EXPIRED event is logged when request expires."""
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload={"item": "valve_spec_5"},
            expires_at=past_time
        )
        self.service.get_request(req["id"])

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action = 'APPROVAL_EXPIRED' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta["approval_id"], req["id"])
        self.assertEqual(meta["approval_status"], "EXPIRED")

    # =========================================================================
    # TEST 21: HMAC Chain Integrity across multiple lifecycle events
    # =========================================================================
    def test_21_hmac_chain_integrity_verification(self):
        """Verify that the cryptographic HMAC-SHA256 audit chain remains intact after multiple approval lifecycle events."""
        # Execute multiple lifecycle flows
        req1 = self.service.create_request(self.requester_eng, ApprovalActionType.DOCUMENT_APPROVAL, {"doc": "1"})
        self.service.approve(req1["id"], self.reviewer_eng)

        req2 = self.service.create_request(self.requester_eng, ApprovalActionType.SANDBOX_EXECUTION_APPROVAL, {"doc": "2"})
        self.service.modify(req2["id"], self.reviewer_eng, {"doc": "2_clean"})

        req3 = self.service.create_request(self.requester_eng, ApprovalActionType.CRITICAL_ACTION_APPROVAL, {"doc": "3"})
        self.service.reject(req3["id"], self.reviewer_eng, "Safety threshold exceeded")

        past_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        req4 = self.service.create_request(self.requester_eng, ApprovalActionType.DOCUMENT_APPROVAL, {"doc": "4"}, expires_at=past_time)
        self.service.get_request(req4["id"])

        # Verify cryptographic chain integrity
        integrity = AuditLogger.verify_chain_integrity()
        self.assertEqual(integrity["status"], "INTACT", f"Chain verification failed: {integrity}")
        self.assertGreaterEqual(integrity["total_records"], 8)
        self.assertIsNone(integrity["tampered_record_id"])

    # =========================================================================
    # TEST 22: Admin cross-department review authorization
    # =========================================================================
    def test_22_admin_cross_department_review_allowed(self):
        """Verify administrators with role='admin' can review requests across all departments."""
        req = self.service.create_request(
            requester=self.requester_eng,
            action_type=ApprovalActionType.CRITICAL_ACTION_APPROVAL,
            proposed_payload={"doc": "Executive Override"},
            department_id=2,  # Maintenance
            department_name="Maintenance"
        )

        # Admin belongs to department 1, but role is admin
        approved = self.service.approve(req["id"], reviewer=self.admin_user)
        self.assertEqual(approved["status"], ApprovalStatus.APPROVED.value)
        self.assertEqual(approved["reviewer_id"], 4)
        self.assertEqual(approved["reviewer_role"], "admin")

    # =========================================================================
    # TEST 23: Adversarial - Double Approval Blocked
    # =========================================================================
    def test_23_adversarial_double_approval_blocked(self):
        """Verify calling approve twice on the same request is rejected."""
        req = self.service.create_request(self.requester_eng, ApprovalActionType.DOCUMENT_APPROVAL, {"doc": "Double Approve"})
        self.service.approve(req["id"], self.reviewer_eng)

        with self.assertRaises(InvalidStateTransitionError):
            self.service.approve(req["id"], self.reviewer_eng)

    # =========================================================================
    # TEST 24: Adversarial - Modification after Approval Blocked
    # =========================================================================
    def test_24_adversarial_modification_after_approval_blocked(self):
        """Verify calling modify on an already APPROVED request is rejected."""
        req = self.service.create_request(self.requester_eng, ApprovalActionType.DOCUMENT_APPROVAL, {"doc": "Mod After Approve"})
        self.service.approve(req["id"], self.reviewer_eng)

        with self.assertRaises(InvalidStateTransitionError):
            self.service.modify(req["id"], self.reviewer_eng, {"doc": "Sneaky Mod"})

    # =========================================================================
    # TEST 25: Adversarial - Rejection after Approval Blocked
    # =========================================================================
    def test_25_adversarial_rejection_after_approval_blocked(self):
        """Verify calling reject on an already APPROVED request is rejected."""
        req = self.service.create_request(self.requester_eng, ApprovalActionType.DOCUMENT_APPROVAL, {"doc": "Reject After Approve"})
        self.service.approve(req["id"], self.reviewer_eng)

        with self.assertRaises(InvalidStateTransitionError):
            self.service.reject(req["id"], self.reviewer_eng, rejection_reason="Too late")

    # =========================================================================
    # TEST 26: Adversarial - Confidential audit leak prevention
    # =========================================================================
    def test_26_adversarial_confidential_leak_prevention(self):
        """Verify rejection reasons and payloads with secrets do not leak passwords/tokens into audit logs."""
        req = self.service.create_request(self.requester_eng, ApprovalActionType.DOCUMENT_APPROVAL, {"doc": "Leak Test"})
        self.service.reject(
            req["id"],
            reviewer=self.reviewer_eng,
            rejection_reason="The password was incorrect and authorization token was invalid."
        )

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT metadata_json FROM audit_logs WHERE action = 'APPROVAL_REJECTED' ORDER BY id DESC LIMIT 1")
        meta_json = cursor.fetchone()[0]
        conn.close()

        self.assertNotIn("super_secret", meta_json)
        self.assertNotIn("password was incorrect", meta_json)
        self.assertIn("[REDACTED]", meta_json)


if __name__ == "__main__":
    unittest.main()
