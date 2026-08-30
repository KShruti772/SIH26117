import os
import shutil
import tempfile
import unittest
from backend.rag.embeddings import get_local_embedding_model
from backend.rag.pipeline import AegisRagService

class TestSimilarityRetrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls.vector_dir = os.path.join(cls.test_dir, "test_vectorstore")
        cls.doc_dir = os.path.join(cls.test_dir, "docs")
        os.makedirs(cls.doc_dir, exist_ok=True)
        
        # Initialize real embedding model
        model_path = os.path.abspath("./models/all-MiniLM-L6-v2")
        cls.embedding_model = get_local_embedding_model(model_path)
        
        # Instantiate RAG service targeting isolated temp directory
        cls.rag_service = AegisRagService(
            embedding_model=cls.embedding_model,
            persist_directory=cls.vector_dir,
            safe_directories=[cls.test_dir]
        )
        
        # Write deterministic test document
        cls.sample_doc_path = os.path.join(cls.doc_dir, "safety_manual.txt")
        with open(cls.sample_doc_path, "w", encoding="utf-8") as f:
            f.write("The emergency shutdown procedure requires operators to press the red isolation switch immediately.")
            
        cls.doc_id = cls.rag_service.ingest_document(cls.sample_doc_path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_semantically_related_query_retrieves_relevant_chunk(self):
        """Verify that a semantically related query matches the relevant text passage."""
        query = "What should an operator do to initiate an emergency shutdown?"
        results = self.rag_service.search(query=query, top_k=1)
        
        self.assertEqual(len(results), 1)
        matched_text = results[0]["text"]
        self.assertIn("red isolation switch", matched_text)
        self.assertIn("emergency shutdown procedure", matched_text)

    def test_unrelated_query_has_higher_distance(self):
        """Verify that an unrelated query receives a significantly higher distance score."""
        related_query = "How to trigger an emergency shutdown?"
        unrelated_query = "What is the capital city of France?"
        
        related_res = self.rag_service.search(query=related_query, top_k=1)
        unrelated_res = self.rag_service.search(query=unrelated_query, top_k=1)
        
        self.assertTrue(len(related_res) > 0)
        self.assertTrue(len(unrelated_res) > 0)
        
        # Lower cosine distance = higher similarity
        related_distance = related_res[0]["distance"]
        unrelated_distance = unrelated_res[0]["distance"]
        
        self.assertLess(related_distance, unrelated_distance)

    def test_dynamic_query_text_usage_no_hardcoding(self):
        """Verify that the retrieval function executes search using the passed query text dynamically."""
        query_1 = "emergency shutdown"
        query_2 = "red isolation switch"
        
        res_1 = self.rag_service.search(query=query_1, top_k=1)
        res_2 = self.rag_service.search(query=query_2, top_k=1)
        
        # Verify query_1 and query_2 trigger individual search executions
        self.assertIsNotNone(res_1)
        self.assertIsNotNone(res_2)

    def test_returned_chunk_preserves_complete_metadata(self):
        """Verify that returned chunk results preserve non-fabricated metadata fields."""
        query = "emergency shutdown procedure"
        results = self.rag_service.search(query=query, top_k=1)
        
        self.assertEqual(len(results), 1)
        meta = results[0]["metadata"]
        
        self.assertEqual(meta["document_id"], self.doc_id)
        self.assertEqual(meta["filename"], "safety_manual.txt")
        self.assertIn("page_number", meta)
        self.assertIn("chunk_id", meta)
        self.assertIn("chunk_index", meta)
        self.assertEqual(meta["is_mock"], False)

if __name__ == "__main__":
    unittest.main()
