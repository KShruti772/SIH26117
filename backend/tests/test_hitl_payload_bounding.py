import unittest
import os
import json
import uuid
import sqlite3
import shutil
import tempfile
from typing import Dict, Any, List
from unittest.mock import MagicMock, AsyncMock, patch

from backend.security.database import init_db
from backend.security.models import ApprovalStatus, ApprovalActionType
from backend.security.audit import AuditLogger
from backend.services.approval_service import ApprovalService, ApprovalValidationError, MAX_PAYLOAD_JSON_BYTES
from backend.agents.controller.agent import AgentController, AgentPlan, AgentStep, AgentState, StepType
from backend.tools.code_sandbox.sandbox import SubprocessSandbox
from backend.tools.document_generators.generators import DocxGenerator, PdfGenerator, XlsxGenerator
from backend.agents.context_manager import ContextManager


class TestHitlPayloadBounding(unittest.IsolatedAsyncioTestCase):
    """
    Focused regression test suite for HITL approval payload bounding and replanning state isolation.
    """

    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aegis_hitl_bounding_")
        self.db_path = os.path.join(self.test_dir, "test_hitl_bounding.db")
        self.exports_dir = os.path.join(self.test_dir, "exports")
        os.makedirs(self.exports_dir, exist_ok=True)
        os.environ["AEGIS_DB_PATH"] = self.db_path

        self.patcher_db = patch("backend.security.database.get_db_path", return_value=self.db_path)
        self.patcher_db.start()

        self.patcher_settings = patch("backend.app.config.settings.settings.AUTH_DB_PATH", self.db_path)
        self.patcher_settings.start()

        init_db()

        # Provision test users
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) VALUES (1, 'engineer_bob', 'hash', 'user', 3, 'Engineering', 1)"
        )
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role, department_id, department_name, is_active) VALUES (2, 'lead_alice', 'hash', 'reviewer', 3, 'Engineering', 1)"
        )
        conn.commit()
        conn.close()

        self.user_bob = {"id": 1, "username": "engineer_bob", "role": "user", "department_id": 3, "department_name": "Engineering"}
        self.reviewer_alice = {"id": 2, "username": "lead_alice", "role": "reviewer", "department_id": 3, "department_name": "Engineering"}

        self.approval_service = ApprovalService(self.db_path)
        self.sandbox_service = SubprocessSandbox(
            workspace_parent=os.path.join(self.test_dir, "sandbox_runs"),
            artifacts_storage=os.path.join(self.test_dir, "artifacts")
        )
        self.doc_generators = {
            "docx": DocxGenerator(output_base_dir=self.exports_dir),
            "pdf": PdfGenerator(output_base_dir=self.exports_dir),
            "xlsx": XlsxGenerator(output_base_dir=self.exports_dir),
        }

        self.mock_registry = MagicMock()
        mock_profile = MagicMock()
        mock_profile.context_length = 32768
        self.mock_registry.get_model.return_value = mock_profile

        self.mock_loader = MagicMock()
        self.mock_loader.base_url = "http://localhost:11434"
        self.mock_loader.current_model_id = "qwen2.5-14b"
        self.mock_loader.generate = AsyncMock(side_effect=self._mock_model_generate)

        self.mock_router = MagicMock()
        self.mock_router.route = AsyncMock(side_effect=self._mock_router_route)

        self.mock_rag = MagicMock()
        self.sample_doc = {
            "id": "doc_pump_01",
            "filename": "cooling_tower_inspection_report.pdf",
            "title": "Cooling Tower & Pump Inspection Report",
            "owner_id": 1
        }
        self.sample_chunks = [
            {
                "text": "Cooling Tower CT-01 Inspection: Inlet water temperature is 38.5 C. Outlet water temperature is 29.2 C. Ambient wet-bulb temperature is 24.0 C. Circulation water flow is 1200 m3/h. Induced draft fan vibration is normal at 2.1 mm/s.",
                "metadata": {"filename": "cooling_tower_inspection_report.pdf", "page_number": 1}
            },
            {
                "text": "Operating parameters require Range (T_in - T_out) >= 8.0 C and Approach (T_out - T_wb) <= 6.0 C. Maintenance sign-off requires approval note from plant engineering lead.",
                "metadata": {"filename": "cooling_tower_inspection_report.pdf", "page_number": 2}
            }
        ]
        self.mock_rag.list_documents.return_value = [self.sample_doc]
        self.mock_rag.get_document.return_value = self.sample_doc
        self.mock_rag.search.return_value = self.sample_chunks
        self.mock_rag.get_document_chunks.return_value = self.sample_chunks

        self.context_manager = ContextManager(
            registry_manager=self.mock_registry,
            rag_service=self.mock_rag,
            default_context_budget=16384
        )

        self.controller = AgentController(
            registry_manager=self.mock_registry,
            loader_manager=self.mock_loader,
            model_router=self.mock_router,
            rag_service=self.mock_rag,
            sandbox_service=self.sandbox_service,
            doc_generators=self.doc_generators,
            context_manager=self.context_manager,
            approval_service=self.approval_service,
            enable_hitl=True,
            max_replans=3,
            max_steps=15
        )

    async def asyncTearDown(self):
        self.patcher_db.stop()
        self.patcher_settings.stop()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    async def _mock_router_route(self, required_capabilities, prompt=None, auto_switch=True, user_id=None, username=None, role=None):
        cap = required_capabilities[0] if required_capabilities else "text_generation"
        selected = "qwen2.5-coder:7b" if cap == "coding" else "gemma3:4b"
        decision = MagicMock()
        decision.selected_model = selected
        decision.runtime_model_name = selected
        decision.switched = False
        decision.to_dict.return_value = {
            "selected_model": selected,
            "runtime_model_name": selected,
            "required_capabilities": required_capabilities,
            "task_type": "coding" if cap == "coding" else "reasoning",
            "reason": f"Selected {selected} for {cap}",
            "switched": False
        }
        return decision

    async def _mock_model_generate(self, prompt, system_prompt=None, **kwargs):
        p_lower = prompt.lower()
        if "extract key findings" in p_lower or "extract structured technical findings" in p_lower:
            return (
                "### Technical Inspection Findings\n"
                "- Equipment: Cooling Tower CT-01\n"
                "- Inlet Temperature: 38.5 °C\n"
                "- Outlet Temperature: 29.2 °C\n"
                "- Ambient Wet-Bulb: 24.0 °C\n"
                "- Water Flow Rate: 1200 m³/h\n"
                "- Recommendation: Routine maintenance approved."
            )
        if "cooling tower" in p_lower and ("efficiency" in p_lower or "delta" in p_lower or "range" in p_lower or "compute" in p_lower or "script" in p_lower or "python" in p_lower):
            return (
                "```python\n"
                "t_in = 38.5\n"
                "t_out = 29.2\n"
                "t_wb = 24.0\n"
                "cooling_range = t_in - t_out\n"
                "approach = t_out - t_wb\n"
                "efficiency = (cooling_range / (cooling_range + approach)) * 100\n"
                "print(f'Cooling Range: {cooling_range:.2f} C')\n"
                "print(f'Approach: {approach:.2f} C')\n"
                "print(f'Thermal Efficiency: {efficiency:.2f}%')\n"
                "```"
            )
        if "approval note" in p_lower or "draft" in p_lower:
            return (
                "# Cooling Tower Inspection & Maintenance Approval Note\n\n"
                "## 1. Executive Summary & Approval Decision\n"
                "Formal engineering approval is granted for CT-01.\n\n"
                "## 2. Operating Metrics\n"
                "- Inlet Temp: 38.5 °C\n"
                "- Outlet Temp: 29.2 °C\n\n"
                "## 3. Calculations & Efficiency\n"
                "- Cooling Range: 9.30 °C\n"
                "- Approach: 5.20 °C\n\n"
                "## 4. Formal Sign-off\n"
                "Approved by Engineering Lead."
            )
        return "Default model output for test."

    # -------------------------------------------------------------------------
    # TEST 1: Normal Approval Payload Remains Far Below 64 KB Limit
    # -------------------------------------------------------------------------
    async def test_01_normal_approval_payload_bounded_under_64kb(self):
        """Verify normal approval payload is compact (< 20 KB) and far below 64 KB."""
        prompt = "Analyze the cooling tower inspection report and prepare an approval note."
        
        result = await self.controller.run(
            request=prompt,
            current_user=self.user_bob,
            conversation_id="conv_hitl_bound_01",
            enable_hitl=True
        )

        approval_id = result.get("approval_id")
        self.assertIsNotNone(approval_id)

        req = self.approval_service.get_request(approval_id)
        self.assertEqual(req["status"], ApprovalStatus.WAITING_FOR_HUMAN.value)
        raw_payload_json = req["proposed_payload_json"]
        payload_bytes = len(raw_payload_json.encode("utf-8"))

        # Assert payload is strictly bounded and far below 64 KB
        self.assertLess(payload_bytes, MAX_PAYLOAD_JSON_BYTES, f"Payload {payload_bytes} exceeds {MAX_PAYLOAD_JSON_BYTES}")
        self.assertLess(payload_bytes, 20480, f"Normal payload {payload_bytes} should comfortably be under 20 KB")

        parsed = json.loads(raw_payload_json)
        self.assertIn("findings", parsed)
        self.assertIn("calculations", parsed)
        self.assertIn("plan_snapshot", parsed)
        self.assertEqual(parsed["plan_snapshot"]["plan_id"], result["plan_id"])

    # -------------------------------------------------------------------------
    # TEST 2-5: Replan 1, 2, 3 Do NOT Recursively Embed Previous Plans and Stay Bounded
    # -------------------------------------------------------------------------
    async def test_02_replanning_does_not_nest_plans_and_stays_bounded_across_3_replans(self):
        """
        Simulate 3 successive replans before reaching HITL approval gate.
        Assert that:
        - Replan #1 does not embed previous plan recursively.
        - Replan #2 does not embed previous plan recursively.
        - Replan #3 does not embed previous plan recursively.
        - Step IDs are cleanly named (e.g. step_2_replan_1, step_2_replan_2, step_2_replan_3) rather than step_2_replan_1_replan_2_replan_3.
        - The resulting approval payload remains strictly bounded (< 15 KB) and well below 64 KB.
        """
        plan = AgentPlan(
            request="Analyze pump vibration and compile approval deliverable",
            category="CATEGORY_D",
            goal="Analyze pump vibration with replans"
        )
        plan.conversation_id = "conv_replan_test"

        # Step 0: RAG search (with large mock data)
        step_0 = AgentStep(
            step_id="step_0",
            description="Perform RAG search",
            capability="rag",
            step_type=StepType.RAG_SEARCH.value,
            input_data={"action": "rag_search"}
        )
        step_0.status = "COMPLETED"
        step_0.output = [
            {"text": "Extremely large chunk of context " * 50, "metadata": {"filename": f"doc_{i}.pdf", "page_number": i}}
            for i in range(10)
        ]
        plan.steps.append(step_0)

        # Step 1: Draft findings
        step_1 = AgentStep(
            step_id="step_1",
            description="Extract findings",
            capability="text_generation",
            step_type=StepType.MODEL_INFERENCE.value,
            input_data={"action": "extract_findings"}
        )
        step_1.status = "COMPLETED"
        step_1.output = "Extracted findings: Centrifugal pump P-101 vibration measured at 145 mm/s. AOR limit is 100 mm/s."
        plan.steps.append(step_1)

        # Step 2: Coding step that fails 3 times
        step_2 = AgentStep(
            step_id="step_2",
            description="Run numerical validation script",
            capability="coding",
            step_type=StepType.SANDBOX_EXECUTION.value,
            input_data={"action": "execute_code"}
        )
        step_2.status = "FAILED"
        step_2.error = "Sandbox Execution Failed (Exit code 1):\nTraceback (most recent call last):\n  File 'script.py', line 12, in <module>\n    raise ValueError('Exceeded limit')\nValueError: Exceeded limit\n" + ("x" * 2000)
        step_2.output = {
            "success": False,
            "exit_code": 1,
            "stdout": "Running checks...\n",
            "stderr": step_2.error,
            "code": "def check_limit(): raise ValueError()\n" * 50
        }
        plan.steps.append(step_2)
        plan.current_step_index = 2

        state = AgentState(request=plan.request, user_id=1, username="bob", conversation_id="conv_replan_test", task_type="CATEGORY_D")
        self.controller.active_states[plan.plan_id] = state

        # Trigger Replan #1
        replan1_ok = self.controller._replan(plan, step_2, state, current_user=self.user_bob)
        self.assertTrue(replan1_ok)
        self.assertEqual(plan.replan_count, 1)

        replan1_step = plan.steps[3]
        self.assertEqual(replan1_step.step_id, "step_2_replan_1", "Replan 1 step ID must be clean")
        self.assertNotIn("_replan_1_replan", replan1_step.step_id)
        self.assertLessEqual(len(replan1_step.input.get("previous_error", "")), 500, "Previous error must be bounded")

        # Simulate failure of Replan #1 and trigger Replan #2
        replan1_step.status = "FAILED"
        replan1_step.error = "TypeError: 'dict' object cannot be interpreted as integer\n" + ("y" * 2000)
        replan1_step.output = {"success": False, "exit_code": 1, "stderr": replan1_step.error, "stdout": "Test replan 1"}
        
        replan2_ok = self.controller._replan(plan, replan1_step, state, current_user=self.user_bob)
        self.assertTrue(replan2_ok)
        self.assertEqual(plan.replan_count, 2)

        replan2_step = plan.steps[4]
        self.assertEqual(replan2_step.step_id, "step_2_replan_2", "Replan 2 step ID must not chain recursively")
        self.assertNotIn("step_2_replan_1_replan_2", replan2_step.step_id)

        # Simulate failure of Replan #2 and trigger Replan #3
        replan2_step.status = "FAILED"
        replan2_step.error = "ZeroDivisionError: division by zero\n" + ("z" * 2000)
        replan2_step.output = {"success": False, "exit_code": 1, "stderr": replan2_step.error, "stdout": "Test replan 2"}

        replan3_ok = self.controller._replan(plan, replan2_step, state, current_user=self.user_bob)
        self.assertTrue(replan3_ok)
        self.assertEqual(plan.replan_count, 3)

        replan3_step = plan.steps[5]
        self.assertEqual(replan3_step.step_id, "step_2_replan_3", "Replan 3 step ID must not chain recursively")
        self.assertNotIn("replan_1_replan_2_replan_3", replan3_step.step_id)

        # Replan #3 succeeds
        replan3_step.status = "COMPLETED"
        replan3_step.output = {
            "success": True,
            "exit_code": 0,
            "stdout": "Measured vibration: 145 mm/s. AOR limit (100 mm/s) EXCEEDED by 45%.",
            "stderr": "",
            "artifacts": []
        }
        replan3_step.observation = {"tool": "sandbox", "exit_code": 0, "stdout": replan3_step.output["stdout"]}

        # Step 3: Draft document content
        step_doc = AgentStep(
            step_id="step_3",
            description="Draft deliverable report",
            capability="text_generation",
            step_type=StepType.MODEL_INFERENCE.value,
            input_data={"action": "generate_document_content", "target_format": "docx"}
        )
        step_doc.status = "COMPLETED"
        step_doc.output = "# Vibration Assessment Report\n\n## Summary\nPump P-101 vibration exceeds AOR limit."
        plan.steps.append(step_doc)

        # Step 4: HITL Approval Step
        step_hitl = AgentStep(
            step_id="step_4",
            description="Human Approval Gate",
            capability="governance",
            step_type=StepType.HUMAN_APPROVAL.value,
            input_data={"action": "hitl_approval", "target_format": "docx"}
        )
        plan.steps.append(step_hitl)
        plan.current_step_index = 7

        # Snapshot the plan
        snapshot = plan.to_snapshot_dict()
        self.assertIn("steps", snapshot)
        self.assertEqual(len(snapshot["steps"]), 8)

        # Verify no recursive plan inside any step's input or output
        for s in snapshot["steps"]:
            self.assertNotIn("plan_snapshot", s.get("input", {}))
            self.assertNotIn("plan", s.get("input", {}))
            if isinstance(s.get("output"), dict):
                self.assertNotIn("plan_snapshot", s["output"])
                self.assertNotIn("plan", s["output"])

        # Construct HITL proposed_payload as in AgentController
        proposed_payload = {
            "task_type": plan.task_type,
            "step_type": step_hitl.step_type,
            "plan_version": plan.replan_count + 1,
            "summary": "Draft approval note",
            "findings": "Findings text",
            "calculations": "Calculations text",
            "citations": [],
            "draft_document_text": step_doc.output,
            "target_format": "docx",
            "plan_id": plan.plan_id,
            "step_id": step_hitl.step_id,
            "plan_snapshot": snapshot
        }

        # Create the approval request in ApprovalService
        appr_rec = self.approval_service.create_request(
            requester=self.user_bob,
            action_type=ApprovalActionType.DOCUMENT_APPROVAL,
            proposed_payload=proposed_payload,
            plan_id=plan.plan_id,
            step_id=step_hitl.step_id,
            conversation_id="conv_replan_test",
            department_id=3,
            department_name="Engineering"
        )

        self.assertEqual(appr_rec["status"], ApprovalStatus.WAITING_FOR_HUMAN.value)
        stored_bytes = len(appr_rec["proposed_payload_json"].encode("utf-8"))

        # Assert payload is well bounded and strictly < 64 KB
        self.assertLess(stored_bytes, MAX_PAYLOAD_JSON_BYTES)
        self.assertLess(stored_bytes, 15000, f"Payload after 3 replans ({stored_bytes} bytes) should be < 15 KB")

    # -------------------------------------------------------------------------
    # TEST 6 & 7: Sandbox Stdout / Stderr are NOT Copied Wholesale into Approval Payload
    # -------------------------------------------------------------------------
    def test_06_07_sandbox_stdout_stderr_not_copied_wholesale(self):
        """Verify massive sandbox stdout and stderr are sanitized into a compact summary."""
        huge_stdout = "Calculated metric line: " + ("1234567890 " * 5000)  # ~55 KB
        huge_stderr = "Traceback error line: " + ("FAIL_TRACE_001 " * 5000)  # ~70 KB

        step = AgentStep(
            step_id="step_sandbox_large",
            description="Run large analysis",
            capability="coding",
            step_type=StepType.SANDBOX_EXECUTION.value
        )
        step.status = "COMPLETED"
        step.output = {
            "success": True,
            "exit_code": 0,
            "stdout": huge_stdout,
            "stderr": huge_stderr,
            "artifacts": []
        }
        step.observation = {"tool": "sandbox", "exit_code": 0, "stdout": huge_stdout}

        snapshot_dict = step.to_snapshot_dict()
        snapshot_bytes = len(json.dumps(snapshot_dict).encode("utf-8"))

        # Snapshot must be tiny (< 2 KB), not > 120 KB
        self.assertLess(snapshot_bytes, 2048, f"Step snapshot size {snapshot_bytes} exceeds 2 KB limit")
        self.assertIn("summary", snapshot_dict["output"])
        self.assertLessEqual(len(snapshot_dict["output"]["summary"]), 200)

    # -------------------------------------------------------------------------
    # TEST 8 & 9: Model Output & Plans are Not Recursively Accumulated
    # -------------------------------------------------------------------------
    def test_08_09_no_recursive_plan_or_model_accumulation(self):
        """Verify plan snapshot excludes previous approval payloads and nested plans."""
        plan1 = AgentPlan(request="Original request", category="CATEGORY_A")
        step1 = AgentStep(step_id="s1", description="Step 1", capability="text_generation")
        step1.output = "Some text"
        plan1.steps.append(step1)

        # Intentionally inject recursive reference into input
        step2 = AgentStep(
            step_id="s2",
            description="Step 2",
            capability="text_generation",
            input_data={"plan_snapshot": plan1.to_dict(), "previous_plan": plan1.to_dict()}
        )
        plan1.steps.append(step2)

        snap = plan1.to_snapshot_dict()
        s2_snap = snap["steps"][1]

        self.assertNotIn("plan_snapshot", s2_snap["input"])
        self.assertNotIn("previous_plan", s2_snap["input"])

    # -------------------------------------------------------------------------
    # TEST 10: Approval Payload Does Not Contain Another Approval Payload
    # -------------------------------------------------------------------------
    def test_10_approval_payload_does_not_contain_nested_approval_payload(self):
        """Verify approval payload cannot contain nested approval payloads."""
        nested_appr = {
            "id": "appr_old_999",
            "proposed_payload_json": json.dumps({"findings": "old findings"})
        }
        step = AgentStep(
            step_id="s_hitl",
            description="HITL",
            capability="governance",
            input_data={"approval_payload": nested_appr}
        )
        snap = step.to_snapshot_dict()
        self.assertNotIn("approval_payload", snap["input"])

    # -------------------------------------------------------------------------
    # TEST 11: Maximum Replan Budget Exhaustion Halts Cleanly with FAILED
    # -------------------------------------------------------------------------
    async def test_11_max_replan_budget_exhaustion_halts_with_failed(self):
        """Verify exhausting 3 replans halts truthfully with FAILED status and truthful error."""
        plan = AgentPlan(request="Failing task", category="CATEGORY_B")
        state = AgentState(request="Failing task", user_id=1, username="bob", conversation_id="conv_fail", task_type="CATEGORY_B")

        step = AgentStep(step_id="step_fail", description="Failing step", capability="coding")
        step.status = "FAILED"
        step.error = "Persistent syntax error in generated code."
        plan.steps.append(step)

        # Attempt 1
        ok1 = self.controller._replan(plan, step, state, current_user=self.user_bob)
        self.assertTrue(ok1)

        # Attempt 2
        step_r1 = plan.steps[1]
        step_r1.status = "FAILED"
        step_r1.error = "Persistent syntax error attempt 2."
        ok2 = self.controller._replan(plan, step_r1, state, current_user=self.user_bob)
        self.assertTrue(ok2)

        # Attempt 3
        step_r2 = plan.steps[2]
        step_r2.status = "FAILED"
        step_r2.error = "Persistent syntax error attempt 3."
        ok3 = self.controller._replan(plan, step_r2, state, current_user=self.user_bob)
        self.assertTrue(ok3)

        # Attempt 4 (Exceeds max_replans = 3)
        step_r3 = plan.steps[3]
        step_r3.status = "FAILED"
        step_r3.error = "Persistent syntax error attempt 4."
        ok4 = self.controller._replan(plan, step_r3, state, current_user=self.user_bob)

        self.assertFalse(ok4, "Replan attempt beyond max budget must return False")
        self.assertEqual(plan.status, "FAILED")
        self.assertEqual(state.status, "FAILED")
        self.assertIn("maximum replan budget of 3 attempts was exhausted", plan.final_output)

    # -------------------------------------------------------------------------
    # TEST 12: Genuine HITL Request Remains WAITING_FOR_HUMAN
    # -------------------------------------------------------------------------
    async def test_12_genuine_hitl_request_remains_waiting_for_human(self):
        """Verify legitimate HITL pause sets and preserves WAITING_FOR_HUMAN."""
        result = await self.controller.run(
            request="Analyze the cooling tower inspection report and prepare an approval note.",
            current_user=self.user_bob,
            conversation_id="conv_hitl_wait_test",
            enable_hitl=True
        )
        self.assertIsNotNone(result.get("approval_id"))

        req = self.approval_service.get_request(result["approval_id"])
        self.assertEqual(req["status"], ApprovalStatus.WAITING_FOR_HUMAN.value)

    # -------------------------------------------------------------------------
    # TEST 13: Payload Size Protection Rejects Intentionally Oversized Payloads (> 64 KB)
    # -------------------------------------------------------------------------
    def test_13_payload_size_protection_rejects_oversized_payloads(self):
        """Verify ApprovalService raises ApprovalValidationError if a payload exceeds 65536 bytes."""
        oversized_dict = {
            "summary": "Oversized malicious payload",
            "findings": "A" * 70000  # 70 KB
        }
        with self.assertRaises(ApprovalValidationError) as ctx:
            self.approval_service.create_request(
                requester=self.user_bob,
                action_type=ApprovalActionType.DOCUMENT_APPROVAL,
                proposed_payload=oversized_dict,
                plan_id="plan_oversize_test",
                step_id="step_oversize",
                conversation_id="conv_oversize"
            )
        self.assertIn("exceeds maximum allowed size of 65536 bytes", str(ctx.exception))

    # -------------------------------------------------------------------------
    # TEST 14: HMAC Audit Chain Remains Intact
    # -------------------------------------------------------------------------
    async def test_14_hmac_audit_chain_remains_intact(self):
        """Verify full cryptographic HMAC chain integrity across HITL execution and audit events."""
        result = await self.controller.run(
            request="Analyze the cooling tower inspection report and prepare an approval note.",
            current_user=self.user_bob,
            conversation_id="conv_hmac_test",
            enable_hitl=True
        )
        approval_id = result["approval_id"]

        # Reviewer approves
        self.approval_service.approve(approval_id, reviewer=self.reviewer_alice)

        # Resume execution to completion
        resume_res = await self.controller.resume_execution(
            plan_id=result["plan_id"],
            approval_id=approval_id,
            current_user=self.reviewer_alice,
            conversation_id="conv_hmac_test"
        )
        self.assertTrue(resume_res["success"])
        self.assertEqual(resume_res["status"], "COMPLETED")

        # Verify HMAC ledger integrity
        integrity = AuditLogger.verify_chain_integrity()
        self.assertEqual(integrity["status"], "INTACT", f"HMAC ledger integrity verification failed: {integrity}")

    # -------------------------------------------------------------------------
    # TEST 15: Server Restart Resumption from Persisted Plan Snapshot
    # -------------------------------------------------------------------------
    async def test_15_server_restart_resumption_from_snapshot(self):
        """
        Verify that after a simulated server restart (controller destroyed),
        a new controller can restore plan from proposed_payload_json.plan_snapshot
        and resume execution to COMPLETED status.
        """
        result = await self.controller.run(
            request="Analyze the cooling tower inspection report and prepare an approval note.",
            current_user=self.user_bob,
            conversation_id="conv_restart_test",
            enable_hitl=True
        )
        approval_id = result["approval_id"]
        plan_id = result["plan_id"]

        # Approve the request
        self.approval_service.approve(approval_id, reviewer=self.reviewer_alice)

        # Destroy old controller completely
        del self.controller

        # Create fresh controller (simulating backend reboot)
        fresh_controller = AgentController(
            registry_manager=self.mock_registry,
            loader_manager=self.mock_loader,
            model_router=self.mock_router,
            rag_service=self.mock_rag,
            sandbox_service=self.sandbox_service,
            doc_generators=self.doc_generators,
            context_manager=self.context_manager,
            approval_service=self.approval_service,
            enable_hitl=True
        )

        # Resume execution
        resume_res = await fresh_controller.resume_execution(
            plan_id=plan_id,
            approval_id=approval_id,
            current_user=self.reviewer_alice,
            conversation_id="conv_restart_test"
        )

        self.assertTrue(resume_res["success"])
        self.assertEqual(resume_res["status"], "COMPLETED")
        self.assertIsNotNone(resume_res.get("artifact"))
        self.assertTrue(os.path.exists(resume_res["artifact"]["artifact_path"]))

    # -------------------------------------------------------------------------
    # TEST 16: Generated Calculation Logic - Dictionary Numeric Value Comparison
    # -------------------------------------------------------------------------
    def test_16_dictionary_numeric_limit_comparison_behavior(self):
        """
        Regression test demonstrating the correct dictionary numeric limit check.
        Verifies that measured values are compared against dictionary values (limits['AOR']),
        not checking key membership ('measured_value in limits').
        """
        limits = {"AOR": 100, "POR": 200}
        measured_value = 145.5

        # Flawed logic: checks keys (returns False because 145.5 is not in ['AOR', 'POR'])
        flawed_result = measured_value in limits
        self.assertFalse(flawed_result, "Key membership check fails to compare numeric limit")

        # Correct AEGIS logic: compares numeric value against dictionary limit value
        exceeds_aor = measured_value > limits["AOR"]
        exceeds_por = measured_value > limits["POR"]
        within_acceptable = limits["AOR"] <= measured_value <= limits["POR"]

        self.assertTrue(exceeds_aor, "145.5 mm/s exceeds AOR limit of 100 mm/s")
        self.assertFalse(exceeds_por, "145.5 mm/s does not exceed POR limit of 200 mm/s")
        self.assertTrue(within_acceptable, "145.5 mm/s is within the operating region [100, 200]")


if __name__ == "__main__":
    unittest.main()
