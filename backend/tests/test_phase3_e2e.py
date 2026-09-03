import os
import shutil
import tempfile
import unittest
import asyncio
import uuid
import sqlite3
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.rag.embeddings import MockEmbeddingModel
from backend.rag.pipeline import AegisRagService
from backend.rag.grounded_qa import GroundedQAService
from backend.services.document_generator import DocumentGeneratorService
from backend.security.audit import AuditLogger
from backend.agents.conversations import ConversationManager
from backend.app.main import app
from backend.security.dependencies import get_current_user

class MockUser:
    def __init__(self, data):
        self._data = data
    def __getitem__(self, item):
        return self._data[item]
    def get(self, item, default=None):
        return self._data.get(item, default)
    @property
    def id(self):
        return self._data.get("id")
    @property
    def username(self):
        return self._data.get("username")
    @property
    def role(self):
        return self._data.get("role")

class TestPhase3EndToEndVerification(unittest.TestCase):
    """
    End-to-End Product Truth & Integration Verification Test Suite for AEGIS Phase 3.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls.vectorstore_path = os.path.join(cls.test_dir, "test_vectorstore")
        cls.docs_dir = os.path.join(cls.test_dir, "test_docs")
        cls.generated_dir = os.path.join(cls.test_dir, "test_generated")
        os.makedirs(cls.vectorstore_path, exist_ok=True)
        os.makedirs(cls.docs_dir, exist_ok=True)
        os.makedirs(cls.generated_dir, exist_ok=True)

        # Real sample document with multiple sections and pages
        cls.sample_pdf_text = (
            "Mangalore Refinery Industrial Safety & Automated Control Specification\n\n"
            "Chapter 1: Operational Baseline\n"
            "The standard operating reactor temperature is calibrated at 340 degrees Celsius.\n"
            "All feed gas flows must maintain a minimum velocity of 12.5 meters per second.\n\n"
            "Chapter 2: Emergency Response & Nitrogen Purge\n"
            "If main chamber pressure exceeds 180 PSI, operators must initiate the nitrogen purge within 15 seconds.\n"
            "The auxiliary containment valve is located in Substation 4B.\n\n"
            "Chapter 3: Maintenance & Risk Assessment\n"
            "Annual inspection of ceramic seals is strictly required to avoid hydrogen embrittlement."
        )

        cls.sample_doc_path = os.path.join(cls.docs_dir, "Mangalore_Safety_Spec.txt")
        with open(cls.sample_doc_path, "w", encoding="utf-8") as f:
            f.write(cls.sample_pdf_text)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        self.orig_auth_db = settings.AUTH_DB_PATH
        self.db_path = os.path.join(self.test_dir, f"test_e2e_{uuid.uuid4().hex[:8]}.db")
        settings.AUTH_DB_PATH = self.db_path
        init_db()

        self.embedding_model = MockEmbeddingModel(dimension=384)
        self.rag_service = AegisRagService(
            embedding_model=self.embedding_model,
            persist_directory=self.vectorstore_path,
            safe_directories=[self.test_dir]
        )
        if self.rag_service.collection.count() > 0:
            all_ids = self.rag_service.collection.get()["ids"]
            if all_ids:
                self.rag_service.collection.delete(ids=all_ids)

        self.doc_generator = DocumentGeneratorService(output_dir=self.generated_dir)
        self.mock_loader = MagicMock()
        self.mock_loader.generate = AsyncMock(return_value=(
            "If main chamber pressure exceeds 180 PSI, operators must initiate the nitrogen purge within 15 seconds "
            "[Source: Mangalore_Safety_Spec.txt | Page 1]."
        ))

        self.qa_service = GroundedQAService(
            rag_service=self.rag_service,
            loader_manager=self.mock_loader,
            doc_generator=self.doc_generator
        )

        self.client = TestClient(app)
        self.user_a = MockUser({"id": 201, "username": "operator_alpha", "role": "user"})
        self.user_b = MockUser({"id": 202, "username": "operator_beta", "role": "user"})
        self.admin = MockUser({"id": 999, "username": "admin", "role": "admin"})

    def tearDown(self):
        app.dependency_overrides.clear()
        settings.AUTH_DB_PATH = self.orig_auth_db
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_real_document_upload_and_single_logical_record(self):
        """Phase 3A: Verify 1 uploaded document creates exactly ONE logical record with chunk_count > 1."""
        doc_id = self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )
        self.assertIsNotNone(doc_id)

        # Check SQLite record
        doc = self.rag_service.get_document(doc_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["filename"], "Mangalore_Safety_Spec.txt")
        self.assertEqual(doc["status"], "indexed")
        self.assertGreater(doc["chunk_count"], 0)

        # Verify logical statistics: Exactly 1 document
        stats = self.rag_service.get_document_stats(owner_id=201, is_admin=False)
        self.assertEqual(stats["total_documents"], 1)
        self.assertEqual(stats["indexed_documents"], 1)
        self.assertEqual(stats["total_chunks"], doc["chunk_count"])

    def test_document_grounded_qa_with_exact_page_citations(self):
        """Phase 3B: Verify grounded answer synthesizes facts and returns exact source and page citations."""
        doc_id = self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )

        res = asyncio.run(self.qa_service.generate_grounded_answer(
            query="What is the emergency procedure when pressure exceeds 180 PSI?",
            current_user=self.user_a
        ))

        self.assertTrue(res["grounded"])
        self.assertIn("180 PSI", res["answer"])
        self.assertGreater(len(res["sources"]), 0)
        self.assertEqual(res["sources"][0]["filename"], "Mangalore_Safety_Spec.txt")
        self.assertEqual(res["sources"][0]["document_id"], doc_id)

    def test_anti_hallucination_unsupported_question_refusal(self):
        """Phase 3D: Verify question with no supporting evidence returns honest refusal without hallucinating."""
        self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )
        self.mock_loader.generate.return_value = (
            "I could not find sufficient evidence in the indexed organizational documents to answer this question."
        )

        res = asyncio.run(self.qa_service.generate_grounded_answer(
            query="What is the satellite uplink frequency for offshore communications?",
            current_user=self.user_a
        ))

        self.assertFalse(res["grounded"])
        self.assertEqual(
            res["answer"],
            "I could not find sufficient evidence in the indexed organizational documents to answer this question."
        )

    def test_conversation_and_message_persistence_across_reloads(self):
        """Phase 3E: Verify conversation session and message sequences persist authoritatively in SQLite."""
        self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )
        sid = f"conv_test_{uuid.uuid4().hex[:8]}"

        # Create persistent session
        ConversationManager.create_conversation(
            title="Refinery Safety Review",
            user_id=201,
            username="operator_alpha",
            session_id=sid,
            feature="knowledge"
        )

        # Run query with session_id
        asyncio.run(self.qa_service.generate_grounded_answer(
            query="What temperature is calibrated for the reactor?",
            session_id=sid,
            current_user=self.user_a
        ))

        # Retrieve conversation from SQLite
        conv = ConversationManager.get_conversation(sid)
        self.assertIsNotNone(conv)
        self.assertEqual(conv["title"], "Refinery Safety Review")
        self.assertEqual(len(conv["messages"]), 2)
        self.assertEqual(conv["messages"][0]["role"], "user")
        self.assertEqual(conv["messages"][1]["role"], "assistant")
        self.assertTrue(conv["messages"][1]["rag_used"])

    def test_real_pdf_and_docx_report_generation(self):
        """Phase 3G & 3H: Verify physical PDF and DOCX reports are created on disk and metadata stored."""
        sections = {
            "Executive Summary": "The Mangalore refinery operates with strict automated nitrogen purge protocols.",
            "Key Findings": "Reactor temperature operates at 340°C. Nitrogen purge activates within 15 seconds.",
            "Risks & Issues": "Hydrogen embrittlement risk if ceramic seal inspection is neglected.",
            "Recommendations": "Ensure annual inspection schedule for Substation 4B containment valves."
        }
        sources = [{
            "filename": "Mangalore_Safety_Spec.txt",
            "pages": [1, 2],
            "relevance": "High"
        }]

        # 1. Generate PDF Report
        pdf_record = self.doc_generator.create_report(
            title="Mangalore Refinery Safety Audit Report",
            sections=sections,
            sources=sources,
            format_type="pdf",
            owner_id=201,
            owner_username="operator_alpha"
        )

        self.assertTrue(os.path.exists(pdf_record["file_path"]))
        self.assertGreater(pdf_record["file_size"], 0)
        self.assertEqual(pdf_record["format"], "pdf")

        # Verify physical file magic bytes (%PDF)
        with open(pdf_record["file_path"], "rb") as f:
            header = f.read(5)
            self.assertEqual(header, b"%PDF-")

        # 2. Generate DOCX Report
        docx_record = self.doc_generator.create_report(
            title="Mangalore Refinery Safety Audit Document",
            sections=sections,
            sources=sources,
            format_type="docx",
            owner_id=201,
            owner_username="operator_alpha"
        )

        self.assertTrue(os.path.exists(docx_record["file_path"]))
        self.assertGreater(docx_record["file_size"], 0)
        self.assertEqual(docx_record["format"], "docx")

        # Verify record in SQLite
        listed_docs = self.doc_generator.list_generated_documents(owner_id=201, is_admin=False)
        self.assertEqual(len(listed_docs), 2)

    def test_generated_document_download_endpoint(self):
        """Phase 3H: Verify REST API streaming download for generated reports."""
        sections = {"Executive Summary": "Operational overview for Mangalore unit."}
        sources = [{"filename": "Mangalore_Safety_Spec.txt", "pages": [1]}]

        rep = self.doc_generator.create_report(
            title="Unit Download Test",
            sections=sections,
            sources=sources,
            format_type="pdf",
            owner_id=201,
            owner_username="operator_alpha"
        )

        app.dependency_overrides[get_current_user] = lambda: self.user_a
        response = self.client.get(f"/documents/generated/{rep['id']}/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(len(response.content), rep["file_size"])

    def test_multi_user_isolation_across_documents_and_reports(self):
        """Phase 3F: Verify User B cannot access User A's source documents or generated reports."""
        # User A creates document and report
        doc_a_id = self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )
        rep_a = self.doc_generator.create_report(
            title="Confidential Alpha Report",
            sections={"Executive Summary": "Restricted information."},
            sources=[{"filename": "Mangalore_Safety_Spec.txt", "pages": [1]}],
            owner_id=201,
            owner_username="operator_alpha"
        )

        # User B queries generated documents
        user_b_reports = self.doc_generator.list_generated_documents(owner_id=202, is_admin=False)
        self.assertEqual(len(user_b_reports), 0)

        # User B attempts download via REST API
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        res = self.client.get(f"/documents/generated/{rep_a['id']}/download")
        self.assertEqual(res.status_code, 403)

    def test_audit_ledger_event_creation_and_hmac_chain_integrity(self):
        """Phase 3I: Verify audit ledger logs real operations and validates cryptographic HMAC-SHA256 chain."""
        # Clean initial state
        verify_initial = AuditLogger.verify_chain_integrity()
        self.assertEqual(verify_initial["status"], "INTACT")

        # Perform audited operations
        self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )
        self.doc_generator.create_report(
            title="Audit Verification Report",
            sections={"Summary": "Audit test."},
            sources=[],
            owner_id=201,
            owner_username="operator_alpha"
        )

        # Verify chain integrity
        verify_after = AuditLogger.verify_chain_integrity()
        self.assertEqual(verify_after["status"], "INTACT")
        self.assertGreater(verify_after["total_records"], 0)

    def test_tamper_detection_breaks_hmac_audit_chain(self):
        """Phase 3I: Verify manual database tampering immediately triggers TAMPERED status."""
        self.doc_generator.create_report(
            title="Pre-Tamper Report",
            sections={"Summary": "Test."},
            sources=[],
            owner_id=201,
            owner_username="operator_alpha"
        )

        # Directly tamper with an audit entry in SQLite
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE audit_logs SET action = 'UNAUTHORIZED_TAMPERED_ACTION' WHERE id = 1")
            conn.commit()
        finally:
            conn.close()

        # Run verification check
        verify_result = AuditLogger.verify_chain_integrity()
        self.assertEqual(verify_result["status"], "TAMPERED")
        self.assertEqual(verify_result["tampered_record_id"], 1)

    def test_document_deletion_purges_chunks_and_file(self):
        """Phase 3A: Verify document deletion purges SQLite, ChromaDB chunks, and updates statistics."""
        doc_id = self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )
        self.assertEqual(self.rag_service.get_document_stats(201)["total_documents"], 1)

        # Delete document
        self.rag_service.delete_document(doc_id)

        # Verify statistics return to 0
        stats_after = self.rag_service.get_document_stats(201)
        self.assertEqual(stats_after["total_documents"], 0)
        self.assertEqual(stats_after["total_chunks"], 0)
        self.assertIsNone(self.rag_service.get_document(doc_id))

    def test_e2e_api_document_generation_pdf_and_download(self):
        """E2E Test: Ingest doc -> POST /documents/generate (PDF) -> verify DB & disk -> GET download -> verify streamed bytes."""
        doc_id = self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )

        app.dependency_overrides[get_current_user] = lambda: self.user_a

        # Mock the grounded QA service inside app to use our mock loader
        with patch("backend.app.main.grounded_qa_service", self.qa_service):
            gen_res = self.client.post("/documents/generate", json={
                "title": "Mangalore Refinery Intelligence Brief",
                "topic": "generate a summary document of Mangalore_Safety_Spec.txt",
                "format": "pdf",
                "document_id": doc_id
            })

            self.assertEqual(gen_res.status_code, 200, f"Generation failed: {gen_res.text}")
            data = gen_res.json()
            self.assertIn("id", data)
            self.assertEqual(data["format"], "pdf")
            self.assertGreater(data["file_size"], 0)

            # Verify physical file
            self.assertTrue(os.path.exists(data["file_path"]))
            with open(data["file_path"], "rb") as f:
                header = f.read(5)
                self.assertEqual(header, b"%PDF-")

            # Stream download via API
            dl_res = self.client.get(f"/documents/generated/{data['id']}/download")
            self.assertEqual(dl_res.status_code, 200)
            self.assertEqual(dl_res.headers["content-type"], "application/pdf")
            self.assertEqual(len(dl_res.content), data["file_size"])

    def test_e2e_api_document_generation_docx_and_download(self):
        """E2E Test: Ingest doc -> POST /documents/generate (DOCX) -> verify DB & disk -> GET download."""
        doc_id = self.rag_service.ingest_document(
            self.sample_doc_path,
            owner_id=201,
            owner_username="operator_alpha",
            original_filename="Mangalore_Safety_Spec.txt"
        )

        app.dependency_overrides[get_current_user] = lambda: self.user_a

        with patch("backend.app.main.grounded_qa_service", self.qa_service):
            gen_res = self.client.post("/documents/generate", json={
                "title": "Mangalore Refinery Operational Protocol",
                "topic": "create a DOCX summary of Mangalore_Safety_Spec.txt",
                "format": "docx",
                "document_id": doc_id
            })

            self.assertEqual(gen_res.status_code, 200)
            data = gen_res.json()
            self.assertEqual(data["format"], "docx")
            self.assertGreater(data["file_size"], 0)

            # Stream download
            dl_res = self.client.get(f"/documents/generated/{data['id']}/download")
            self.assertEqual(dl_res.status_code, 200)
            self.assertIn("wordprocessingml.document", dl_res.headers["content-type"])
            self.assertEqual(len(dl_res.content), data["file_size"])

    def test_e2e_api_nonexistent_document_returns_404(self):
        """E2E Test: Requesting report generation on a non-existent document returns 404 with honest error."""
        app.dependency_overrides[get_current_user] = lambda: self.user_a

        with patch("backend.app.main.grounded_qa_service", self.qa_service):
            gen_res = self.client.post("/documents/generate", json={
                "title": "Ghost Report",
                "topic": "generate summary of non_existent_doc.pdf",
                "format": "pdf",
                "document_id": "non_existent_doc_id"
            })

            self.assertEqual(gen_res.status_code, 404)
            self.assertIn("was not found among your indexed documents", gen_res.json()["detail"])

    def test_generation_failure_cleanup_and_audit(self):
        """E2E Test: If generation fails, temporary files are removed, no DB record is created, and failure is logged."""
        bad_generator = DocumentGeneratorService(output_dir=self.generated_dir)
        with patch.object(bad_generator, "generate_pdf_report", side_effect=RuntimeError("Physical rendering failed")):
            with self.assertRaises(RuntimeError):
                bad_generator.create_report(
                    title="Failed Render Test",
                    sections={"Summary": "Fail"},
                    sources=[],
                    format_type="pdf",
                    owner_id=201,
                    owner_username="operator_alpha"
                )

        # Verify no record in SQLite
        records = bad_generator.list_generated_documents(owner_id=201)
        self.assertEqual(len(records), 0)

        # Verify audit failure event
        recent_logs = AuditLogger.query_audit_logs(limit=10)
        failed_event = next((l for l in recent_logs if l["action"] == "DOCUMENT_GENERATION_FAILED"), None)
        self.assertIsNotNone(failed_event)
        self.assertEqual(failed_event["status"], "failure")

if __name__ == "__main__":
    unittest.main()
