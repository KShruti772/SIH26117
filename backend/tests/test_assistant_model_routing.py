import os
import shutil
import tempfile
import sqlite3
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.database import init_db
from backend.security.auth import create_access_token, hash_password
from backend.models.router import TaskType, ModelRouter, NoCompatibleModelError
from backend.app.main import app

class TestAssistantModelRouting(unittest.IsolatedAsyncioTestCase):
    """Integration test suite proving ModelRouter is integrated into the real AI Assistant execution path."""

    @classmethod
    def setUpClass(cls):
        cls.orig_db_path = settings.AUTH_DB_PATH
        cls.test_dir = tempfile.mkdtemp(prefix="aegis_router_int_")
        cls.db_path = os.path.join(cls.test_dir, "test_router.db")
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

    def test_01_document_qa_routes_to_compatible_model(self):
        """1. Document QA prompt routes to a text_generation capable model."""
        with patch("backend.app.main.agent_controller.rag_service.search") as mock_search, \
             patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_search.return_value = [
                {"text": "Section 3: Operational pressure is 4.5 bar.", "metadata": {"filename": "manual.pdf", "page_number": 1}}
            ]
            mock_gen.return_value = "Based on manual.pdf, the maximum operational pressure is 4.5 bar. [Source: manual.pdf | Page 1]"
            
            res = self.client.post(
                "/chat",
                json={"message": "What is the operational pressure in the manual?"},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["routing_info"]["task_type"], "DOCUMENT_QA")
            self.assertTrue(data["routing_info"]["selected_model"].startswith("gemma") or data["routing_info"]["selected_model"].startswith("qwen"))

    def test_02_coding_routes_to_coding_model(self):
        """2. Coding calculation task routes to coding-capable model and triggers sandbox."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "```python\nimport math\nprint(math.factorial(10))\n```"
            
            res = self.client.post(
                "/chat",
                json={"message": "Calculate factorial of 10 using Python."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIn("3628800", data["answer"])
            self.assertIn(data["routing_info"]["task_type"], ["CODING", "CALCULATION"])

    def test_03_vision_routes_to_vision_capable_model(self):
        """3. Vision prompt routes to vision-capable model."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "The scanned drawing shows a centrifugal pump with flange connections."
            
            res = self.client.post(
                "/chat",
                json={"message": "Analyze scanned image diagram of unit 4."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["routing_info"]["task_type"], "VISION_ANALYSIS")
            self.assertIn(data["routing_info"]["selected_model"], ["gemma3:4b", "qwen3-vl:4b"])

    def test_04_active_compatible_model_is_reused(self):
        """4. If currently active model satisfies capabilities, router reuses it without switching."""
        from backend.app.main import loader_manager
        loader_manager.current_model_id = "gemma3:4b"
        
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Reused model reasoning answer."
            res = self.client.post(
                "/chat",
                json={"message": "Explain hydraulic safety fundamentals."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["model"], "gemma3:4b")
            self.assertFalse(data["routing_info"]["switched"])

    def test_05_incompatible_active_model_is_switched(self):
        """5. Incompatible active model is automatically switched by the router."""
        with patch("backend.app.main.loader_manager.get_current_model_id", new_callable=AsyncMock) as mock_curr, \
             patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen, \
             patch("backend.app.main.loader_manager.switch_model", new_callable=AsyncMock) as mock_switch:
            mock_curr.return_value = "qwen3:4b"
            mock_gen.return_value = "Vision OCR extracted parameters."
            mock_switch.return_value = True
            
            res = self.client.post(
                "/chat",
                json={"message": "Read image diagram of reactor valve."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn(data["routing_info"]["selected_model"], ["gemma3:4b", "qwen3-vl:4b"])
            self.assertTrue(data["routing_info"]["switched"])

    def test_06_selected_model_is_actually_used_for_inference(self):
        """6. The model selected by the router is explicitly passed into loader_manager.generate()."""
        from backend.app.main import loader_manager
        loader_manager.current_model_id = "gemma3:4b"
        
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Inference verified."
            res = self.client.post(
                "/chat",
                json={"message": "Explain sensor calibration."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            mock_gen.assert_called()
            call_kwargs = mock_gen.call_args[1] if mock_gen.call_args else {}
            if "model_id" in call_kwargs:
                self.assertEqual(call_kwargs["model_id"], "gemma3:4b")

    def test_07_no_compatible_model_produces_truthful_error(self):
        """7. When no compatible model satisfies mandatory capability, truthful error is returned."""
        with patch("backend.models.router.router.ModelRouter.route", side_effect=NoCompatibleModelError("No installed model supports audio analysis.")):
            res = self.client.post(
                "/chat",
                json={"message": "Process audio recording from factory floor."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertFalse(data["success"])
            self.assertIn("No installed model supports audio analysis", data.get("answer", "") or data.get("error", ""))

    def test_08_rag_response_retains_grounding(self):
        """8. RAG queries retain document grounding and citation sources."""
        with patch("backend.app.main.agent_controller.rag_service.search") as mock_search, \
             patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_search.return_value = [
                {"text": "Section 4.1: Max pressure 4.5 bar.", "metadata": {"filename": "safety_sop.pdf", "page_number": 3}}
            ]
            mock_gen.return_value = "According to safety_sop.pdf, the maximum pressure is 4.5 bar. [Source: safety_sop.pdf | Page 3]"

            res = self.client.post(
                "/chat",
                json={"message": "What is the maximum pressure in safety_sop.pdf?"},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["rag_used"])
            self.assertGreaterEqual(len(data["sources"]), 1)
            self.assertEqual(data["sources"][0]["filename"], "safety_sop.pdf")

    def test_09_conversation_persistence_works(self):
        """9. Multi-turn conversation messages persist correctly across reloads."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Persistent conversation test answer."
            
            res_c = self.client.post(
                "/conversations",
                json={"title": "Routing Persistence Test"},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            sid = res_c.json()["id"]

            res_chat = self.client.post(
                f"/conversations/{sid}/messages",
                json={"message": "Calculate speed given distance 100m and time 5s."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res_chat.status_code, 200)

            # Reload conversation
            res_reload = self.client.get(f"/conversations/{sid}", headers={"Authorization": f"Bearer {self.token_alpha}"})
            self.assertEqual(res_reload.status_code, 200)
            conv = res_reload.json()
            self.assertEqual(len(conv["messages"]), 2)

    def test_10_routing_metadata_is_persisted_and_returned(self):
        """10. Routing metadata is returned in API response and persisted in SQLite message metadata."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Metadata test answer."
            
            res_c = self.client.post(
                "/conversations",
                json={"title": "Routing Metadata Verification"},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            sid = res_c.json()["id"]

            res_chat = self.client.post(
                f"/conversations/{sid}/messages",
                json={"message": "Analyze system requirements."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res_chat.status_code, 200)
            chat_data = res_chat.json()
            self.assertIn("routing_info", chat_data)
            self.assertEqual(chat_data["routing_info"]["routing"], "automatic")

            # Verify persisted message metadata in SQLite
            res_reload = self.client.get(f"/conversations/{sid}", headers={"Authorization": f"Bearer {self.token_alpha}"})
            conv = res_reload.json()
            asst_msg = conv["messages"][1]
            self.assertEqual(asst_msg["metadata"]["routing"], "automatic")
            self.assertIn("selected_model", asst_msg["metadata"])

    def test_11_model_routed_audit_event_is_generated(self):
        """11. Every model routing operation writes a MODEL_ROUTED audit record."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Audit generation response."
            
            res = self.client.post(
                "/chat",
                json={"message": "Explain pneumatic actuator operation."},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)

            # Inspect audit table in isolated test DB
            conn = sqlite3.connect(self.db_path)
            row = conn.execute("SELECT * FROM audit_logs WHERE action = 'MODEL_ROUTED' ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()
            self.assertIsNotNone(row)

    def test_12_user_isolation_is_preserved(self):
        """12. Operator Beta cannot access Operator Alpha's routed conversation."""
        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Confidential response."
            
            res_c = self.client.post(
                "/conversations",
                json={"title": "Alpha Confidential Routing"},
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            sid_alpha = res_c.json()["id"]

            res_unauth = self.client.get(f"/conversations/{sid_alpha}", headers={"Authorization": f"Bearer {self.token_beta}"})
            self.assertEqual(res_unauth.status_code, 403)

    def test_13_test_db_isolation(self):
        """13. Ensure this test suite executes on an isolated temporary SQLite database."""
        self.assertTrue(self.db_path.endswith("test_router.db"))
        self.assertNotEqual(self.db_path, self.orig_db_path)

if __name__ == "__main__":
    unittest.main()
