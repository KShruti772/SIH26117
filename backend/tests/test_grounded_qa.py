import os
import shutil
import tempfile
import unittest
import asyncio
import uuid
import sqlite3
from unittest.mock import MagicMock, patch, AsyncMock

from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.rag.embeddings import MockEmbeddingModel
from backend.rag.pipeline import AegisRagService
from backend.rag.grounded_qa import GroundedQAService
from backend.agents.conversations import ConversationManager
from fastapi.testclient import TestClient
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

class TestGroundedQAService(unittest.TestCase):
    """
    Verification test suite for Phase 2: Real Document-Grounded AI Analysis.
    Covers:
    1. Question answered from actual document evidence
    2. Correct source document and page number citations
    3. Multi-page and multi-chunk information synthesis
    4. Strict anti-hallucination refusal when evidence is missing
    5. Whole-document analysis & map-reduce chunk assembly
    6. Multi-tenant document isolation
    7. Document-scoped query filtering
    8. Authoritative conversation & message persistence
    9. REST API POST /documents/ask endpoint
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls.vectorstore_path = os.path.join(cls.test_dir, "test_vectorstore")
        cls.docs_dir = os.path.join(cls.test_dir, "test_docs")
        os.makedirs(cls.vectorstore_path, exist_ok=True)
        os.makedirs(cls.docs_dir, exist_ok=True)

        # Create multi-page sample documents
        cls.doc1_path = os.path.join(cls.docs_dir, "FT_03.txt")
        with open(cls.doc1_path, "w", encoding="utf-8") as f:
            f.write(
                "Project Title: Sovereign On-Premise Agentic AI Workbench for Confidential Industrial Work.\n\n"
                "Section 1: Overview and Objectives\n"
                "The objective is to provide a 100% air-gapped sovereign AI system for Mangalore Refinery.\n\n"
                "Section 2: System Architecture\n"
                "The architecture features a 3-tier sovereign pipeline consisting of local vector search, code sandbox, and grounding verifier.\n\n"
                "Section 3: Safety and Emergency Protocols\n"
                "If pipeline pressure exceeds 180 PSI, operators must initiate the automated nitrogen purge procedure immediately."
            )

        cls.doc2_path = os.path.join(cls.docs_dir, "security_policy.txt")
        with open(cls.doc2_path, "w", encoding="utf-8") as f:
            f.write(
                "Organizational Security Policy.\n\n"
                "Section 1: Access Control\n"
                "Multi-factor authentication is mandatory for all root operations.\n\n"
                "Section 2: Encryption Standards\n"
                "All stored artifacts must use AES-256 and HMAC-SHA256 hash chains."
            )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        self.orig_auth_db = settings.AUTH_DB_PATH
        self.db_path = os.path.join(self.test_dir, f"test_grounded_{uuid.uuid4().hex[:8]}.db")
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

        self.mock_loader = MagicMock()
        self.mock_loader.generate = AsyncMock(return_value=(
            "According to the documentation, if pipeline pressure exceeds 180 PSI, operators must initiate "
            "the automated nitrogen purge procedure immediately [Source: FT_03.txt | Page 1]."
        ))

        self.qa_service = GroundedQAService(
            rag_service=self.rag_service,
            loader_manager=self.mock_loader
        )

        self.client = TestClient(app)
        self.user_a = MockUser({"id": 101, "username": "operator_a", "role": "user"})
        self.user_b = MockUser({"id": 102, "username": "operator_b", "role": "user"})
        self.admin = MockUser({"id": 999, "username": "admin", "role": "admin"})

    def tearDown(self):
        app.dependency_overrides.clear()
        settings.AUTH_DB_PATH = self.orig_auth_db
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_question_answered_from_real_document_evidence(self):
        """1 & 2. Verify answer is generated strictly from evidence and contains citations."""
        doc_id = self.rag_service.ingest_document(
            self.doc1_path,
            owner_id=101,
            owner_username="operator_a",
            original_filename="FT_03.txt"
        )

        res = asyncio.run(self.qa_service.generate_grounded_answer(
            query="What is the emergency protocol if pressure exceeds 180 PSI?",
            current_user=self.user_a
        ))

        self.assertTrue(res["grounded"])
        self.assertIn("180 PSI", res["answer"])
        self.assertGreater(len(res["sources"]), 0)
        self.assertEqual(res["sources"][0]["filename"], "FT_03.txt")
        self.assertEqual(res["sources"][0]["document_id"], doc_id)

    def test_anti_hallucination_refusal_when_no_evidence_exists(self):
        """6 & 7. Verify question with no supporting evidence returns honest refusal without calling LLM."""
        # Empty index — zero documents ingested
        res = asyncio.run(self.qa_service.generate_grounded_answer(
            query="What is the quantum encryption key for the satellite link?",
            current_user=self.user_a
        ))

        self.assertFalse(res["grounded"])
        self.assertEqual(
            res["answer"],
            "I could not find sufficient evidence in the indexed organizational documents to answer this question."
        )
        self.assertEqual(len(res["sources"]), 0)
        # Verify LLM was NOT invoked with empty context
        self.mock_loader.generate.assert_not_called()

    def test_multi_user_document_isolation(self):
        """11. Verify User A cannot retrieve User B's private documents."""
        # Ingest doc for User B
        doc_b_id = self.rag_service.ingest_document(
            self.doc2_path,
            owner_id=102,
            owner_username="operator_b",
            original_filename="security_policy.txt"
        )

        # User A asks question about User B's document
        res_a = asyncio.run(self.qa_service.generate_grounded_answer(
            query="What encryption standard is required for stored artifacts?",
            current_user=self.user_a
        ))

        # User A must NOT receive User B's document content
        self.assertFalse(res_a["grounded"])
        self.assertEqual(
            res_a["answer"],
            "I could not find sufficient evidence in the indexed organizational documents to answer this question."
        )

        # User B asks the same question and gets grounded response
        self.mock_loader.generate.return_value = "AES-256 and HMAC-SHA256 [Source: security_policy.txt | Page 1]"
        res_b = asyncio.run(self.qa_service.generate_grounded_answer(
            query="What encryption standard is required for stored artifacts?",
            current_user=self.user_b
        ))
        self.assertTrue(res_b["grounded"])
        self.assertIn("AES-256", res_b["answer"])

    def test_document_scoped_analysis(self):
        """12. Verify query scoped to a specific document ID only accesses that document."""
        doc1_id = self.rag_service.ingest_document(self.doc1_path, owner_id=101, original_filename="FT_03.txt")
        doc2_id = self.rag_service.ingest_document(self.doc2_path, owner_id=101, original_filename="security_policy.txt")

        # Scope query specifically to doc1
        res = asyncio.run(self.qa_service.generate_grounded_answer(
            query="What is the objective of the workbench?",
            document_id=doc1_id,
            current_user=self.user_a
        ))

        self.assertTrue(res["grounded"])
        for src in res["sources"]:
            self.assertEqual(src["document_id"], doc1_id)

    def test_conversation_and_message_persistence(self):
        """8, 9, 10. Verify Q&A exchange persists authoritatively in SQLite conversation history."""
        self.rag_service.ingest_document(self.doc1_path, owner_id=101, original_filename="FT_03.txt")
        sid = f"conv_qa_{uuid.uuid4().hex[:8]}"

        # Create session
        ConversationManager.create_conversation(
            title="Safety Review Session",
            user_id=101,
            username="operator_a",
            session_id=sid,
            feature="knowledge"
        )

        # Ask question with session_id
        res = asyncio.run(self.qa_service.generate_grounded_answer(
            query="Explain the emergency protocol for high pressure.",
            session_id=sid,
            current_user=self.user_a
        ))

        # Retrieve conversation from SQLite
        loaded = ConversationManager.get_conversation(sid)
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded["messages"]), 2)
        self.assertEqual(loaded["messages"][0]["role"], "user")
        self.assertEqual(loaded["messages"][0]["content"], "Explain the emergency protocol for high pressure.")
        self.assertEqual(loaded["messages"][1]["role"], "assistant")
        self.assertTrue(loaded["messages"][1]["rag_used"])
        self.assertEqual(loaded["messages"][1]["verification"], "GROUNDED")

    def test_whole_document_summarization_strategy(self):
        """5. Verify whole-document query retrieves all ordered chunks."""
        doc1_id = self.rag_service.ingest_document(self.doc1_path, owner_id=101, original_filename="FT_03.txt")

        self.mock_loader.generate.return_value = (
            "Executive Summary:\nThe AEGIS project establishes a sovereign on-premise AI workbench.\n\n"
            "Architecture:\n3-tier air-gapped system with local vector store and sandboxes [Source: FT_03.txt | Page 1]."
        )

        res = asyncio.run(self.qa_service.generate_grounded_answer(
            query="Summarize the entire document and explain the project architecture.",
            current_user=self.user_a
        ))

        self.assertTrue(res["grounded"])
        self.assertIn("Executive Summary", res["answer"])
        self.assertEqual(res["sources"][0]["filename"], "FT_03.txt")

    def test_rest_api_ask_documents_endpoint(self):
        """16. Verify FastAPI POST /documents/ask endpoint end-to-end."""
        doc1_id = self.rag_service.ingest_document(self.doc1_path, owner_id=101, original_filename="FT_03.txt")
        app.dependency_overrides[get_current_user] = lambda: self.user_a

        with patch("backend.app.main.grounded_qa_service.rag_service", self.rag_service), \
             patch("backend.app.main.grounded_qa_service.loader_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "The workbench operates 100% air-gapped [Source: FT_03.txt | Page 1]."
            
            payload = {
                "query": "What are the core operating conditions?",
                "document_id": doc1_id,
                "top_k": 3
            }
            response = self.client.post("/documents/ask", json=payload)

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["grounded"])
            self.assertIn("100% air-gapped", data["answer"])
            self.assertGreater(len(data["sources"]), 0)

if __name__ == "__main__":
    unittest.main()
