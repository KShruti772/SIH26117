import os
import sys
import shutil
import tempfile
import sqlite3
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.agents.context_manager import ContextManager
from backend.agents.controller.agent import AgentController
from backend.agents.conversations import ConversationManager
from backend.security.database import init_db, get_db_path
from backend.security.auth import hash_password
from backend.models.router import ModelRouter, RoutingDecision
from backend.tools.code_sandbox.sandbox import SubprocessSandbox
from backend.tools.document_generators.generators import DocxGenerator, PdfGenerator, XlsxGenerator


class TestTruthfulExecutionScenarios(unittest.IsolatedAsyncioTestCase):
    """
    End-to-End Acceptance Test Suite validating truthful agent execution,
    real sandbox invocation, workspace file creation, multi-domain docgen,
    multi-turn persistent context resolution, and RBAC isolation.
    """

    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aegis_scenarios_")
        self.db_path = os.path.join(self.test_dir, "auth_scenarios.db")
        self.exports_dir = os.path.join(self.test_dir, "exports")
        os.makedirs(self.exports_dir, exist_ok=True)

        self.patcher_db = patch("backend.security.database.get_db_path", return_value=self.db_path)
        self.patcher_db.start()

        self.patcher_settings = patch("backend.app.config.settings.settings.AUTH_DB_PATH", self.db_path)
        self.patcher_settings.start()

        init_db()

        # Provision users
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                       ("operator_a", hash_password("PassA123!"), "user", 1))
        self.user_a_id = cursor.lastrowid
        cursor.execute("INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                       ("operator_b", hash_password("PassB123!"), "user", 1))
        self.user_b_id = cursor.lastrowid
        cursor.execute("INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                       ("admin_user", hash_password("AdminPass123!"), "admin", 1))
        self.admin_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.user_a = {"id": self.user_a_id, "username": "operator_a", "role": "user"}
        self.user_b = {"id": self.user_b_id, "username": "operator_b", "role": "user"}
        self.admin = {"id": self.admin_id, "username": "admin_user", "role": "admin"}

        # Real Sandbox Service in isolated test directory
        self.sandbox = SubprocessSandbox(
            workspace_parent=os.path.join(self.test_dir, "sandbox_runs"),
            artifacts_storage=os.path.join(self.test_dir, "sandbox_artifacts")
        )

        # Real Document Generators in isolated directory
        self.doc_generators = {
            "docx": DocxGenerator(output_base_dir=self.exports_dir),
            "pdf": PdfGenerator(output_base_dir=self.exports_dir),
            "xlsx": XlsxGenerator(output_base_dir=self.exports_dir)
        }

        # Mock Model Registry & Loader
        self.mock_registry = MagicMock()
        mock_profile = MagicMock()
        mock_profile.context_length = 32768
        self.mock_registry.get_model.return_value = mock_profile

        self.mock_loader = MagicMock()
        self.mock_loader.current_model_id = "gemma3:4b"
        self.mock_loader.generate = AsyncMock(side_effect=self._mock_model_generate)

        self.mock_router = MagicMock()
        self.mock_router.route = AsyncMock(side_effect=self._mock_router_route)

        self.mock_rag = MagicMock()
        self.mock_rag.list_documents.return_value = [
            {"id": "doc_turbine", "filename": "turbine_spec.pdf", "owner_id": self.user_a["id"]}
        ]
        self.mock_rag.get_document.return_value = {"id": "doc_turbine", "filename": "turbine_spec.pdf", "owner_id": self.user_a["id"]}
        self.mock_rag.search.return_value = [
            {"text": "Turbine RPM limit is 3600 RPM under continuous load.", "metadata": {"filename": "turbine_spec.pdf", "page_number": 2}, "distance": 0.05, "similarity": 0.98}
        ]

        self.context_manager = ContextManager(
            registry_manager=self.mock_registry,
            rag_service=self.mock_rag,
            default_context_budget=16384,
            max_messages_window=10
        )

        self.controller = AgentController(
            registry_manager=self.mock_registry,
            loader_manager=self.mock_loader,
            model_router=self.mock_router,
            sandbox_service=self.sandbox,
            rag_service=self.mock_rag,
            doc_generators=self.doc_generators,
            context_manager=self.context_manager,
            max_steps=10,
            max_replans=3
        )

    async def _mock_model_generate(self, prompt, **kwargs):
        p_lower = prompt.lower()
        if "factorial" in p_lower:
            return "```python\nimport math\nprint(math.factorial(20))\n```"
        elif "fibonacci" in p_lower:
            return "```python\ndef fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)\nprint([fib(i) for i in range(8)])\n```"
        elif "binary search" in p_lower:
            return "```python\ndef binary_search(arr, x):\n    l, r = 0, len(arr) - 1\n    while l <= r:\n        m = (l + r) // 2\n        if arr[m] == x: return m\n        elif arr[m] < x: l = m + 1\n        else: r = m - 1\n    return -1\n```"
        elif "report" in p_lower or "compliance" in p_lower or "summary" in p_lower:
            return (
                "# Industrial Compliance Report\n\n"
                "## Executive Summary\n"
                "All operational parameters for Zone A turbines are within designated safety envelopes.\n\n"
                "## Key Findings\n"
                "- Maximum operating pressure: 4.5 bar\n"
                "- Turbine speed limit: 3600 RPM\n\n"
                "## Recommendations\n"
                "1. Schedule periodic lubrication checks.\n"
                "2. Maintain sensor calibration logs.\n"
            )
        return "Standard technical response."

    async def _mock_router_route(self, required_capabilities, prompt=None, **kwargs):
        req = required_capabilities or ["text_generation"]
        if "coding" in req:
            return RoutingDecision(
                selected_model="qwen2.5-coder:7b",
                runtime_model_name="qwen2.5-coder:7b",
                required_capabilities=req,
                matched_capabilities=req,
                task_type="CODING",
                switched=False,
                reason="Coding model selected"
            )
        return RoutingDecision(
            selected_model="gemma3:4b",
            runtime_model_name="gemma3:4b",
            required_capabilities=req,
            matched_capabilities=req,
            task_type="GENERAL_TEXT",
            switched=False,
            reason="General language model selected"
        )

    async def asyncTearDown(self):
        self.patcher_db.stop()
        self.patcher_settings.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # SCENARIO A: Python Code Generation AND Real Sandbox Execution
    # -------------------------------------------------------------------------
    async def test_scenario_a_code_generation_and_real_sandbox_execution(self):
        """Calculates factorial of 20, executes in real sandbox, captures 2432902008176640000 and persists execution record."""
        conv = ConversationManager.create_conversation(title="Factorial 20", user_id=self.user_a["id"], username=self.user_a["username"])
        sid = conv["id"]

        req = "Write a Python program to calculate factorial of 20, execute it in the sandbox, and show the actual output."
        res = await self.controller.run(req, current_user=self.user_a, conversation_id=sid)

        self.assertTrue(res["success"])
        self.assertIn("2432902008176640000", res["answer"])
        self.assertIsNotNone(res["sandbox_execution"])
        self.assertEqual(res["sandbox_execution"]["exit_code"], 0)
        self.assertIn("2432902008176640000", res["sandbox_execution"]["stdout"])
        self.assertGreater(res["sandbox_execution"]["duration_ms"], 0)

        # Verify DB execution record
        execs = self.sandbox.list_executions(user_id=self.user_a["id"], is_admin=False)
        self.assertGreaterEqual(len(execs), 1)
        latest = execs[0]
        self.assertEqual(latest["exit_code"], 0)
        self.assertIn("2432902008176640000", latest["stdout"])
        self.assertEqual(latest["username"], "operator_a")

    # -------------------------------------------------------------------------
    # SCENARIO B: Named File Creation in Sandbox Artifacts Workspace
    # -------------------------------------------------------------------------
    async def test_scenario_b_named_python_file_creation(self):
        """Creates a named file 'factorial.py', writes code, and records file in sandbox_artifacts."""
        conv = ConversationManager.create_conversation(title="File Creation", user_id=self.user_a["id"], username=self.user_a["username"])
        sid = conv["id"]

        req = "Create a python file named factorial.py to compute factorial of 20 without executing."
        res = await self.controller.run(req, current_user=self.user_a, conversation_id=sid)

        self.assertTrue(res["success"])
        self.assertEqual(res["category"], "CATEGORY_FILE_CREATE")
        self.assertIn("factorial.py", res["answer"])

        # Check file in sandbox files API
        files = self.sandbox.list_files(user_id=self.user_a["id"], is_admin=False)
        self.assertTrue(any(f["filename"] == "factorial.py" for f in files))
        fact_file = next(f for f in files if f["filename"] == "factorial.py")
        self.assertGreater(fact_file["lines_count"], 0)
        self.assertEqual(fact_file["username"], "operator_a")

        # Verify content retrieval
        file_details = self.sandbox.get_file(fact_file["id"], user_id=self.user_a["id"], is_admin=False)
        self.assertIsNotNone(file_details)
        self.assertIn("factorial", file_details["content"])

    # -------------------------------------------------------------------------
    # SCENARIO C: Direct Script Execution in Sandbox (Explicit Code)
    # -------------------------------------------------------------------------
    async def test_scenario_c_direct_explicit_code_execution(self):
        """Submits raw code directly to execute in sandbox."""
        conv = ConversationManager.create_conversation(title="Direct Exec", user_id=self.user_a["id"], username=self.user_a["username"])
        sid = conv["id"]

        raw_script = "```python\nprint(2 ** 16)\n```"
        res = await self.controller.run(raw_script, current_user=self.user_a, conversation_id=sid)

        self.assertTrue(res["success"])
        self.assertIn("65536", res["answer"])
        self.assertEqual(res["sandbox_execution"]["exit_code"], 0)
        self.assertIn("65536", res["sandbox_execution"]["stdout"])

    # -------------------------------------------------------------------------
    # SCENARIO D: Code Generation ONLY (No Sandbox Execution)
    # -------------------------------------------------------------------------
    async def test_scenario_d_code_generation_only(self):
        """Asks for code without executing -> returns code cleanly, sandbox is NOT invoked."""
        conv = ConversationManager.create_conversation(title="Code Display", user_id=self.user_a["id"], username=self.user_a["username"])
        sid = conv["id"]

        req = "Show me Python code for binary search without executing."
        res = await self.controller.run(req, current_user=self.user_a, conversation_id=sid)

        self.assertTrue(res["success"])
        self.assertEqual(res["category"], "CATEGORY_CODE_GEN")
        self.assertIn("def binary_search", res["answer"])
        self.assertIsNone(res["sandbox_execution"])

    # -------------------------------------------------------------------------
    # SCENARIO E: Document Deliverable Generation (DOCX / PDF / XLSX)
    # -------------------------------------------------------------------------
    async def test_scenario_e_document_deliverables_generation(self):
        """Generates real DOCX, PDF, and XLSX documents on disk and persists in generated_documents."""
        conv = ConversationManager.create_conversation(title="DocGen Task", user_id=self.user_a["id"], username=self.user_a["username"])
        sid = conv["id"]

        # 1. DOCX Generation
        req_docx = "Generate a technical safety compliance report in docx format."
        res_docx = await self.controller.run(req_docx, current_user=self.user_a, conversation_id=sid)
        self.assertTrue(res_docx["success"])
        docx_art = res_docx["state"]["generated_artifacts"][0]
        self.assertTrue(docx_art["filename"].endswith(".docx"))
        self.assertTrue(os.path.exists(docx_art["path"]))
        self.assertGreater(os.path.getsize(docx_art["path"]), 0)

        # 2. PDF Generation
        req_pdf = "Generate a technical safety compliance report in pdf format."
        res_pdf = await self.controller.run(req_pdf, current_user=self.user_a, conversation_id=sid)
        self.assertTrue(res_pdf["success"])
        pdf_art = res_pdf["state"]["generated_artifacts"][0]
        self.assertTrue(pdf_art["filename"].endswith(".pdf"))
        self.assertTrue(os.path.exists(pdf_art["path"]))
        self.assertGreater(os.path.getsize(pdf_art["path"]), 0)

        # 3. XLSX Generation
        req_xlsx = "Generate a technical safety compliance report in xlsx spreadsheet format."
        res_xlsx = await self.controller.run(req_xlsx, current_user=self.user_a, conversation_id=sid)
        self.assertTrue(res_xlsx["success"])
        xlsx_art = res_xlsx["state"]["generated_artifacts"][0]
        self.assertTrue(xlsx_art["filename"].endswith(".xlsx"))
        self.assertTrue(os.path.exists(xlsx_art["path"]))
        self.assertGreater(os.path.getsize(xlsx_art["path"]), 0)

    # -------------------------------------------------------------------------
    # SCENARIO F: Multi-Turn Contextual Follow-up
    # -------------------------------------------------------------------------
    async def test_scenario_f_multi_turn_execution_resolution(self):
        """Turn 1 runs factorial -> Turn 2 asks 'What result did you get?' and answers 2432902008176640000 without re-running."""
        conv = ConversationManager.create_conversation(title="Multi-Turn Calc", user_id=self.user_a["id"], username=self.user_a["username"])
        sid = conv["id"]

        # Turn 1
        req_1 = "Calculate factorial of 20 using Python."
        res_1 = await self.controller.run(req_1, current_user=self.user_a, conversation_id=sid)
        self.assertTrue(res_1["success"])

        ConversationManager.add_message(sid, "user", req_1, user_id=self.user_a["id"], username=self.user_a["username"])
        ConversationManager.add_message(
            sid, "assistant", res_1["answer"], user_id=self.user_a["id"], username=self.user_a["username"],
            metadata={"sandbox_execution": res_1["sandbox_execution"]}
        )

        # Turn 2: Follow-up question
        req_2 = "What was the result you got?"
        res_2 = await self.controller.run(req_2, current_user=self.user_a, conversation_id=sid)
        self.assertTrue(res_2["success"])
        self.assertEqual(res_2["category"], "CATEGORY_EXEC_RESULT")
        self.assertIn("2432902008176640000", res_2["answer"])

    # -------------------------------------------------------------------------
    # SCENARIO G: Multi-Turn Format Conversion
    # -------------------------------------------------------------------------
    async def test_scenario_g_multi_turn_docx_to_pdf_conversion(self):
        """Turn 1 generates DOCX report -> Turn 2 converts that report to PDF."""
        conv = ConversationManager.create_conversation(title="Convert Task", user_id=self.user_a["id"], username=self.user_a["username"])
        sid = conv["id"]

        # Turn 1: Generate DOCX
        req_1 = "Generate a technical safety compliance report for zone A in docx format."
        res_1 = await self.controller.run(req_1, current_user=self.user_a, conversation_id=sid)
        self.assertTrue(res_1["success"])

        ConversationManager.add_message(sid, "user", req_1, user_id=self.user_a["id"], username=self.user_a["username"])
        ConversationManager.add_message(sid, "assistant", res_1["answer"], user_id=self.user_a["id"], username=self.user_a["username"])

        # Turn 2: Convert to PDF
        req_2 = "Convert that report to PDF."
        res_2 = await self.controller.run(req_2, current_user=self.user_a, conversation_id=sid)
        self.assertTrue(res_2["success"])
        self.assertEqual(res_2["category"], "CATEGORY_CONVERT")
        pdf_art = res_2["state"]["generated_artifacts"][0]
        self.assertTrue(pdf_art["filename"].endswith(".pdf"))
        self.assertTrue(os.path.exists(pdf_art["path"]))
        self.assertGreater(os.path.getsize(pdf_art["path"]), 0)

    # -------------------------------------------------------------------------
    # SCENARIO H: Multi-Tenant RBAC Isolation on Sandbox Files & Executions
    # -------------------------------------------------------------------------
    async def test_scenario_h_rbac_isolation(self):
        """Operator A's files and execution logs are isolated from Operator B, but visible to Admin."""
        # Operator A creates a file and executes code
        f_record = self.sandbox.create_file("secret_alpha.py", "print('alpha secret')", user_id=self.user_a["id"], username=self.user_a["username"])
        e_record = self.sandbox.execute("print('exec alpha')", user_id=self.user_a["id"], username=self.user_a["username"])

        # Operator B lists files and executions
        b_files = self.sandbox.list_files(user_id=self.user_b["id"], is_admin=False)
        self.assertFalse(any(f["filename"] == "secret_alpha.py" for f in b_files))

        b_execs = self.sandbox.list_executions(user_id=self.user_b["id"], is_admin=False)
        self.assertFalse(any(e["id"] == e_record["execution_id"] for e in b_execs))

        # Operator B direct access to file/exec is blocked
        b_get_file = self.sandbox.get_file(f_record["id"], user_id=self.user_b["id"], is_admin=False)
        self.assertIsNone(b_get_file)

        b_get_exec = self.sandbox.get_execution(e_record["execution_id"], user_id=self.user_b["id"], is_admin=False)
        self.assertIsNone(b_get_exec)

        # Admin has full visibility
        admin_files = self.sandbox.list_files(user_id=self.admin["id"], is_admin=True)
        self.assertTrue(any(f["filename"] == "secret_alpha.py" for f in admin_files))

        admin_execs = self.sandbox.list_executions(user_id=self.admin["id"], is_admin=True)
        self.assertTrue(any(e["id"] == e_record["execution_id"] for e in admin_execs))


if __name__ == "__main__":
    unittest.main()
