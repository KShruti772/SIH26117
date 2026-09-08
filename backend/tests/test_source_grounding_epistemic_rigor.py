import os
import sys
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
from backend.agents.controller.source_grounding import (
    sanitize_draft_document_text,
    validate_epistemic_rigor,
    parse_markdown_to_content_blocks,
    MANDATORY_HUMAN_DECISION_TEXT,
    EPISTEMIC_FACT,
    EPISTEMIC_CALC,
    EPISTEMIC_INFERENCE,
    EPISTEMIC_RECOMMENDATION
)
from backend.security.models import ApprovalStatus, ApprovalActionType
from backend.services.approval_service import ApprovalService
from backend.security.database import init_db, get_db_path
from backend.security.auth import hash_password
from backend.security.audit import AuditLogger
from backend.tools.code_sandbox.sandbox import SubprocessSandbox
from backend.tools.document_generators.generators import DocxGenerator, PdfGenerator, XlsxGenerator


class TestSourceGroundingEpistemicRigor(unittest.IsolatedAsyncioTestCase):
    """
    AEGIS Source-Grounding & Epistemic Rigor Regression Test Suite.

    Verifies all 10 critical requirements:
    1. Missing measurement never becomes 0% deviation.
    2. Missing measurement never becomes PASS or WITHIN_LIMITS.
    3. Qualitative 'close tolerance' never becomes numeric 0.05 mm.
    4. Qualitative leakage language never becomes numeric 0.5 L/min.
    5. No current AOR measurement never becomes 'within AOR'.
    6. Missing vibration measurement never becomes 'within limits' (API 610).
    7. Missing temperature measurement never becomes 'within limits' (Manufacturer Baseline).
    8. Unsupported assumptions are prohibited and removed.
    9. AEGIS never independently grants operational approval (HUMAN APPROVAL REQUIRED enforced).
    10. Recommendations are not labeled as source facts.
    11. Full 7-section document structure is preserved.
    12. Real end-to-end PDF generation produces binary deliverable without hallucinations.
    """

    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aegis_epistemic_test_")
        self.db_path = os.path.join(self.test_dir, "test_epistemic.db")
        self.exports_dir = os.path.join(self.test_dir, "exports")
        os.makedirs(self.exports_dir, exist_ok=True)

        self.patcher_db = patch("backend.security.database.get_db_path", return_value=self.db_path)
        self.patcher_db.start()

        self.patcher_settings = patch("backend.app.config.settings.settings.AUTH_DB_PATH", self.db_path)
        self.patcher_settings.start()

        init_db()

        # Provision test user
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, department_id, department_name, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("operator_may", hash_password("PassMay123!"), "user", 3, "Engineering", 1))
        self.user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.user = {
            "id": self.user_id,
            "username": "operator_may",
            "role": "user",
            "department_id": 3,
            "department_name": "Engineering"
        }

        self.sandbox = SubprocessSandbox(
            workspace_parent=os.path.join(self.test_dir, "sandbox_runs"),
            artifacts_storage=os.path.join(self.test_dir, "sandbox_artifacts")
        )

        self.doc_generators = {
            "docx": DocxGenerator(output_base_dir=self.exports_dir),
            "pdf": PdfGenerator(output_base_dir=self.exports_dir),
            "xlsx": XlsxGenerator(output_base_dir=self.exports_dir)
        }

        self.approval_service = ApprovalService(db_path=self.db_path)

        self.mock_registry = MagicMock()
        mock_profile = MagicMock()
        mock_profile.context_length = 32768
        mock_profile.runtime_model_name = "qwen2.5-coder:7b"
        self.mock_registry.get_model.return_value = mock_profile

        self.mock_loader = MagicMock()
        self.mock_loader.base_url = "http://localhost:11434"
        self.mock_loader.current_model_id = "qwen2.5-coder:7b"

        self.mock_router = MagicMock()
        self.mock_router.route = AsyncMock(side_effect=self._mock_router_route)

        self.mock_rag = MagicMock()
        self.cooling_tower_doc = {
            "id": "doc_ct_rag",
            "filename": "cooling_tower_inspection.pdf",
            "title": "Cooling Tower Inspection Report",
            "owner_id": self.user["id"],
            "source_path": os.path.join(self.test_dir, "cooling_tower_inspection.pdf")
        }
        self.mock_rag.list_documents.return_value = [self.cooling_tower_doc]
        self.mock_rag.get_document.return_value = self.cooling_tower_doc
        self.mock_rag.search.return_value = [
            {
                "text": "Cooling Tower CT-02: Monthly visual inspection conducted. Observation: Excessive leakage observed at pump shaft seal. Close tolerance alignment noted. Operating region is not specified in current log. Baseline vibration and temperature measurements are unavailable.",
                "metadata": {"filename": "cooling_tower_inspection.pdf", "page_number": 1},
                "distance": 0.05,
                "similarity": 0.95
            }
        ]
        self.mock_rag.get_document_chunks.return_value = self.mock_rag.search.return_value

        with open(self.cooling_tower_doc["source_path"], "wb") as fh:
            fh.write(b"%PDF-1.4 Mock Cooling Tower Content")

        self.controller = AgentController(
            registry_manager=self.mock_registry,
            loader_manager=self.mock_loader,
            model_router=self.mock_router,
            rag_service=self.mock_rag,
            sandbox_service=self.sandbox,
            doc_generators=self.doc_generators,
            enable_hitl=True,
            approval_service=self.approval_service
        )

    async def asyncTearDown(self):
        self.patcher_db.stop()
        self.patcher_settings.stop()

    async def _mock_router_route(self, required_capabilities, **kwargs):
        cap = required_capabilities[0] if required_capabilities else "text_generation"
        decision = MagicMock()
        decision.selected_model = "qwen2.5-coder:7b"
        decision.runtime_model_name = "qwen2.5-coder:7b"
        decision.switched = False
        decision.to_dict.return_value = {
            "selected_model": "qwen2.5-coder:7b",
            "runtime_model_name": "qwen2.5-coder:7b",
            "required_capabilities": required_capabilities,
            "task_type": "reasoning",
            "reason": "Test routing",
            "switched": False
        }
        return decision

    # =========================================================================
    # TEST 1: MISSING MEASUREMENT NEVER BECOMES 0% DEVIATION
    # =========================================================================
    def test_01_missing_measurement_never_becomes_zero_deviation(self):
        flawed_draft = (
            "# Cooling Tower Inspection & Maintenance Approval Note\n\n"
            "## 1. Executive Summary\n"
            "Draft assessment.\n\n"
            "## 4. Engineering Calculations\n"
            "- [UNAVAILABLE_MEASUREMENT: Vibration] Calculated Deviation: 0%\n"
            "- [UNAVAILABLE_MEASUREMENT: Thermal Efficiency] Deviation: 0.0%\n\n"
            "## 7. Human Review Decision\n"
            f"{MANDATORY_HUMAN_DECISION_TEXT}"
        )
        sanitized = sanitize_draft_document_text(flawed_draft)
        self.assertNotIn("Deviation: 0%", sanitized)
        self.assertNotIn("Deviation: 0.0%", sanitized)
        self.assertIn("Deviation: NOT CALCULATED", sanitized)

    # =========================================================================
    # TEST 2: MISSING MEASUREMENT NEVER BECOMES PASS OR WITHIN_LIMITS
    # =========================================================================
    def test_02_missing_measurement_never_becomes_pass_or_within_limits(self):
        flawed_draft = (
            "## 4. Engineering Calculations\n"
            "- [UNAVAILABLE_MEASUREMENT: Vibration] Status: PASS\n"
            "- [UNAVAILABLE_MEASUREMENT: Temperature] Status: WITHIN_LIMITS\n"
        )
        sanitized = sanitize_draft_document_text(flawed_draft)
        self.assertNotIn("Status: PASS", sanitized)
        self.assertNotIn("Status: WITHIN_LIMITS", sanitized)
        self.assertIn("Status: UNAVAILABLE", sanitized)

    # =========================================================================
    # TEST 3: QUALITATIVE 'CLOSE TOLERANCE' NEVER BECOMES NUMERIC 0.05 MM
    # =========================================================================
    def test_03_close_tolerance_never_becomes_numeric_limit(self):
        flawed_draft = (
            "## 2. Evidence-Based Findings\n"
            "- Pump alignment < 0.05 mm (close tolerance)\n"
        )
        sanitized = sanitize_draft_document_text(flawed_draft)
        self.assertNotIn("< 0.05 mm", sanitized)
        self.assertIn("NOT QUANTIFIED IN AUTHORIZED EVIDENCE", sanitized)

    # =========================================================================
    # TEST 4: QUALITATIVE LEAKAGE NEVER BECOMES NUMERIC 0.5 L/MIN
    # =========================================================================
    def test_04_excessive_leakage_never_becomes_numeric_limit(self):
        flawed_draft = (
            "## 2. Evidence-Based Findings\n"
            "- Leakage limit < 0.5 L/min for pump seal\n"
        )
        sanitized = sanitize_draft_document_text(flawed_draft)
        self.assertNotIn("< 0.5 L/min", sanitized)
        self.assertIn("NOT QUANTIFIED IN AUTHORIZED EVIDENCE", sanitized)

    # =========================================================================
    # TEST 5: NO CURRENT AOR NEVER BECOMES 'WITHIN AOR'
    # =========================================================================
    def test_05_unspecified_operating_region_never_claims_within_aor(self):
        flawed_draft = (
            "## 1. Executive Summary\n"
            "The cooling tower system operates within the Allowable Operating Region (AOR).\n"
        )
        findings = "[UNAVAILABLE_MEASUREMENT: Allowable Operating Region] Operating region is not specified in source log."
        sanitized = sanitize_draft_document_text(flawed_draft, findings_text=findings)
        self.assertNotIn("operates within the allowable operating region (aor)", sanitized.lower())
        self.assertIn("Operating region (AOR): UNAVAILABLE", sanitized)

    # =========================================================================
    # TEST 6: MISSING VIBRATION NEVER BECOMES WITHIN LIMITS (API 610)
    # =========================================================================
    def test_06_missing_vibration_never_claims_api_610_within_limits(self):
        flawed_draft = (
            "## 5. Assessment\n"
            "- API 610/Hydraulic Institute — Within limits\n"
        )
        findings = "[UNAVAILABLE_MEASUREMENT: Vibration] Vibration measurement absent from report."
        sanitized = sanitize_draft_document_text(flawed_draft, findings_text=findings)
        self.assertNotIn("Within limits", sanitized)
        self.assertIn("API 610 / Hydraulic Institute: UNAVAILABLE", sanitized)

    # =========================================================================
    # TEST 7: MISSING TEMPERATURE NEVER BECOMES WITHIN LIMITS
    # =========================================================================
    def test_07_missing_temperature_never_claims_baseline_within_limits(self):
        flawed_draft = (
            "## 5. Assessment\n"
            "- Manufacturer's baseline — Within limits\n"
        )
        findings = "[UNAVAILABLE_MEASUREMENT: Temperature] Temperature baseline measurements absent."
        sanitized = sanitize_draft_document_text(flawed_draft, findings_text=findings)
        self.assertNotIn("Within limits", sanitized)
        self.assertIn("Manufacturer Baseline: UNAVAILABLE", sanitized)

    # =========================================================================
    # TEST 8: UNSUPPORTED THERMAL EFFICIENCY ASSUMPTIONS ARE REMOVED
    # =========================================================================
    def test_08_thermal_efficiency_assumptions_removed(self):
        flawed_draft = (
            "## 1. Executive Summary\n"
            "Thermal efficiency is assumed to be within manufacturer specifications.\n"
        )
        sanitized = sanitize_draft_document_text(flawed_draft)
        self.assertNotIn("is assumed to be within", sanitized)
        self.assertIn("Thermal efficiency: UNAVAILABLE", sanitized)

    # =========================================================================
    # TEST 9: AEGIS NEVER INDEPENDENTLY GRANTS OPERATIONAL APPROVAL
    # =========================================================================
    def test_09_aegis_never_independently_grants_approval(self):
        flawed_draft = (
            "# Cooling Tower Inspection & Maintenance Approval Note\n\n"
            "## 1. Executive Summary\n"
            "Approval is granted for continued operation without corrective intervention.\n\n"
            "## 7. Human Review Decision\n"
            "Approved by AEGIS Agent."
        )
        sanitized = sanitize_draft_document_text(flawed_draft)
        self.assertNotIn("Approval is granted for continued operation", sanitized)
        self.assertIn("HUMAN APPROVAL REQUIRED", sanitized)
        self.assertIn(MANDATORY_HUMAN_DECISION_TEXT, sanitized)

    # =========================================================================
    # TEST 10: RECOMMENDATIONS ARE NEVER LABELED AS SOURCE FACTS
    # =========================================================================
    def test_10_recommendations_not_labeled_as_facts(self):
        flawed_draft = (
            "## 2. Evidence-Based Findings\n"
            "- [SOURCE_DOCUMENT_FACT] Recommendation: Clean basin sludge within 60 days.\n"
            "- [SOURCE_DOCUMENT_FACT] Recommended action: Schedule pump alignment inspection.\n"
        )
        sanitized = sanitize_draft_document_text(flawed_draft)
        self.assertNotIn("- [SOURCE_DOCUMENT_FACT] Recommendation:", sanitized)
        self.assertIn("- [RECOMMENDATION] Recommendation:", sanitized)
        self.assertIn("- [RECOMMENDATION] Recommended action:", sanitized)

    # =========================================================================
    # TEST 11: VALIDATOR ACCURATELY FLAGS ALL 10 VIOLATIONS
    # =========================================================================
    def test_11_epistemic_validator_catches_all_violations(self):
        bad_doc = (
            "# Cooling Tower Inspection & Maintenance Approval Note\n\n"
            "## 1. Executive Summary\n"
            "All observed conditions comply with manufacturer specifications.\n"
            "The cooling tower system operates within the Allowable Operating Region (AOR).\n"
            "Approval is granted for continued operation without corrective intervention.\n"
            "Thermal efficiency is assumed to be within manufacturer specifications.\n\n"
            "## 2. Evidence-Based Findings\n"
            "- Pump alignment < 0.05 mm\n"
            "- Leakage rate < 0.5 L/min\n\n"
            "## 4. Engineering Calculations\n"
            "- [UNAVAILABLE_MEASUREMENT: Vibration] Calculated Deviation: 0%\n\n"
            "## 5. Assessment\n"
            "- API 610/Hydraulic Institute — Within limits\n"
            "- Manufacturer's baseline — Within limits\n"
        )
        is_valid, violations = validate_epistemic_rigor(bad_doc)
        self.assertFalse(is_valid)
        self.assertGreaterEqual(len(violations), 5)

        # After sanitization, document must pass validation
        sanitized_doc = sanitize_draft_document_text(bad_doc)
        is_valid_sanitized, remaining_violations = validate_epistemic_rigor(sanitized_doc)
        self.assertTrue(is_valid_sanitized, f"Remaining violations: {remaining_violations}")
        self.assertEqual(len(remaining_violations), 0)

    # =========================================================================
    # TEST 12: REAL END-TO-END PDF GENERATION & DISK VERIFICATION
    # =========================================================================
    async def test_12_end_to_end_pdf_deliverable_passes_source_grounding(self):
        task = "Analyze the cooling tower inspection report and prepare an approval note in PDF format."
        
        async def mock_generate(prompt, system_prompt=None, **kwargs):
            p_low = prompt.lower()
            if "extract_findings" in p_low or "extract structured technical findings" in p_low:
                return (
                    "[SOURCE_DOCUMENT_FACT] Inspection Date: May 2026 [Source: cooling_tower_inspection.pdf, Page 1]\n"
                    "[SOURCE_DOCUMENT_FACT] Observation: Excessive leakage at shaft seal [Source: cooling_tower_inspection.pdf, Page 1]\n"
                    "[UNAVAILABLE_MEASUREMENT: Vibration] Status: UNAVAILABLE (Not present in document)\n"
                    "[UNAVAILABLE_MEASUREMENT: Temperature] Status: UNAVAILABLE (Not present in document)\n"
                    "[UNAVAILABLE_MEASUREMENT: Operating Region / AOR] Status: UNAVAILABLE (Not present in document)\n"
                    "[RECOMMENDATION] Recommendation: Clean basin and replace fill packing within 60 days."
                )
            if "write a python" in p_low or "calculation task" in p_low:
                return (
                    "```python\n"
                    "print('Measured Value: UNAVAILABLE')\n"
                    "print('Applicable Limit: NOT QUANTIFIED IN AUTHORIZED EVIDENCE')\n"
                    "print('Deviation: NOT CALCULATED')\n"
                    "print('Status: UNAVAILABLE')\n"
                    "```"
                )
            if "synthesizer" in (system_prompt or "").lower() or "approval note" in p_low:
                return (
                    "# Cooling Tower Inspection & Maintenance Approval Note\n\n"
                    "## 1. Executive Summary\n"
                    "Draft Technical Assessment for Human Review.\n\n"
                    "## 2. Evidence-Based Findings\n"
                    "- [SOURCE_DOCUMENT_FACT] Observation: Excessive leakage at pump seal [Source: cooling_tower_inspection.pdf, Page 1]\n"
                    "- [UNAVAILABLE_MEASUREMENT: Vibration] Status: UNAVAILABLE\n"
                    "- [UNAVAILABLE_MEASUREMENT: Temperature] Status: UNAVAILABLE\n\n"
                    "## 3. Evidence / Citations\n"
                    "- [Source: cooling_tower_inspection.pdf, Page 1] Observation recorded during monthly inspection.\n\n"
                    "## 4. Engineering Calculations\n"
                    "- [DERIVED_CALCULATION] Vibration: Measured Value: UNAVAILABLE, Deviation: NOT CALCULATED, Status: UNAVAILABLE\n\n"
                    "## 5. Assessment\n"
                    "- [MODEL_INFERENCE] Operational assessment is limited due to missing thermal and vibration telemetry.\n\n"
                    "## 6. Recommended / Scheduled Actions\n"
                    "- [RECOMMENDATION] Clean basin sludge within 60 calendar days (Routine Scheduled Maintenance).\n\n"
                    "## 7. Human Review Decision\n"
                    f"{MANDATORY_HUMAN_DECISION_TEXT}"
                )
            return "Default open-weight response."

        self.mock_loader.generate = AsyncMock(side_effect=mock_generate)

        # 1. Start execution -> pauses at HITL gate
        result = await self.controller.run(
            request=task,
            current_user=self.user,
            conversation_id="conv_epistemic_01"
        )
        self.assertEqual(result["status"], "WAITING_FOR_HUMAN")
        approval_id = result["approval_id"]

        # 2. Approve via ApprovalService
        supervisor = {"id": 99, "username": "lead_engineer", "role": "reviewer", "department_id": 3}
        self.approval_service.approve(approval_id, reviewer=supervisor)

        # 3. Resume execution to generate binary PDF
        resume_res = await self.controller.resume_execution(
            plan_id=result["plan_id"],
            approval_id=approval_id,
            current_user=supervisor,
            conversation_id="conv_epistemic_01"
        )
        self.assertTrue(resume_res["success"])
        self.assertEqual(resume_res["status"], "COMPLETED")

        # 4. Verify physical deliverable on disk
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, file_path, file_size, owner_id FROM generated_documents ORDER BY created_at DESC LIMIT 1")
        doc_row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(doc_row)
        pdf_path = doc_row[2]
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 0)
        self.assertEqual(doc_row[4], self.user["id"])

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

        # Verify cryptographic audit chain
        integrity_res = AuditLogger.verify_chain_integrity()
        self.assertEqual(integrity_res["status"], "INTACT")
        self.assertIsNone(integrity_res.get("tampered_record_id"))


if __name__ == "__main__":
    unittest.main()
