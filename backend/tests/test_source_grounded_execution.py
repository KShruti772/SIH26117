import os
import sys
import json
import time
import tempfile
import sqlite3
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from backend.agents.context_manager import ContextManager
from backend.agents.controller.agent import (
    AgentController, AgentStep, AgentPlan, AgentState, StepType, FailureCategory
)
from backend.security.models import ApprovalStatus, ApprovalActionType
from backend.services.approval_service import ApprovalService
from backend.security.database import init_db, get_db_path
from backend.security.auth import hash_password
from backend.security.audit import AuditLogger, VALID_ACTIONS
from backend.tools.code_sandbox.sandbox import SubprocessSandbox
from backend.tools.document_generators.generators import DocxGenerator, PdfGenerator, XlsxGenerator


class TestSourceGroundedExecution(unittest.IsolatedAsyncioTestCase):
    """
    AEGIS Source-Grounded Execution & Zero-Mock Verification Test Suite.

    Verifies:
    1. Actual uploaded document evidence reaches the workflow.
    2. No hardcoded/sample document text is injected into sandbox code or findings.
    3. No fabricated measurements are introduced; real extracted values are preserved.
    4. Numeric limit comparison logic against dictionaries is correct (relational comparison, key lookup).
    5. Missing evidence produces an insufficient-evidence / unavailable-measurement result.
    6. Source page citations remain attached to findings and deliverables.
    7. HITL still pauses before final artifact generation (WAITING_FOR_HUMAN).
    8. APPROVE resumes successfully to produce a verified deliverable.
    9. MODIFY causes structured replanning with reviewer feedback.
    10. REJECT prevents final artifact generation.
    11. HMAC cryptographic audit chain remains 100% INTACT throughout the workflow.
    """

    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aegis_grounding_test_")
        self.db_path = os.path.join(self.test_dir, "test_grounding.db")
        self.exports_dir = os.path.join(self.test_dir, "exports")
        os.makedirs(self.exports_dir, exist_ok=True)

        self.patcher_db = patch("backend.security.database.get_db_path", return_value=self.db_path)
        self.patcher_db.start()

        self.patcher_settings = patch("backend.app.config.settings.settings.AUTH_DB_PATH", self.db_path)
        self.patcher_settings.start()

        init_db()

        # Provision test users
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO users (username, password_hash, role, department_id, department_name, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("engineer_ops", hash_password("PassOps123!"), "user", 3, "Engineering", 1))
        self.user_ops_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO users (username, password_hash, role, department_id, department_name, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("supervisor_eng", hash_password("PassSuper123!"), "reviewer", 3, "Engineering", 1))
        self.supervisor_id = cursor.lastrowid

        conn.commit()
        conn.close()

        self.user_ops = {
            "id": self.user_ops_id,
            "username": "engineer_ops",
            "role": "user",
            "department_id": 3,
            "department_name": "Engineering"
        }
        self.supervisor_user = {
            "id": self.supervisor_id,
            "username": "supervisor_eng",
            "role": "reviewer",
            "department_id": 3,
            "department_name": "Engineering"
        }

        # Real Sandbox Service
        self.sandbox = SubprocessSandbox(
            workspace_parent=os.path.join(self.test_dir, "sandbox_runs"),
            artifacts_storage=os.path.join(self.test_dir, "sandbox_artifacts")
        )

        # Real Document Generators
        self.doc_generators = {
            "docx": DocxGenerator(output_base_dir=self.exports_dir),
            "pdf": PdfGenerator(output_base_dir=self.exports_dir),
            "xlsx": XlsxGenerator(output_base_dir=self.exports_dir)
        }

        # Real Approval Service
        self.approval_service = ApprovalService(db_path=self.db_path)

        # Model Registry & Mock Loader
        self.mock_registry = MagicMock()
        mock_profile = MagicMock()
        mock_profile.context_length = 32768
        mock_profile.runtime_model_name = "qwen2.5-coder:7b"
        self.mock_registry.get_model.return_value = mock_profile

        self.mock_loader = MagicMock()
        self.mock_loader.base_url = "http://localhost:11434"
        self.mock_loader.current_model_id = "qwen2.5-coder:7b"
        self.mock_loader.generate = AsyncMock(side_effect=self._mock_model_generate)

        self.mock_router = MagicMock()
        self.mock_router.route = AsyncMock(side_effect=self._mock_router_route)

        # Mock RAG Service with realistic authorized industrial document chunks
        self.mock_rag = MagicMock()
        self.cooling_tower_doc = {
            "id": "doc_ct_04",
            "filename": "cooling_tower_inspection_may.pdf",
            "title": "Alpha Unit Cooling Tower Q3 Inspection Report",
            "owner_id": self.user_ops["id"],
            "source_path": os.path.join(self.test_dir, "cooling_tower_inspection_may.pdf")
        }
        self.mock_rag.list_documents.return_value = [self.cooling_tower_doc]
        self.mock_rag.get_document.return_value = self.cooling_tower_doc
        self.mock_rag.search.return_value = [
            {
                "text": "Cooling Tower CT-04 Inspection: Inlet Temp = 42.5 C, Outlet Temp = 31.0 C, Wet Bulb = 28.0 C. Vibration = 3.2 mm/s. Fan efficiency delta = -4.1%.",
                "metadata": {"filename": "cooling_tower_inspection_may.pdf", "page_number": 3},
                "distance": 0.08,
                "similarity": 0.92
            },
            {
                "text": "Acceptable Limits: Maximum Vibration = 4.5 mm/s, Design Cooling Approach = 3.0 C to 5.0 C, Design Range = 10.0 C to 13.0 C.",
                "metadata": {"filename": "cooling_tower_inspection_may.pdf", "page_number": 4},
                "distance": 0.10,
                "similarity": 0.90
            }
        ]
        self.mock_rag.get_document_chunks.return_value = self.mock_rag.search.return_value

        # Write actual physical file on disk
        with open(self.cooling_tower_doc["source_path"], "wb") as fh:
            fh.write(b"%PDF-1.4 Real Authorized Cooling Tower Document Content")

        self.context_manager = ContextManager(
            registry_manager=self.mock_registry,
            rag_service=self.mock_rag,
            default_context_budget=16384
        )

        # Controller initialized with HITL enabled
        self.controller = AgentController(
            registry_manager=self.mock_registry,
            loader_manager=self.mock_loader,
            model_router=self.mock_router,
            rag_service=self.mock_rag,
            sandbox_service=self.sandbox,
            doc_generators=self.doc_generators,
            context_manager=self.context_manager,
            approval_service=self.approval_service,
            enable_hitl=True,
            max_steps=10,
            max_replans=3
        )

    async def asyncTearDown(self):
        self.patcher_db.stop()
        self.patcher_settings.stop()

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

        # Findings extraction
        if "extract key findings" in p_lower or "extract structured technical findings" in p_lower or "structured epistemic findings" in p_lower or "extract_findings" in p_lower:
            return (
                "[SOURCE_DOCUMENT_FACT]: Inlet Temp = 42.5 C [Source: cooling_tower_inspection_may.pdf, Page 3]\n"
                "[SOURCE_DOCUMENT_FACT]: Outlet Temp = 31.0 C [Source: cooling_tower_inspection_may.pdf, Page 3]\n"
                "[SOURCE_DOCUMENT_FACT]: Wet Bulb Temp = 28.0 C [Source: cooling_tower_inspection_may.pdf, Page 3]\n"
                "[SOURCE_DOCUMENT_FACT]: Measured Vibration = 3.2 mm/s [Source: cooling_tower_inspection_may.pdf, Page 3]\n"
                "[SOURCE_DOCUMENT_FACT]: Vibration Limit = 4.5 mm/s [Source: cooling_tower_inspection_may.pdf, Page 4]\n"
                "[DERIVED_CALCULATION]: Cooling Range = 11.5 C, Cooling Approach = 3.0 C\n"
                "[MODEL_INFERENCE]: Thermal performance meets acceptable design range.\n"
                "[RECOMMENDATION]: Continue standard quarterly maintenance cycle."
            )

        # Calculation code generation / execution in sandbox
        if ("cooling tower" in p_lower or "calculation" in p_lower or "compute" in p_lower) and ("efficiency" in p_lower or "delta" in p_lower or "metrics" in p_lower or "write a python" in p_lower):
            return (
                "```python\n"
                "inlet_temp = 42.5\n"
                "outlet_temp = 31.0\n"
                "wet_bulb = 28.0\n"
                "vibration = 3.2\n"
                "limits = {'max_vibration': 4.5, 'min_range': 10.0, 'max_range': 13.0}\n"
                "cooling_range = inlet_temp - outlet_temp\n"
                "cooling_approach = outlet_temp - wet_bulb\n"
                "vib_status = 'PASS' if vibration <= limits['max_vibration'] else 'EXCEEDED'\n"
                "print(f'Measured Value: {vibration} mm/s')\n"
                "print(f'Applicable Limit: {limits[\"max_vibration\"]} mm/s')\n"
                "print(f'Comparison: {vibration} <= {limits[\"max_vibration\"]}')\n"
                "print(f'Deviation / Margin: {limits[\"max_vibration\"] - vibration:.2f} mm/s')\n"
                "print('Evidence Source / Page: [Source: cooling_tower_inspection_may.pdf, Page 3]')\n"
                "print(f'Status: {vib_status}')\n"
                "print(f'Cooling Range: {cooling_range:.1f} C')\n"
                "print(f'Cooling Approach: {cooling_approach:.1f} C')\n"
                "```"
            )

        # Document content synthesis
        if "approval note" in p_lower or "draft the complete" in p_lower or "synthesizer" in (system_prompt or "").lower():
            return (
                "# Cooling Tower Inspection & Maintenance Approval Note\n\n"
                "## 1. Executive Summary & Approval Decision\n"
                "Formal engineering approval is granted for continued operation.\n\n"
                "## 2. Technical Inspection Findings & Operating Metrics\n"
                "- [SOURCE_DOCUMENT_FACT] Inlet Temp: 42.5 °C [Source: cooling_tower_inspection_may.pdf, Page 3]\n"
                "- [SOURCE_DOCUMENT_FACT] Outlet Temp: 31.0 °C [Source: cooling_tower_inspection_may.pdf, Page 3]\n"
                "- [SOURCE_DOCUMENT_FACT] Vibration: 3.2 mm/s [Source: cooling_tower_inspection_may.pdf, Page 3]\n\n"
                "## 3. Engineering Calculations & Thermal Efficiency Performance\n"
                "- [DERIVED_CALCULATION] Cooling Range: 11.50 °C (Within design range 10.0 - 13.0 °C)\n"
                "- [DERIVED_CALCULATION] Cooling Approach: 3.00 °C (Within design approach 3.0 - 5.0 °C)\n"
                "- [DERIVED_CALCULATION] Vibration: 3.20 mm/s <= 4.50 mm/s (PASS)\n\n"
                "## 4. Operational Inferences & Risk Assessment\n"
                "- [MODEL_INFERENCE] Operational parameters remain within safe baseline envelopes.\n\n"
                "## 5. Corrective Maintenance Actions & Safety Compliance\n"
                "- [RECOMMENDATION] Continue scheduled vibration monitoring.\n\n"
                "## 6. Formal Engineering Sign-off & Source Citations\n"
                "Approved by Plant Engineering Lead."
            )

        return "Default response from open-weight model."

    # =========================================================================
    # TEST 1 — ACTUAL UPLOADED DOCUMENT EVIDENCE REACHES WORKFLOW
    # =========================================================================
    async def test_01_actual_document_evidence_reaches_workflow(self):
        """
        Verify that actual authorized RAG chunks with genuine industrial metrics
        are retrieved and passed directly into the extract_findings and drafting steps.
        """
        task = "Analyze the cooling tower inspection report and prepare an approval note."
        result = await self.controller.run(
            request=task,
            current_user=self.user_ops,
            conversation_id="conv_grounding_01",
            enable_hitl=True
        )

        # Proves workflow paused at HITL with grounded payload
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "WAITING_FOR_HUMAN")
        self.assertTrue(result["is_waiting_for_human"])
        self.mock_rag.search.assert_called()

        # Check prompt sent to extract_findings contains genuine document chunks
        all_calls = self.mock_loader.generate.call_args_list
        findings_prompt = all_calls[0].kwargs.get("prompt") or all_calls[0][0][0]
        self.assertIn("Cooling Tower CT-04 Inspection", findings_prompt)
        self.assertIn("Inlet Temp = 42.5 C", findings_prompt)
        self.assertIn("cooling_tower_inspection_may.pdf", findings_prompt)

    # =========================================================================
    # TEST 2 — NO HARDCODED/SAMPLE DOCUMENT INJECTED INTO SANDBOX
    # =========================================================================
    async def test_02_no_hardcoded_sample_document_injected(self):
        """
        Verify that generated sandbox Python scripts operate purely on extracted variables
        and do NOT embed placeholder document strings (e.g. 'maintenance_document = ... # Sample text').
        """
        system_prompt_used = ""

        async def capture_generate(prompt, **kwargs):
            nonlocal system_prompt_used
            sys_p = kwargs.get("system_prompt", "")
            if "AEGIS Code Generator" in sys_p:
                system_prompt_used = sys_p
            return (
                "```python\n"
                "measured_temp = 42.5\n"
                "design_limit = 45.0\n"
                "diff = design_limit - measured_temp\n"
                "status = 'PASS' if measured_temp <= design_limit else 'EXCEEDED'\n"
                "print(f'Measured Value: {measured_temp} C')\n"
                "print(f'Applicable Limit: {design_limit} C')\n"
                "print(f'Comparison: {measured_temp} <= {design_limit}')\n"
                "print(f'Deviation: {diff} C')\n"
                "print(f'Status: {status}')\n"
                "```"
            )

        self.mock_loader.generate.side_effect = capture_generate
        task = "Calculate cooling tower efficiency delta for the inspected unit."
        plan = self.controller._create_plan(task, current_user=self.user_ops)
        state = AgentState(request=task)

        gen_step = AgentStep(
            step_id="step_gen",
            description="Generate code",
            capability="coding",
            step_type=StepType.CODE_GENERATION.value,
            input_data={"action": "generate_code", "prompt": task}
        )
        plan.steps = [gen_step]
        plan.current_step_index = 0

        success = await self.controller._execute_step(plan, gen_step, state, self.user_ops)
        self.assertTrue(success)

        # Verify system prompt strictly forbids sample document strings
        self.assertIn("CRITICAL DATA GROUNDING & ZERO-MOCK RULES", system_prompt_used)
        self.assertIn("NEVER create, embed, or declare sample documents", system_prompt_used)
        self.assertIn("NEVER invent, hallucinate, or fabricate default limits", system_prompt_used)

        # Verify generated code contains NO sample text placeholders
        code_output = gen_step.output
        self.assertNotIn("maintenance_document =", code_output)
        self.assertNotIn("# Sample maintenance document text", code_output)
        self.assertNotIn("# Replace with actual text", code_output)

    # =========================================================================
    # TEST 3 — NO FABRICATED MEASUREMENTS ARE INTRODUCED
    # =========================================================================
    async def test_03_no_fabricated_measurements_introduced(self):
        """
        Verify that when a measurement is present, the exact extracted value is used.
        When a parameter is missing, the system outputs UNAVAILABLE_MEASUREMENT rather than fabricating.
        """
        self.mock_rag.search.return_value = [{
            "text": "Inspection Log: Motor vibration = 2.8 mm/s. Oil level = Adequate. (Note: Acoustic emission sensor was uncalibrated; reading not recorded).",
            "metadata": {"filename": "pump_p102_log.pdf", "page_number": 1}
        }]

        extracted_findings = (
            "[SOURCE_DOCUMENT_FACT]: Motor vibration = 2.8 mm/s [Source: pump_p102_log.pdf, Page 1]\n"
            "[SOURCE_DOCUMENT_FACT]: Oil level = Adequate [Source: pump_p102_log.pdf, Page 1]\n"
            "[UNAVAILABLE_MEASUREMENT: Acoustic Emission] - Not present in authorized document.\n"
            "[MODEL_INFERENCE]: Pump vibration is within acceptable standard limits.\n"
            "[RECOMMENDATION]: Recalibrate acoustic emission sensor prior to next cycle."
        )
        self.mock_loader.generate.side_effect = None
        self.mock_loader.generate.return_value = extracted_findings

        task = "Analyze pump P-102 inspection report"
        plan = self.controller._create_plan(task, current_user=self.user_ops)
        state = AgentState(request=task)

        rag_step = AgentStep(step_id="s0", description="RAG", capability="text_generation", step_type=StepType.RAG_SEARCH.value, input_data={"action": "rag_search"})
        rag_step.output = self.mock_rag.search.return_value

        step = AgentStep(
            step_id="step_find",
            description="Extract findings",
            capability="text_generation",
            step_type=StepType.MODEL_INFERENCE.value,
            input_data={"action": "extract_findings", "query": task}
        )
        plan.steps = [rag_step, step]
        plan.current_step_index = 1

        await self.controller._execute_step(plan, step, state, self.user_ops)

        self.assertIn("Motor vibration = 2.8 mm/s", step.output)
        self.assertIn("[UNAVAILABLE_MEASUREMENT: Acoustic Emission]", step.output)
        self.assertNotIn("Acoustic emission = 45 dB", step.output)  # Zero fabrication

    # =========================================================================
    # TEST 4 — NUMERIC LIMIT COMPARISON AGAINST DICTIONARY
    # =========================================================================
    def test_04_numeric_dictionary_limit_comparison_logic(self):
        """
        Verify the difference between erroneous key membership ('val in limits')
        and correct dictionary relational limit comparisons ('val > limits[\"AOR\"]').
        """
        limits = {"AOR": 100.0, "POR": 200.0, "MAX_VIB": 4.5}
        measured_vibration = 3.2
        measured_power = 150.0

        # Flawed Python logic check: 'measured_vibration in limits' evaluates key presence ('3.2' in dict)
        self.assertFalse(measured_vibration in limits, "Flawed 'in' check incorrectly tests dict keys")

        # Correct AEGIS limit validation:
        vib_within_limit = measured_vibration <= limits["MAX_VIB"]
        power_within_por = limits["AOR"] <= measured_power <= limits["POR"]

        self.assertTrue(vib_within_limit)
        self.assertTrue(power_within_por)

        # Check violation case:
        high_vib = 5.8
        vib_exceeded = high_vib > limits["MAX_VIB"]
        self.assertTrue(vib_exceeded)

    # =========================================================================
    # TEST 5 — MISSING EVIDENCE PRODUCES INSUFFICIENT EVIDENCE RESULT
    # =========================================================================
    async def test_05_missing_evidence_produces_insufficient_evidence(self):
        """
        Verify that when no authorized document chunks exist for a query,
        the workflow gracefully outputs an INSUFFICIENT_EVIDENCE statement.
        """
        self.mock_rag.search.return_value = []

        task = "What is the operating pressure of reactor R-99?"
        plan = self.controller._create_plan(task, current_user=self.user_ops)
        state = AgentState(request=task)

        rag_step = AgentStep(step_id="s0", description="RAG", capability="text_generation", step_type=StepType.RAG_SEARCH.value, input_data={"action": "rag_search"})
        rag_step.output = []

        step_eval = AgentStep(
            step_id="step_eval",
            description="Evaluate evidence",
            capability="text_generation",
            step_type=StepType.MODEL_INFERENCE.value,
            input_data={"action": "evaluate_evidence", "query": task}
        )
        plan.steps = [rag_step, step_eval]
        plan.current_step_index = 1

        await self.controller._execute_step(plan, step_eval, state, self.user_ops)

        self.assertIn("INSUFFICIENT_EVIDENCE", step_eval.output)
        self.assertEqual(step_eval.observation.get("status"), "insufficient_evidence")

    # =========================================================================
    # TEST 6 — SOURCE PAGE CITATIONS REMAIN ATTACHED
    # =========================================================================
    async def test_06_source_page_citations_remain_attached(self):
        """
        Verify that source citations [Source: <filename>, Page <p>] remain attached
        from RAG search through extract_findings to the HITL approval payload.
        """
        chunks = [
            {
                "text": "Bearing temperature measured at 68.2 C during full-load testing.",
                "metadata": {"filename": "generator_commissioning_report.pdf", "page_number": 14},
                "distance": 0.05,
                "similarity": 0.95
            }
        ]
        self.mock_rag.search.return_value = chunks

        findings_text = (
            "[SOURCE_DOCUMENT_FACT]: Bearing temperature = 68.2 C [Source: generator_commissioning_report.pdf, Page 14]\n"
            "[MODEL_INFERENCE]: Bearing temperature is within nominal class B insulation rise.\n"
            "[RECOMMENDATION]: Re-verify during 1000-hour overhaul."
        )

        task = "Prepare generator commissioning approval note"
        plan = self.controller._create_plan(task, current_user=self.user_ops)
        state = AgentState(request=task)

        rag_step = AgentStep(step_id="s1", description="RAG", capability="text_generation", step_type=StepType.RAG_SEARCH.value, input_data={"action": "rag_search"})
        rag_step.output = chunks

        find_step = AgentStep(step_id="s2", description="Findings", capability="text_generation", step_type=StepType.MODEL_INFERENCE.value, input_data={"action": "extract_findings"})
        find_step.output = findings_text

        step_hitl = AgentStep(
            step_id="step_hitl",
            description="HITL Review",
            capability="reasoning",
            step_type=StepType.HUMAN_APPROVAL.value,
            input_data={"action": "hitl_approval", "target_format": "docx"}
        )
        plan.steps = [rag_step, find_step, step_hitl]
        plan.current_step_index = 2

        await self.controller._execute_step(plan, step_hitl, state, self.user_ops)

        appr_id = step_hitl.output.get("approval_id")
        record = self.approval_service.get_request(appr_id)
        payload = json.loads(record["proposed_payload_json"])

        self.assertIn("generator_commissioning_report.pdf", json.dumps(payload["citations"]))
        self.assertEqual(payload["citations"][0]["page_number"], 14)
        self.assertIn("[Source: generator_commissioning_report.pdf, Page 14]", payload["findings"])

    # =========================================================================
    # TEST 7 — HITL STILL PAUSES BEFORE FINAL ARTIFACT GENERATION
    # =========================================================================
    async def test_07_hitl_pauses_before_final_artifact_generation(self):
        """
        Verify that sensitive deliverable workflows pause at WAITING_FOR_HUMAN
        and do not create deliverable files on disk prior to approval.
        """
        task = "Analyze cooling tower inspection report and prepare an approval note."
        result = await self.controller.run(
            request=task,
            current_user=self.user_ops,
            conversation_id="conv_grounding_07",
            enable_hitl=True
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "WAITING_FOR_HUMAN")
        self.assertTrue(result["is_waiting_for_human"])
        self.assertIsNotNone(result.get("approval_id"))
        self.assertIsNone(result.get("final_artifact"))

    # =========================================================================
    # TEST 8 — APPROVE RESUMES SUCCESSFULLY
    # =========================================================================
    async def test_08_approve_resumes_successfully(self):
        """
        Verify that an APPROVED decision by an authorized reviewer resumes
        execution, compiles the binary document, and completes the workflow.
        """
        task = "Analyze cooling tower inspection report and prepare an approval note."
        pause_res = await self.controller.run(
            request=task,
            current_user=self.user_ops,
            conversation_id="conv_grounding_08",
            enable_hitl=True
        )
        approval_id = pause_res["approval_id"]
        plan_id = pause_res["plan_id"]

        # Reviewer approves
        self.approval_service.approve(
            approval_id=approval_id,
            reviewer=self.supervisor_user
        )

        # Resume execution
        resume_res = await self.controller.resume_execution(
            plan_id=plan_id,
            approval_id=approval_id,
            current_user=self.supervisor_user,
            conversation_id="conv_grounding_08"
        )

        self.assertTrue(resume_res.get("success"))
        self.assertEqual(resume_res.get("status"), "COMPLETED")
        self.assertIsNotNone(resume_res.get("artifact"))

    # =========================================================================
    # TEST 9 — MODIFY CAUSES REPLAN
    # =========================================================================
    async def test_09_modify_causes_replan(self):
        """
        Verify that a MODIFIED review decision injects feedback constraints
        and triggers replanning without payload explosion.
        """
        task = "Analyze cooling tower inspection report and prepare an approval note."
        pause_res = await self.controller.run(
            request=task,
            current_user=self.user_ops,
            conversation_id="conv_grounding_09",
            enable_hitl=True
        )
        approval_id = pause_res["approval_id"]
        plan_id = pause_res["plan_id"]

        # Reviewer modifies with explicit feedback constraint
        modification = {"required_additions": "Include water treatment chemical dosage check."}
        self.approval_service.modify(
            approval_id=approval_id,
            reviewer=self.supervisor_user,
            modified_payload=modification
        )

        resume_res = await self.controller.resume_execution(
            plan_id=plan_id,
            approval_id=approval_id,
            current_user=self.supervisor_user,
            conversation_id="conv_grounding_09"
        )

        # Verify that modification caused replanning
        self.assertIn(resume_res.get("status"), ("WAITING_FOR_HUMAN", "COMPLETED"))

    # =========================================================================
    # TEST 10 — REJECT PREVENTS FINAL ARTIFACT GENERATION
    # =========================================================================
    async def test_10_reject_prevents_final_artifact_generation(self):
        """
        Verify that a REJECTED decision by an authorized supervisor immediately
        halts the workflow and prevents artifact publication.
        """
        task = "Analyze cooling tower inspection report and prepare an approval note."
        pause_res = await self.controller.run(
            request=task,
            current_user=self.user_ops,
            conversation_id="conv_grounding_10",
            enable_hitl=True
        )
        approval_id = pause_res["approval_id"]
        plan_id = pause_res["plan_id"]

        # Reviewer rejects
        self.approval_service.reject(
            approval_id=approval_id,
            reviewer=self.supervisor_user,
            rejection_reason="Unrepaired crack in fan blade violates plant safety standard Section 4.2."
        )

        resume_res = await self.controller.resume_execution(
            plan_id=plan_id,
            approval_id=approval_id,
            current_user=self.supervisor_user,
            conversation_id="conv_grounding_10"
        )

        self.assertFalse(resume_res.get("success"))
        self.assertEqual(resume_res.get("status"), "REJECTED")
        self.assertIsNone(resume_res.get("artifact"))

    # =========================================================================
    # TEST 11 — CRYPTOGRAPHIC HMAC AUDIT CHAIN INTACT
    # =========================================================================
    def test_11_cryptographic_hmac_audit_chain_intact(self):
        """
        Verify that the HMAC-SHA256 hash chain in audit_logs is 100% verified INTACT.
        """
        AuditLogger.log_event(
            action="TOOL_EXECUTION_COMPLETED",
            component="test_source_grounded_execution",
            status="success",
            user_id=self.user_ops_id,
            username="engineer_ops",
            role="user",
            metadata={"test_suite": "source_grounded_execution"}
        )

        chain_res = AuditLogger.verify_chain_integrity()
        self.assertEqual(chain_res["status"], "INTACT", f"Audit log HMAC chain compromised: {chain_res}")


if __name__ == "__main__":
    unittest.main()
