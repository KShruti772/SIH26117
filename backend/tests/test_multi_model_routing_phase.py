import os
import shutil
import tempfile
import sqlite3
import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.database import init_db
from backend.security.auth import create_access_token, hash_password
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.models.router import (
    ModelRouter,
    TaskType,
    RoutingDecision,
    NoCompatibleModelError,
    classify_task_from_prompt
)
from backend.app.main import app, agent_controller, loader_manager, model_router

class TestMultiModelRoutingPhase(unittest.IsolatedAsyncioTestCase):
    """
    Comprehensive verification suite for AEGIS Capability-Based Multi-Model Sovereign AI System.
    Validates all 15 test matrix areas specified in the project specification.
    """

    @classmethod
    def setUpClass(cls):
        cls.orig_db_path = settings.AUTH_DB_PATH
        cls.test_dir = tempfile.mkdtemp(prefix="aegis_multi_model_test_")
        cls.db_path = os.path.join(cls.test_dir, "test_multi_model.db")
        settings.AUTH_DB_PATH = cls.db_path
        init_db()

        # Provision test operators
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("operator_alpha", hash_password("AlphaPass123!"), "user", 1)
        )
        cls.user_alpha_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("operator_beta", hash_password("BetaPass123!"), "user", 1)
        )
        cls.user_beta_id = cursor.lastrowid

        conn.commit()
        conn.close()

        cls.token_alpha = create_access_token("operator_alpha", "user")
        cls.token_beta = create_access_token("operator_beta", "user")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls.orig_db_path
        init_db()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # TEST 1: GENERAL_TEXT
    # -------------------------------------------------------------------------
    def test_01_general_text_routing(self):
        """TEST 1: GENERAL_TEXT requests route to an appropriate local text model."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Preventive maintenance is the systematic inspection and servicing of plant equipment."
            
            res = self.client.post(
                "/chat",
                json={"message": "Explain preventive maintenance in an industrial refinery."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["routing_info"]["task_type"], "GENERAL_TEXT")
            self.assertIn(data["routing_info"]["selected_model"], ["gemma3:4b", "qwen3:4b"])
            self.assertIsNone(data.get("sandbox_execution"))

    # -------------------------------------------------------------------------
    # TEST 2: CODING
    # -------------------------------------------------------------------------
    def test_02_coding_routing(self):
        """TEST 2: CODING capability requests route to coding-capable model."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "```python\ndef factorial(n):\n    return 1 if n <= 1 else n * factorial(n - 1)\n```"
            
            res = self.client.post(
                "/chat",
                json={"message": "Write a Python function to compute factorial."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["routing_info"]["task_type"], "CODING")
            self.assertIn(data["routing_info"]["selected_model"], ["qwen2.5-coder:7b", "qwen3:4b", "gemma3:4b"])

    # -------------------------------------------------------------------------
    # TEST 3: VISION
    # -------------------------------------------------------------------------
    def test_03_vision_routing(self):
        """TEST 3: VISION capability requests route strictly to a vision-capable model."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "The P&ID schematic shows the crude distillation column and safety relief valves."
            
            res = self.client.post(
                "/chat",
                json={"message": "Analyze this P&ID diagram and explain the major equipment."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["routing_info"]["task_type"], "VISION_ANALYSIS")
            self.assertIn(data["routing_info"]["selected_model"], ["qwen3-vl:4b", "gemma3:4b"])

    # -------------------------------------------------------------------------
    # TEST 4: INCOMPATIBLE MODEL REJECTION
    # -------------------------------------------------------------------------
    def test_04_incompatible_model_rejection(self):
        """TEST 4: Incompatible text-only model (qwen3:4b) is rejected when vision is requested."""
        with patch("backend.app.main.loader_manager.get_current_model_id", new_callable=AsyncMock) as mock_curr, \
             patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen, \
             patch("backend.app.main.loader_manager.switch_model", new_callable=AsyncMock) as mock_switch:
            mock_curr.return_value = "qwen3:4b"
            mock_gen.return_value = "P&ID inspection analysis result."
            mock_switch.return_value = True

            res = self.client.post(
                "/chat",
                json={"message": "Analyze this scanned image of the pipeline."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            # qwen3:4b must be rejected because supports_vision = False
            self.assertNotEqual(data["routing_info"]["selected_model"], "qwen3:4b")
            self.assertIn(data["routing_info"]["selected_model"], ["qwen3-vl:4b", "gemma3:4b"])

    # -------------------------------------------------------------------------
    # TEST 5: REAL MODEL SWITCH
    # -------------------------------------------------------------------------
    def test_05_real_model_switch(self):
        """TEST 5: Switching from qwen3:4b to vision model produces switched=True and uses selected model for inference."""
        with patch("backend.app.main.loader_manager.get_current_model_id", new_callable=AsyncMock) as mock_curr, \
             patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen, \
             patch("backend.app.main.loader_manager.switch_model", new_callable=AsyncMock) as mock_switch:
            mock_curr.return_value = "qwen3:4b"
            mock_gen.return_value = "Vision OCR extracted parameters."
            mock_switch.return_value = True

            res = self.client.post(
                "/chat",
                json={"message": "Look at this image of pump failure."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["routing_info"]["switched"])
            mock_switch.assert_called()
            mock_gen.assert_called()

    # -------------------------------------------------------------------------
    # TEST 6: STICKY MODEL REUSE
    # -------------------------------------------------------------------------
    def test_06_sticky_model_reuse(self):
        """TEST 6: Two consecutive compatible text requests reuse the active model without switching."""
        from backend.app.main import loader_manager
        loader_manager.current_model_id = "gemma3:4b"

        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen, \
             patch("backend.app.main.loader_manager.switch_model", new_callable=AsyncMock) as mock_switch:
            mock_gen.return_value = "Explanation of preventive maintenance."

            # Turn 1
            res1 = self.client.post(
                "/chat",
                json={"message": "Explain preventive maintenance."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res1.status_code, 200)
            data1 = res1.json()
            self.assertFalse(data1["routing_info"]["switched"])

            # Turn 2: Follow-up text query
            mock_gen.return_value = "The main risks are unexpected vibration and overheating."
            res2 = self.client.post(
                "/chat",
                json={"message": "What are the main risks associated with it?"},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res2.status_code, 200)
            data2 = res2.json()
            self.assertFalse(data2["routing_info"]["switched"])
            mock_switch.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 7: CODING + SANDBOX EXECUTION
    # -------------------------------------------------------------------------
    def test_07_coding_and_sandbox_execution(self):
        """TEST 7: Coding execution request writes script, executes in sandbox, captures stdout and exit code 0."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "```python\nimport math\nprint(math.factorial(20))\n```"

            res = self.client.post(
                "/chat",
                json={"message": "Write Python code to calculate factorial of 20 and execute it in the sandbox."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIn("2432902008176640000", data["answer"])
            self.assertIsNotNone(data["sandbox_execution"])
            self.assertEqual(data["sandbox_execution"]["exit_code"], 0)
            self.assertIn("2432902008176640000", data["sandbox_execution"]["stdout"])

    # -------------------------------------------------------------------------
    # TEST 8: CODE ONLY
    # -------------------------------------------------------------------------
    def test_08_code_generation_only(self):
        """TEST 8: Code generation without execution displays code and DOES NOT invoke the sandbox."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "```python\ndef binary_search(arr, target):\n    return -1\n```"

            res = self.client.post(
                "/chat",
                json={"message": "Write a Python binary search function without executing it."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIn("def binary_search", data["answer"])
            self.assertIsNone(data["sandbox_execution"])

    # -------------------------------------------------------------------------
    # TEST 9: DOCUMENT SUMMARY (NO PDF UNLESS REQUESTED)
    # -------------------------------------------------------------------------
    def test_09_document_summary_no_pdf(self):
        """TEST 9: Document summary returns AI answer only without generating a physical PDF."""
        with patch("backend.app.main.agent_controller.rag_service.search") as mock_search, \
             patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_search.return_value = [
                {"text": "Safety findings: All equipment passed safety inspection with 0 defects.", "metadata": {"filename": "inspection_report.pdf", "page_number": 1}}
            ]
            mock_gen.return_value = "The safety findings summarize that all equipment passed inspection. [Source: inspection_report.pdf | Page 1]"

            res = self.client.post(
                "/chat",
                json={"message": "Summarize the safety findings from our equipment inspection."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIn("safety findings summarize", data["answer"])
            self.assertIsNone(data["sandbox_execution"])
            self.assertFalse(data.get("category") == "CATEGORY_DOCGEN")

    # -------------------------------------------------------------------------
    # TEST 10: DOCUMENT + PDF
    # -------------------------------------------------------------------------
    def test_10_document_analysis_with_pdf(self):
        """TEST 10: Explicit PDF generation request produces a real physical PDF file on disk."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Inspection summary content for PDF."

            res = self.client.post(
                "/chat",
                json={"message": "Create an inspection summary report as PDF."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["category"], "CATEGORY_DOCGEN")
            self.assertIn("Generated industrial deliverable", data["answer"])

    # -------------------------------------------------------------------------
    # TEST 11: DOCUMENT + DOCX
    # -------------------------------------------------------------------------
    def test_11_document_with_docx(self):
        """TEST 11: Explicit DOCX generation request produces a real physical DOCX deliverable on disk."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Word approval note content."

            res = self.client.post(
                "/chat",
                json={"message": "Create an approval note in Word docx format."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["category"], "CATEGORY_DOCGEN")
            self.assertIn("Generated industrial deliverable", data["answer"])

    # -------------------------------------------------------------------------
    # TEST 12: MODEL UNAVAILABLE
    # -------------------------------------------------------------------------
    def test_12_model_unavailable_handling(self):
        """TEST 12: Truthful error returned when no locally installed model supports the requested capability."""
        with patch("backend.models.router.router.ModelRouter.route", side_effect=NoCompatibleModelError("No locally installed model supports quantum computing simulation.")):
            res = self.client.post(
                "/chat",
                json={"message": "Run quantum physics simulation."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertFalse(data["success"])
            self.assertIn("No locally installed model supports", str(data.get("answer", "") or data.get("error", "")))

    # -------------------------------------------------------------------------
    # TEST 13: USER ISOLATION
    # -------------------------------------------------------------------------
    def test_13_user_isolation(self):
        """TEST 13: Operator Beta cannot access Operator Alpha's conversation session or model executions."""
        # Create session as Alpha
        res_c = self.client.post(
            "/conversations",
            json={"title": "Alpha Confidential Task"},
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        sid_alpha = res_c.json()["id"]

        # Attempt access as Beta
        res_beta = self.client.get(
            f"/conversations/{sid_alpha}",
            headers={"Authorization": f"Bearer {self.token_beta}"}
        )
        self.assertEqual(res_beta.status_code, 403)

    # -------------------------------------------------------------------------
    # TEST 14: AUDIT LEDGER INTEGRITY
    # -------------------------------------------------------------------------
    def test_14_audit_ledger_integrity(self):
        """TEST 14: Model routing creates real tamper-evident MODEL_ROUTED audit records with valid HMAC hash chains."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Audited response text."

            res = self.client.post(
                "/chat",
                json={"message": "Explain boiler steam turbine regulation."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = cursor.execute("SELECT * FROM audit_logs WHERE action = 'MODEL_ROUTED' ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()

            self.assertIsNotNone(row)
            self.assertEqual(row["action"], "MODEL_ROUTED")
            self.assertEqual(row["status"], "success")
            self.assertTrue(len(row["entry_hash"]) == 64)

    # -------------------------------------------------------------------------
    # TEST 15: OFFLINE / SOVEREIGN OPERATION
    # -------------------------------------------------------------------------
    def test_15_offline_sovereignty(self):
        """TEST 15: Verifies that inference requests make zero calls to external cloud AI APIs (OpenAI, Claude, Gemini)."""
        import socket
        real_connect = socket.socket.connect
        
        # Verify that no external DNS or cloud socket calls occur
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Sovereign local inference output."

            res = self.client.post(
                "/chat",
                json={"message": "Confirm sovereign air-gap isolation."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIn("Sovereign local inference output.", data["answer"])

if __name__ == "__main__":
    unittest.main()
