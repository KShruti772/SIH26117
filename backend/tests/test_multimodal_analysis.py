import os
import io
import time
import shutil
import tempfile
import sqlite3
import base64
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from PIL import Image
import fitz
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.database import init_db
from backend.security.auth import create_access_token, hash_password
from backend.models.router import TaskType, ModelRouter
from backend.app.main import app, rag_service, loader_manager, grounded_qa_service

class TestMultimodalAnalysis(unittest.IsolatedAsyncioTestCase):
    """Test suite proving real multimodal image and visual PDF analysis in AEGIS."""

    @classmethod
    def setUpClass(cls):
        cls.orig_db_path = settings.AUTH_DB_PATH
        cls.test_dir = tempfile.mkdtemp(prefix="aegis_vision_test_")
        cls.db_path = os.path.join(cls.test_dir, "test_vision.db")
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

        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("admin_operator", hash_password("AdminPass123!"), "admin", 1)
        )
        cls.admin_id = cursor.lastrowid

        conn.commit()
        conn.close()

        cls.token_alpha = create_access_token("operator_alpha", "user")
        cls.token_beta = create_access_token("operator_beta", "user")
        cls.token_admin = create_access_token("admin_operator", "admin")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls.orig_db_path
        init_db()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def _create_dummy_image(self, filename: str = "pump_schematic.png", unique_id: int = 1) -> str:
        """Helper to create a real unique PNG image in the knowledge base directory."""
        from PIL import ImageDraw
        img = Image.new("RGB", (200, 200), color=(unique_id * 25 % 255, unique_id * 35 % 255, 100))
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), f"Unique Image {unique_id} {time.time_ns()}")
        upload_dir = os.path.abspath("data/knowledge_base")
        os.makedirs(upload_dir, exist_ok=True)
        img_path = os.path.join(upload_dir, f"test_{int(time.time()*1000)}_{unique_id}_{filename}")
        img.save(img_path, format="PNG")
        return img_path

    def _create_dummy_pdf(self, filename: str = "inspection_report.pdf", unique_id: int = 1) -> str:
        """Helper to create a real unique 2-page PDF document."""
        doc = fitz.open()
        page1 = doc.new_page(width=300, height=300)
        page1.insert_text((50, 50), f"Inspection Report {unique_id} Page 1: Valve Assembly {time.time_ns()}", fontsize=12)
        page2 = doc.new_page(width=300, height=300)
        page2.insert_text((50, 50), f"Inspection Report {unique_id} Page 2: Defect Diagram {time.time_ns()}", fontsize=12)
        
        upload_dir = os.path.abspath("data/knowledge_base")
        os.makedirs(upload_dir, exist_ok=True)
        pdf_path = os.path.join(upload_dir, f"test_{int(time.time()*1000)}_{unique_id}_{filename}")
        doc.save(pdf_path)
        doc.close()
        return pdf_path

    def test_01_image_analysis_passes_image_bytes_to_vision_model(self):
        """1. Ingests a PNG image, queries visual analysis, and verifies real image bytes reach the vision model."""
        img_path = self._create_dummy_image("pump_schematic.png", unique_id=1)
        doc_id = rag_service.ingest_document(
            img_path,
            original_filename="pump_schematic.png",
            owner_id=self.user_alpha_id,
            owner_username="operator_alpha"
        )

        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = (
                "The image depicts a centrifugal pump schematic with inlet flange, impeller housing, "
                "and discharge nozzle. No cracks or abnormalities are visible. [Source: pump_schematic.png]"
            )

            res = self.client.post(
                "/documents/ask",
                json={
                    "query": "Analyze this image. Identify the major components, labels, connections, and any visible abnormalities. Do not infer information that cannot be seen.",
                    "document_id": doc_id,
                    "session_id": "sess_vision_01"
                },
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )

            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["grounded"])
            self.assertEqual(data["task_type"], "VISION_ANALYSIS")
            self.assertIn("pump schematic", data["answer"])
            self.assertEqual(len(data["sources"]), 1)
            self.assertEqual(data["sources"][0]["filename"], "pump_schematic.png")

            # Verify loader_manager.generate received base64 image bytes
            mock_gen.assert_called_once()
            call_kwargs = mock_gen.call_args.kwargs
            self.assertIn("images", call_kwargs)
            self.assertIsInstance(call_kwargs["images"], list)
            self.assertEqual(len(call_kwargs["images"]), 1)
            # Verify it's valid base64
            img_decoded = base64.b64decode(call_kwargs["images"][0])
            self.assertTrue(img_decoded.startswith(b"\x89PNG"))

    def test_02_image_analysis_triggers_auto_switch_from_non_vision_model(self):
        """2. When active model lacks vision (e.g. qwen3:4b), ModelRouter auto-switches to vision-capable model."""
        img_path = self._create_dummy_image("valve_diagram.png", unique_id=2)
        doc_id = rag_service.ingest_document(
            img_path,
            original_filename="valve_diagram.png",
            owner_id=self.user_alpha_id,
            owner_username="operator_alpha"
        )

        # Set active model to qwen3:4b (text-only)
        loader_manager.current_model_id = "qwen3:4b"

        with patch("backend.models.loaders.manager.ModelLoaderManager.switch_model", new_callable=AsyncMock) as mock_switch, \
             patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_switch.return_value = {"model_id": "gemma3:4b", "runtime_model_name": "gemma3:4b", "switched": True}
            mock_gen.return_value = "Visual analysis shows a high-pressure gate valve. [Source: valve_diagram.png]"

            res = self.client.post(
                "/documents/ask",
                json={
                    "query": "Describe the engineering components in this image.",
                    "document_id": doc_id,
                    "session_id": "sess_vision_02"
                },
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )

            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["grounded"])
            self.assertEqual(data["task_type"], "VISION_ANALYSIS")
            self.assertEqual(data["routing_info"]["selected_model"], "gemma3:4b")

    def test_03_pdf_diagram_page_rendering_for_visual_analysis(self):
        """3. Ingests a multi-page PDF, requests visual analysis of page 2, and verifies page rendering to PNG."""
        pdf_path = self._create_dummy_pdf("inspection_report.pdf", unique_id=3)
        doc_id = rag_service.ingest_document(
            pdf_path,
            original_filename="inspection_report.pdf",
            owner_id=self.user_alpha_id,
            owner_username="operator_alpha"
        )

        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Page 2 diagram displays an isolated defect area. [Source: inspection_report.pdf | Page 2]"

            res = self.client.post(
                "/documents/ask",
                json={
                    "query": "Analyze the diagram on page 2 of this inspection report and describe visible defects.",
                    "document_id": doc_id,
                    "session_id": "sess_vision_03"
                },
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )

            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["grounded"])
            self.assertEqual(data["task_type"], "VISION_ANALYSIS")
            self.assertIn("inspection_report.pdf | Page 2", data["answer"])

            # Verify rendered page was passed as base64 PNG
            mock_gen.assert_called_once()
            call_kwargs = mock_gen.call_args.kwargs
            self.assertIn("images", call_kwargs)
            self.assertEqual(len(call_kwargs["images"]), 1)
            img_decoded = base64.b64decode(call_kwargs["images"][0])
            self.assertTrue(img_decoded.startswith(b"\x89PNG"))

    def test_04_multimodal_conversation_persistence(self):
        """4. Verifies multimodal vision exchanges are persisted with task_type, document_id, model, and sources."""
        img_path = self._create_dummy_image("turbine_blade.png", unique_id=4)
        doc_id = rag_service.ingest_document(
            img_path,
            original_filename="turbine_blade.png",
            owner_id=self.user_alpha_id,
            owner_username="operator_alpha"
        )

        session_id = f"sess_persisted_{int(time.time()*1000)}"

        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "The turbine blade shows minor surface oxidation at the leading edge. [Source: turbine_blade.png]"

            res = self.client.post(
                "/documents/ask",
                json={
                    "query": "Analyze this image for thermal stress or erosion.",
                    "document_id": doc_id,
                    "session_id": session_id
                },
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )
            self.assertEqual(res.status_code, 200)

        # Retrieve messages for this session
        res_msgs = self.client.get(
            f"/conversations/{session_id}/messages",
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        self.assertEqual(res_msgs.status_code, 200)
        msgs = res_msgs.json()
        self.assertEqual(len(msgs), 2)
        
        user_msg = msgs[0]
        asst_msg = msgs[1]
        self.assertEqual(user_msg["role"], "user")
        self.assertEqual(asst_msg["role"], "assistant")
        self.assertEqual(asst_msg["task_type"], "VISION_ANALYSIS")
        self.assertEqual(asst_msg["document_id"], doc_id)
        self.assertEqual(asst_msg["verification"], "VERIFIED")

    def test_05_secure_document_preview_and_isolation(self):
        """5. Secure document preview endpoint streams images to owner and admin, but blocks unauthorized users."""
        img_path = self._create_dummy_image("confidential_blueprint.png", unique_id=5)
        doc_id = rag_service.ingest_document(
            img_path,
            original_filename="confidential_blueprint.png",
            owner_id=self.user_alpha_id,
            owner_username="operator_alpha"
        )

        # Operator Alpha (owner) can preview
        res_alpha = self.client.get(
            f"/documents/{doc_id}/preview",
            headers={"Authorization": f"Bearer {self.token_alpha}"}
        )
        self.assertEqual(res_alpha.status_code, 200)
        self.assertEqual(res_alpha.headers["content-type"], "image/png")
        self.assertTrue(res_alpha.content.startswith(b"\x89PNG"))

        # Operator Beta (unauthorized) is blocked with 403
        res_beta = self.client.get(
            f"/documents/{doc_id}/preview",
            headers={"Authorization": f"Bearer {self.token_beta}"}
        )
        self.assertEqual(res_beta.status_code, 403)

        # Admin can preview
        res_admin = self.client.get(
            f"/documents/{doc_id}/preview",
            headers={"Authorization": f"Bearer {self.token_admin}"}
        )
        self.assertEqual(res_admin.status_code, 200)
        self.assertEqual(res_admin.headers["content-type"], "image/png")

    def test_06_digital_text_pdf_uses_standard_document_qa(self):
        """6. Digital PDF without visual keywords uses standard DOCUMENT_QA text RAG retrieval."""
        pdf_path = self._create_dummy_pdf("standard_sop.pdf", unique_id=6)
        doc_id = rag_service.ingest_document(
            pdf_path,
            original_filename="standard_sop.pdf",
            owner_id=self.user_alpha_id,
            owner_username="operator_alpha"
        )

        with patch("backend.app.main.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "The valve assembly protocol is specified on page 1. [Source: standard_sop.pdf | Page 1]"

            res = self.client.post(
                "/documents/ask",
                json={
                    "query": "What is the procedure mentioned in the document?",
                    "document_id": doc_id,
                    "session_id": "sess_text_qa_01"
                },
                headers={"Authorization": f"Bearer {self.token_alpha}"}
            )

            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["grounded"])
            self.assertEqual(data["task_type"], "DOCUMENT_QA")
            # Verify images were NOT sent for standard text QA
            call_kwargs = mock_gen.call_args.kwargs
            self.assertNotIn("images", call_kwargs)
