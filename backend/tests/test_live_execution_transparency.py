import os
import unittest
import asyncio
import json
import uuid
import re
from typing import List, Dict, Any
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from backend.app.main import app, agent_controller
from backend.agents.controller.agent import ExecutionEventType
from backend.agents.conversations import ConversationManager
from backend.security.database import get_db_path, init_db
import sqlite3
from backend.security.auth import create_access_token, hash_password
from backend.security.audit import AuditLogger


class TestLiveExecutionTransparency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                       ("admin", hash_password("AdminPass123!"), "admin", 1))
        cursor.execute("INSERT OR IGNORE INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                       ("engineer1", hash_password("EngPass123!"), "user", 1))
        cursor.execute("INSERT OR IGNORE INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                       ("operator2", hash_password("OpsPass123!"), "user", 1))
        conn.commit()
        conn.close()

        cls.client = TestClient(app)
        cls.admin_token = create_access_token(subject="admin", role="admin")
        cls.user1_token = create_access_token(subject="engineer1", role="user")
        cls.user2_token = create_access_token(subject="operator2", role="user")

    def test_agent_controller_execution_event_emission(self):
        """Test that AgentController emits structured operational events during execution."""
        emitted_events: List[Dict[str, Any]] = []

        def sync_callback(evt: Dict[str, Any]):
            emitted_events.append(evt)

        # Execute a general reasoning query
        res = asyncio.run(
            agent_controller.run(
                "Summarize key safety checks for turbine bearing temperature limits.",
                current_user={"id": 2, "username": "engineer1", "role": "engineer", "department": "Maintenance"},
                conversation_id="conv_test_events_01",
                event_callback=sync_callback
            )
        )

        self.assertTrue(res.get("success"), f"AgentController failed: {res.get('error')}")
        self.assertIn("execution_id", res)
        execution_id = res["execution_id"]
        self.assertTrue(re.match(r"^EXE-[A-F0-9]{8}$", execution_id), f"Invalid execution_id format: {execution_id}")

        self.assertGreater(len(emitted_events), 0, "No events were emitted to callback")
        event_types = [e["event_type"] for e in emitted_events]

        self.assertIn(ExecutionEventType.REQUEST_RECEIVED.value, event_types)
        self.assertIn(ExecutionEventType.PLANNING_STARTED.value, event_types)
        self.assertIn(ExecutionEventType.PLAN_CREATED.value, event_types)
        self.assertIn(ExecutionEventType.STEP_STARTED.value, event_types)
        self.assertIn(ExecutionEventType.STEP_COMPLETED.value, event_types)
        self.assertIn(ExecutionEventType.EXECUTION_COMPLETED.value, event_types)

        # Verify all events have safe structured fields
        for evt in emitted_events:
            self.assertEqual(evt["execution_id"], execution_id)
            self.assertIn("timestamp", evt)
            self.assertIn("event_type", evt)
            self.assertIn("message", evt)
            self.assertIn("metadata", evt)

    def test_zero_cot_and_secrets_leakage(self):
        """Verify that telemetry events contain zero chain-of-thought, hidden reasoning, or private secrets."""
        emitted_events: List[Dict[str, Any]] = []

        def callback(evt: Dict[str, Any]):
            emitted_events.append(evt)

        asyncio.run(
            agent_controller.run(
                "Calculate standard flow rate variance for pipeline segment A.",
                current_user={"id": 2, "username": "engineer1", "role": "engineer", "department": "Maintenance"},
                conversation_id="conv_test_leakage_01",
                event_callback=callback
            )
        )

        forbidden_patterns = [
            "chain_of_thought",
            "hidden_thought",
            "thinking_process",
            "system_prompt",
            "secret_key",
            "password",
            "Bearer ",
            "api_key"
        ]

        for evt in emitted_events:
            event_str = json.dumps(evt).lower()
            for pattern in forbidden_patterns:
                self.assertNotIn(
                    pattern.lower(),
                    event_str,
                    f"Forbidden pattern '{pattern}' detected in execution event: {evt}"
                )

    def test_chat_stream_sse_endpoint(self):
        """Test POST /chat/stream SSE streaming of live events and final result."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"

        response = self.client.post(
            "/chat/stream",
            headers=headers,
            json={"message": "What is the recommended inspection interval for hydraulic actuators?", "session_id": conv_id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))

        lines = response.text.strip().split("\n\n")
        self.assertGreater(len(lines), 0)

        events = []
        final_result = None

        for line in lines:
            line = line.strip()
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if "event" in payload:
                    events.append(payload["event"])
                if "result" in payload:
                    final_result = payload["result"]

        self.assertGreater(len(events), 0, "No events received via SSE stream")
        self.assertIsNotNone(final_result, "No final result received in SSE stream")
        self.assertTrue(final_result.get("success"))
        self.assertIn("execution_id", final_result)
        self.assertIn("execution_events", final_result)
        self.assertIn("plan", final_result)

    def test_edit_prompt_stream_sse_endpoint(self):
        """Test POST /conversations/{session_id}/messages/{message_id}/edit-stream SSE endpoint."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}

        # 1. Create a conversation
        create_res = self.client.post("/conversations", headers=headers, json={"title": "Actuator Inspection"})
        self.assertEqual(create_res.status_code, 200)
        session_id = create_res.json()["id"]

        # 2. Post initial message
        chat_res = self.client.post("/chat", headers=headers, json={"message": "Inspect valve pressure.", "session_id": session_id})
        self.assertEqual(chat_res.status_code, 200)

        # 3. Retrieve user message ID
        msgs_res = self.client.get(f"/conversations/{session_id}/messages", headers=headers)
        self.assertEqual(msgs_res.status_code, 200)
        msgs = msgs_res.json()
        user_msg = next(m for m in msgs if m["role"] == "user")
        orig_msg_id = user_msg["id"]

        # 4. Stream edited prompt
        edit_res = self.client.post(
            f"/conversations/{session_id}/messages/{orig_msg_id}/edit-stream",
            headers=headers,
            json={"message": "Inspect valve pressure and compare against safety limits."}
        )
        self.assertEqual(edit_res.status_code, 200)
        self.assertIn("text/event-stream", edit_res.headers.get("content-type", ""))

        lines = edit_res.text.strip().split("\n\n")
        events = []
        final_result = None
        for line in lines:
            line = line.strip()
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if "event" in payload:
                    events.append(payload["event"])
                if "result" in payload:
                    final_result = payload["result"]

        self.assertGreater(len(events), 0)
        self.assertIsNotNone(final_result)
        self.assertTrue(final_result.get("success"))

        # 5. Verify conversation now contains 4 messages total (original user, original assistant, edited user, edited assistant)
        updated_msgs = self.client.get(f"/conversations/{session_id}/messages", headers=headers).json()
        self.assertEqual(len(updated_msgs), 4)

    def test_cross_user_isolation_and_authorization(self):
        """Verify cross-user session execution access control."""
        # user1 creates conversation
        u1_headers = {"Authorization": f"Bearer {self.user1_token}"}
        conv = self.client.post("/conversations", headers=u1_headers, json={"title": "Private User1 Session"}).json()
        session_id = conv["id"]

        # user1 posts a message
        self.client.post("/chat", headers=u1_headers, json={"message": "Confidential plan.", "session_id": session_id})
        user1_msgs = self.client.get(f"/conversations/{session_id}/messages", headers=u1_headers).json()
        user1_prompt_id = user1_msgs[0]["id"]

        # user2 attempts to edit-stream user1's session -> must be 403 Forbidden
        u2_headers = {"Authorization": f"Bearer {self.user2_token}"}
        forbidden_res = self.client.post(
            f"/conversations/{session_id}/messages/{user1_prompt_id}/edit-stream",
            headers=u2_headers,
            json={"message": "Unauthorized edit."}
        )
        self.assertEqual(forbidden_res.status_code, 403)

    def test_audit_chain_continuity(self):
        """Verify HMAC integrity of the audit ledger after stream executions."""
        audit_verify = AuditLogger.verify_chain_integrity()
        self.assertEqual(audit_verify.get("status"), "INTACT", f"Audit chain verification failed: {audit_verify}")
        self.assertIsNone(audit_verify.get("tampered_record_id"))


if __name__ == "__main__":
    unittest.main()
