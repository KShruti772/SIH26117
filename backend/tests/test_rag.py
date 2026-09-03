import os
import unittest
import shutil
import tempfile
import time
import pypdf
from backend.rag.embeddings import MockEmbeddingModel
from backend.rag.pipeline import (
    AegisRagService,
    DocumentLoader,
    RecursiveTextSplitter,
    SafePathViolationError,
    DuplicateIngestionError,
    InsufficientTextError
)

class TestAegisRagPipeline(unittest.TestCase):
    """Unit tests for offline-capable Local Knowledge base and RAG pipeline operations."""
    
    @classmethod
    def setUpClass(cls):
        # Create temp folder for test vectorstore and doc ingestions
        cls.test_dir = tempfile.gettempdir()
        cls.vectorstore_path = os.path.join(cls.test_dir, "aegis_vectorstore_test")
        cls.safe_dir_path = os.path.join(cls.test_dir, "aegis_safe_data_test")
        
        os.makedirs(cls.vectorstore_path, exist_ok=True)
        os.makedirs(cls.safe_dir_path, exist_ok=True)
        
        # Ingestion test files paths
        cls.txt_file = os.path.join(cls.safe_dir_path, "sample_doc.txt")
        cls.pdf_file = os.path.join(cls.safe_dir_path, "sample_doc.pdf")
        cls.empty_txt_file = os.path.join(cls.safe_dir_path, "empty.txt")
        cls.scanned_pdf_file = os.path.join(cls.safe_dir_path, "scanned_empty.pdf")
        
        # Write dummy txt
        with open(cls.txt_file, "w", encoding="utf-8") as f:
            f.write(
                "Aegis sovereign AI workbench is built for Mangalore Refinery and Petrochemicals Limited. "
                "The safety protocols for pipeline maintenance are detailed in Section 4. "
                "Maintain pressure below 150 PSI during repairs."
            )
            
        with open(cls.empty_txt_file, "w", encoding="utf-8") as f:
            f.write("   ")
            
        # Write minimal valid text PDF bytes
        pdf_bytes = (
            b"%PDF-1.1\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
            b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
            b"5 0 obj\n<< /Length 59 >>\nstream\n"
            b"BT\n/F1 12 Tf\n72 712 Td\n(Refinery turnaround rules: check valve pressure twice) Tj\nET\nendstream\nendobj\n"
            b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000062 00000 n \n0000000119 00000 n \n0000000213 00000 n \n0000000292 00000 n \n"
            b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
            b"startxref\n402\n%%EOF\n"
        )
        with open(cls.pdf_file, "wb") as f:
            f.write(pdf_bytes)

        # Write scanned PDF (valid PDF structure but empty page contents)
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=72, height=72)
        with open(cls.scanned_pdf_file, "wb") as f:
            writer.write(f)

    @classmethod
    def tearDownClass(cls):
        # Clean up database files and workspaces
        for path in [cls.vectorstore_path, cls.safe_dir_path]:
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                except Exception:
                    pass

    def setUp(self):
        # Refresh the database collection for clean test scopes
        import uuid
        from backend.app.config.settings import settings
        from backend.security.database import init_db
        self.orig_auth_db = settings.AUTH_DB_PATH
        self.db_path = os.path.join(self.safe_dir_path, f"test_rag_{uuid.uuid4().hex[:8]}.db")
        settings.AUTH_DB_PATH = self.db_path
        init_db()

        self.embedding_model = MockEmbeddingModel()
        self.rag_service = AegisRagService(
            embedding_model=self.embedding_model,
            persist_directory=self.vectorstore_path,
            safe_directories=[self.safe_dir_path]
        )
        
        # Clear collection elements if already exist
        if self.rag_service.collection.count() > 0:
            all_ids = self.rag_service.collection.get()["ids"]
            if all_ids:
                self.rag_service.collection.delete(ids=all_ids)

    def tearDown(self):
        from backend.app.config.settings import settings
        settings.AUTH_DB_PATH = self.orig_auth_db
        if hasattr(self, "db_path") and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_embedding_generation(self):
        """5. Verify the embedding model outputs expected dimensional vectors."""
        embedding = self.embedding_model.embed_query("Test string")
        self.assertEqual(len(embedding), 384)
        
        embeddings = self.embedding_model.embed_documents(["Test 1", "Test 2"])
        self.assertEqual(len(embeddings), 2)
        self.assertEqual(len(embeddings[0]), 384)

    def test_chunk_generation(self):
        """3. Verify recursive text splitter correctly divides character streams."""
        splitter = RecursiveTextSplitter(chunk_size=100, chunk_overlap=10)
        text = "A" * 250
        chunks = splitter.split_text(text)
        
        self.assertEqual(len(chunks), 3) # 100, 100, 70 (approx with overlaps)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 100)

    def test_txt_ingestion_and_retrieval(self):
        """1, 7. Verify plain text files load, split, index, and retrieve successfully."""
        doc_id = self.rag_service.ingest_document(self.txt_file, chunk_size=500, chunk_overlap=50)
        self.assertTrue(doc_id)
        
        # Query
        results = self.rag_service.search("pressure limit PSI", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("PSI", results[0]["text"])

    def test_logical_document_count_is_not_chunk_count(self):
        """A single multi-chunk source is returned as one logical document."""
        doc_id = self.rag_service.ingest_document(self.txt_file, chunk_size=40, chunk_overlap=5)
        documents = self.rag_service.list_documents()

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["document_id"], doc_id)
        self.assertGreater(documents[0]["chunk_count"], 1)

    def test_two_documents_have_two_logical_records(self):
        """Two distinct sources produce two logical document records."""
        self.rag_service.ingest_document(self.txt_file)
        self.rag_service.ingest_document(self.pdf_file)

        self.assertEqual(len(self.rag_service.list_documents()), 2)

    def test_pdf_ingestion_and_retrieval(self):
        """2, 7. Verify PDF content parsing, indexing, and vector similarity search works."""
        doc_id = self.rag_service.ingest_document(self.pdf_file)
        self.assertTrue(doc_id)
        
        results = self.rag_service.search("turnaround Rules", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("turnaround", results[0]["text"])

    def test_metadata_preservation(self):
        """4. Verify chunk payloads preserve original metadata logs."""
        self.rag_service.ingest_document(self.pdf_file)
        results = self.rag_service.search("turnaround", top_k=1)
        
        meta = results[0]["metadata"]
        self.assertEqual(meta["filename"], "sample_doc.pdf")
        self.assertEqual(meta["page_number"], 1)
        self.assertIn("chunk_id", meta)
        self.assertIn("document_id", meta)

    def test_chroma_persistence(self):
        """6. Verify that vector stores are saved on disk and survive service reloads."""
        # 1. Ingest document in initial service
        self.rag_service.ingest_document(self.txt_file)
        
        # 2. Re-instantiate service (simulating application reload)
        new_rag_service = AegisRagService(
            embedding_model=self.embedding_model,
            persist_directory=self.vectorstore_path,
            safe_directories=[self.safe_dir_path]
        )
        
        # 3. Query new service and check if database entries are preserved
        results = new_rag_service.search("pressure limit", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("pressure", results[0]["text"])

    def test_empty_database(self):
        """8. Verify searching an empty database returns empty results safely."""
        # Database count is 0
        self.assertEqual(self.rag_service.list_documents(), [])
        results = self.rag_service.search("pressure", top_k=3)
        self.assertEqual(results, [])

    def test_malformed_document(self):
        """9. Verify empty files or scanned PDFs throw text extraction error checks."""
        with self.assertRaises(InsufficientTextError):
            self.rag_service.ingest_document(self.empty_txt_file)
            
        with self.assertRaises(InsufficientTextError):
            self.rag_service.ingest_document(self.scanned_pdf_file)
        self.assertEqual(self.rag_service.list_documents(), [])

    def test_deleted_document_is_removed_from_logical_count(self):
        """Deleting a document removes all of its chunks and its logical record."""
        doc_id = self.rag_service.ingest_document(self.txt_file)
        self.assertEqual(len(self.rag_service.list_documents()), 1)

        self.rag_service.delete_document(doc_id)

        self.assertEqual(self.rag_service.list_documents(), [])

    def test_duplicate_ingestion(self):
        """10. Verify duplicate document indexing requests are blocked."""
        self.rag_service.ingest_document(self.txt_file)
        with self.assertRaises(DuplicateIngestionError):
            self.rag_service.ingest_document(self.txt_file)

    def test_duplicate_content_in_different_paths_is_rejected(self):
        """UUID-prefixed storage paths cannot bypass duplicate-content detection."""
        duplicate_path = os.path.join(self.safe_dir_path, "same-content-renamed.txt")
        shutil.copyfile(self.txt_file, duplicate_path)
        try:
            self.rag_service.ingest_document(self.txt_file)
            with self.assertRaises(DuplicateIngestionError):
                self.rag_service.ingest_document(duplicate_path)
        finally:
            if os.path.exists(duplicate_path):
                os.remove(duplicate_path)

    def test_unsafe_path_traversal(self):
        """11. Verify path traversal escapes outside safe directories are blocked."""
        unsafe_file_path = os.path.join(self.test_dir, "leak_attempt.txt")
        with open(unsafe_file_path, "w") as f:
            f.write("leaked sensitive information")
            
        try:
            # Attempt to ingest file outside self.safe_dir_path
            with self.assertRaises(SafePathViolationError):
                self.rag_service.ingest_document(unsafe_file_path)
        finally:
            if os.path.exists(unsafe_file_path):
                os.remove(unsafe_file_path)

    def test_scanned_pdf_ocr_fallback(self):
        """Verify RAG service integrates with OCR service as fallback for scanned PDFs."""
        from unittest.mock import MagicMock
        from backend.multimodal.ocr import BaseOCR
        
        mock_ocr = MagicMock(spec=BaseOCR)
        mock_ocr.is_available.return_value = True
        mock_ocr.ocr_pdf.return_value = {
            "document": "scanned_empty.pdf",
            "pages": [{"page_number": 1, "text": "Extracted OCR text payload"}]
        }
        
        # Configure service with mock OCR
        self.rag_service.ocr_service = mock_ocr
        
        doc_id = self.rag_service.ingest_document(self.scanned_pdf_file)
        self.assertTrue(doc_id)
        
        # Verify collection holds the OCR output
        results = self.rag_service.search("payload", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("OCR text", results[0]["text"])

if __name__ == "__main__":
    unittest.main()
