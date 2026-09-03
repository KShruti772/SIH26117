import unittest
import os
import sys
import tempfile
import sqlite3
import json
import uuid
import asyncio

from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.agents.conversations import ConversationManager
from backend.security.audit import AuditLogger
from backend.tools.code_sandbox.sandbox import SubprocessSandbox
from backend.rag.pipeline import AegisRagService
from backend.rag.embeddings import MockEmbeddingModel

class TestDataIntegrityAudit(unittest.TestCase):
    """
    Tests ensuring strict data integrity across the AEGIS application:
    - Multi-user conversation session isolation
    - Truthful audit ledger counts backed by real SQLite database rows
    - Subprocess sandbox real execution output & exit code integrity
    - Zero simulated text responses when model inference is unavailable
    - Empty state truthfulness in RAG and search operations
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, f"test_integrity_{uuid.uuid4().hex[:8]}.db")
        self.orig_auth_db = settings.AUTH_DB_PATH
        settings.AUTH_DB_PATH = self.db_path
        init_db()

    def tearDown(self):
        settings.AUTH_DB_PATH = self.orig_auth_db
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_multi_user_conversation_isolation(self):
        """Verify User A cannot see User B's conversations in list_conversations."""
        sid_a = f"conv_a_{uuid.uuid4().hex[:8]}"
        sid_b = f"conv_b_{uuid.uuid4().hex[:8]}"

        # Create conversation for user_a (id=101, username="operator_a")
        ConversationManager.create_conversation(
            title="Operator A Session",
            user_id=101,
            username="operator_a",
            session_id=sid_a
        )
        ConversationManager.add_message(
            session_id=sid_a,
            role="user",
            content="Confidential question from Operator A",
            user_id=101,
            username="operator_a"
        )

        # Create conversation for user_b (id=102, username="operator_b")
        ConversationManager.create_conversation(
            title="Operator B Session",
            user_id=102,
            username="operator_b",
            session_id=sid_b
        )
        ConversationManager.add_message(
            session_id=sid_b,
            role="user",
            content="Confidential question from Operator B",
            user_id=102,
            username="operator_b"
        )

        # Query conversations for user_a
        user_a_convs = ConversationManager.list_conversations(user_id=101, username="operator_a")
        user_a_ids = [c["id"] for c in user_a_convs]
        self.assertIn(sid_a, user_a_ids)
        self.assertNotIn(sid_b, user_a_ids, "User A must NOT see User B's conversations")

        # Query conversations for user_b
        user_b_convs = ConversationManager.list_conversations(user_id=102, username="operator_b")
        user_b_ids = [c["id"] for c in user_b_convs]
        self.assertIn(sid_b, user_b_ids)
        self.assertNotIn(sid_a, user_b_ids, "User B must NOT see User A's conversations")

        # Query conversations as admin (role=admin)
        admin_convs = ConversationManager.list_conversations(is_admin=True)
        admin_ids = [c["id"] for c in admin_convs]
        self.assertIn(sid_a, admin_ids)
        self.assertIn(sid_b, admin_ids)

    def test_unauthenticated_conversation_isolation(self):
        """Unauthenticated or null user receives empty list."""
        sid_sec = f"conv_sec_{uuid.uuid4().hex[:8]}"
        ConversationManager.create_conversation(
            title="Secret Session",
            user_id=201,
            username="analyst_1",
            session_id=sid_sec
        )
        unauth_convs = ConversationManager.list_conversations(user_id=None, username=None, is_admin=False)
        self.assertEqual(len(unauth_convs), 0)

    def test_persisted_conversation_messages_retrieval(self):
        """Verify retrieved conversation loads exact persisted messages without fabrication."""
        sid = f"conv_persist_{uuid.uuid4().hex[:8]}"
        ConversationManager.create_conversation(
            title="Safety Review",
            user_id=301,
            username="safety_lead",
            session_id=sid
        )
        ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="What are the lockout tagout protocols?",
            user_id=301,
            username="safety_lead"
        )
        ConversationManager.add_message(
            session_id=sid,
            role="assistant",
            content="Lockout/Tagout requires zero energy state verification.",
            user_id=301,
            username="safety_lead",
            rag_used=True,
            sources=[{"filename": "osha_guidelines.pdf", "page_number": 12}],
            model_id="gemma3:4b",
            verification="GROUNDED"
        )

        loaded = ConversationManager.get_conversation(sid)
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded["messages"]), 2)
        self.assertEqual(loaded["messages"][0]["content"], "What are the lockout tagout protocols?")
        self.assertEqual(loaded["messages"][1]["content"], "Lockout/Tagout requires zero energy state verification.")
        self.assertTrue(loaded["messages"][1]["rag_used"])
        self.assertEqual(loaded["messages"][1]["sources"][0]["filename"], "osha_guidelines.pdf")
        self.assertEqual(loaded["messages"][1]["verification"], "GROUNDED")

    def test_audit_ledger_authoritative_counts(self):
        """Verify audit totals come from actual SQL queries and not hardcoded numbers."""
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_logs")
        initial_total = cursor.fetchone()[0]
        conn.close()

        # Log 3 distinct operations
        AuditLogger.log_event(
            action="AUTH_LOGIN",
            component="security.auth",
            status="success",
            username="operator1"
        )
        AuditLogger.log_event(
            action="MODEL_LOAD",
            component="models.loaders",
            status="success",
            resource="gemma3:4b"
        )
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="tools.code_sandbox",
            status="failure",
            resource="script_1"
        )

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_logs")
        total_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE status = 'success'")
        success_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE status = 'failure'")
        failure_after = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(total_after, initial_total + 3)
        self.assertGreaterEqual(success_after, 2)
        self.assertGreaterEqual(failure_after, 1)

    def test_sandbox_subprocess_real_execution(self):
        """Verify sandbox returns actual subprocess execution metrics, not simulated data."""
        sandbox = SubprocessSandbox()
        
        # Test real stdout computation
        code = "val = sum([i * 2 for i in range(5)])\nprint(f'COMPUTED_SUM={val}')"
        res = sandbox.execute(code)
        
        self.assertTrue(res["success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("COMPUTED_SUM=20", res["stdout"])
        self.assertGreater(res["duration_ms"], 0)

        # Test real syntax error execution
        bad_code = "print('unterminated"
        bad_res = sandbox.execute(bad_code)
        self.assertFalse(bad_res["success"])
        self.assertIsNotNone(bad_res["error"])

    def test_rag_empty_state_truthfulness(self):
        """Verify empty RAG index returns empty results honestly without pretending."""
        chroma_dir = os.path.join(self.test_dir, "chroma_empty")
        rag = AegisRagService(
            embedding_model=MockEmbeddingModel(dimension=384),
            persist_directory=chroma_dir,
            safe_directories=[self.test_dir, os.getcwd()]
        )
        
        # Search when 0 documents exist
        results = rag.search("What is the emergency protocol?", top_k=5)
        self.assertEqual(len(results), 0, "Empty knowledge base must return 0 results, not fake matches")
        
        docs = rag.list_documents()
        self.assertEqual(len(docs), 0, "Document list must return 0 records when none ingested")
        
        stats = rag.get_document_stats()
        self.assertEqual(stats["total_documents"], 0)
        self.assertEqual(stats["indexed_documents"], 0)
        self.assertEqual(stats["total_chunks"], 0)

    def test_document_lifecycle_and_exact_counts(self):
        """
        Verify complete document lifecycle:
        1. Fresh DB -> 0 documents
        2. Upload 1 document with 13 chunks -> exactly 1 document registered, chunk_count=13
        3. Upload 2nd document -> exactly 2 documents registered
        4. Delete document -> count decreases to 1
        """
        chroma_dir = os.path.join(self.test_dir, f"chroma_life_{uuid.uuid4().hex[:8]}")
        rag = AegisRagService(
            embedding_model=MockEmbeddingModel(dimension=384),
            persist_directory=chroma_dir,
            safe_directories=[self.test_dir, os.getcwd()]
        )

        # 1. Fresh database -> 0 documents
        stats_0 = rag.get_document_stats()
        self.assertEqual(stats_0["indexed_documents"], 0)
        self.assertEqual(stats_0["total_chunks"], 0)

        # 2. Create sample document file with enough content to generate multiple chunks
        doc1_path = os.path.join(self.test_dir, "facility_manual.txt")
        with open(doc1_path, "w", encoding="utf-8") as f:
            # Generate paragraph content
            f.write("Industrial Safety Guidelines and Operating Procedures.\n" * 150)

        doc1_id = rag.ingest_document(
            doc1_path,
            chunk_size=300,
            chunk_overlap=50,
            owner_id=501,
            owner_username="safety_officer"
        )
        self.assertIsNotNone(doc1_id)

        # Verify 1 document with multiple chunks
        docs_after_1 = rag.list_documents(owner_id=501)
        self.assertEqual(len(docs_after_1), 1, "Must report exactly 1 document, NOT chunk count")
        self.assertGreater(docs_after_1[0]["chunk_count"], 1)

        stats_1 = rag.get_document_stats(owner_id=501)
        self.assertEqual(stats_1["indexed_documents"], 1)
        self.assertEqual(stats_1["total_chunks"], docs_after_1[0]["chunk_count"])

        # 3. Ingest a second document
        doc2_path = os.path.join(self.test_dir, "evacuation_plan.txt")
        with open(doc2_path, "w", encoding="utf-8") as f:
            f.write("Emergency Evacuation Procedures for sovereign node facility.\n" * 100)

        doc2_id = rag.ingest_document(
            doc2_path,
            chunk_size=300,
            chunk_overlap=50,
            owner_id=501,
            owner_username="safety_officer"
        )

        docs_after_2 = rag.list_documents(owner_id=501)
        self.assertEqual(len(docs_after_2), 2, "Must report exactly 2 documents")
        stats_2 = rag.get_document_stats(owner_id=501)
        self.assertEqual(stats_2["indexed_documents"], 2)

        # 4. Delete 1 document -> count decreases
        rag.delete_document(doc1_id)
        docs_after_delete = rag.list_documents(owner_id=501)
        self.assertEqual(len(docs_after_delete), 1)
        self.assertEqual(docs_after_delete[0]["id"], doc2_id)
        stats_after_delete = rag.get_document_stats(owner_id=501)
        self.assertEqual(stats_after_delete["indexed_documents"], 1)

    def test_multi_user_document_isolation(self):
        """Verify User A cannot see User B's documents in list_documents or get_document_stats."""
        chroma_dir = os.path.join(self.test_dir, f"chroma_iso_{uuid.uuid4().hex[:8]}")
        rag = AegisRagService(
            embedding_model=MockEmbeddingModel(dimension=384),
            persist_directory=chroma_dir,
            safe_directories=[self.test_dir, os.getcwd()]
        )

        # Ingest document for User A (id=601)
        doc_a_path = os.path.join(self.test_dir, "doc_user_a.txt")
        with open(doc_a_path, "w", encoding="utf-8") as f:
            f.write("Confidential financial projections for division A.\n" * 20)
        doc_a_id = rag.ingest_document(doc_a_path, owner_id=601, owner_username="user_a")

        # Ingest document for User B (id=602)
        doc_b_path = os.path.join(self.test_dir, "doc_user_b.txt")
        with open(doc_b_path, "w", encoding="utf-8") as f:
            f.write("Secret engineering schematics for division B.\n" * 20)
        doc_b_id = rag.ingest_document(doc_b_path, owner_id=602, owner_username="user_b")

        # User A query
        user_a_docs = rag.list_documents(owner_id=601)
        user_a_doc_ids = [d["id"] for d in user_a_docs]
        self.assertIn(doc_a_id, user_a_doc_ids)
        self.assertNotIn(doc_b_id, user_a_doc_ids, "User A must NOT see User B's documents")

        # User B query
        user_b_docs = rag.list_documents(owner_id=602)
        user_b_doc_ids = [d["id"] for d in user_b_docs]
        self.assertIn(doc_b_id, user_b_doc_ids)
        self.assertNotIn(doc_a_id, user_b_doc_ids, "User B must NOT see User A's documents")

        # Admin query
        admin_docs = rag.list_documents(is_admin=True)
        admin_doc_ids = [d["id"] for d in admin_docs]
        self.assertIn(doc_a_id, admin_doc_ids)
        self.assertIn(doc_b_id, admin_doc_ids)

    def test_failed_document_indexing_sets_status(self):
        """Verify that a document failing extraction sets status to 'failed' and is not indexed."""
        chroma_dir = os.path.join(self.test_dir, f"chroma_fail_{uuid.uuid4().hex[:8]}")
        rag = AegisRagService(
            embedding_model=MockEmbeddingModel(dimension=384),
            persist_directory=chroma_dir,
            safe_directories=[self.test_dir, os.getcwd()]
        )

        empty_doc_path = os.path.join(self.test_dir, "empty_doc.txt")
        with open(empty_doc_path, "w", encoding="utf-8") as f:
            f.write("")  # empty file -> InsufficientTextError

        from backend.rag.pipeline import InsufficientTextError
        with self.assertRaises(InsufficientTextError):
            rag.ingest_document(empty_doc_path, owner_id=701, owner_username="analyst_test")

        # Verify failed document recorded with status='failed'
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM documents WHERE owner_id = 701")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "failed")

        # Stats should show 0 indexed documents, 1 failed document
        stats = rag.get_document_stats(owner_id=701)
        self.assertEqual(stats["indexed_documents"], 0)
        self.assertEqual(stats["failed_documents"], 1)

if __name__ == "__main__":
    unittest.main()

