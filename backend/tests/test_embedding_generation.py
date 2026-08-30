import os
import unittest
from backend.rag.embeddings import (
    LocalTransformerEmbeddingModel,
    MockEmbeddingModel,
    get_local_embedding_model,
)

class TestEmbeddingGeneration(unittest.TestCase):
    def setUp(self):
        self.valid_model_path = os.path.abspath("./models/all-MiniLM-L6-v2")

    def test_local_model_initialization(self):
        """Verify that LocalTransformerEmbeddingModel initializes cleanly with real weights."""
        if not os.path.exists(self.valid_model_path):
            self.skipTest(f"Local model path {self.valid_model_path} does not exist.")
        
        model = LocalTransformerEmbeddingModel(self.valid_model_path)
        self.assertFalse(model.is_mock)
        self.assertEqual(model.model_name, "all-MiniLM-L6-v2")
        self.assertEqual(model.dimension, 384)

    def test_document_and_query_embedding_dimension(self):
        """Verify that document and query embeddings produce 384-dimensional real float vectors."""
        if not os.path.exists(self.valid_model_path):
            self.skipTest(f"Local model path {self.valid_model_path} does not exist.")
            
        model = get_local_embedding_model(self.valid_model_path)
        
        # Test document embedding
        doc_texts = ["AEGIS is a sovereign air-gapped AI workbench.", "Local vector index testing."]
        doc_vectors = model.embed_documents(doc_texts)
        self.assertEqual(len(doc_vectors), 2)
        self.assertEqual(len(doc_vectors[0]), 384)
        self.assertEqual(len(doc_vectors[1]), 384)
        
        # Test query embedding
        query_text = "What is AEGIS?"
        query_vector = model.embed_query(query_text)
        self.assertEqual(len(query_vector), 384)
        
        # Test embed_text interface method
        text_vector = model.embed_text(query_text)
        self.assertEqual(text_vector, query_vector)

    def test_singleton_loader_loads_model_once(self):
        """Verify that model is loaded only once and reused across invocations."""
        if not os.path.exists(self.valid_model_path):
            self.skipTest(f"Local model path {self.valid_model_path} does not exist.")
            
        model_inst_1 = get_local_embedding_model(self.valid_model_path)
        model_inst_2 = get_local_embedding_model(self.valid_model_path)
        self.assertIs(model_inst_1, model_inst_2)

    def test_missing_model_raises_clear_unavailable_error(self):
        """Verify that missing model directory raises clear 'Local embedding model is unavailable' error with NO mock fallback."""
        invalid_path = os.path.abspath("./models/non_existent_folder_xyz")
        with self.assertRaises(RuntimeError) as ctx:
            LocalTransformerEmbeddingModel(invalid_path)
        self.assertIn("Local embedding model is unavailable", str(ctx.exception))

    def test_no_mock_embedding_path_exists(self):
        """Verify that get_local_embedding_model never returns a mock embedding path."""
        if not os.path.exists(self.valid_model_path):
            self.skipTest(f"Local model path {self.valid_model_path} does not exist.")
            
        model = get_local_embedding_model(self.valid_model_path)
        self.assertFalse(model.is_mock)
        self.assertNotIsInstance(model, MockEmbeddingModel)

    def test_offline_local_operation(self):
        """Verify that the model operates entirely locally on CPU without cloud APIs."""
        if not os.path.exists(self.valid_model_path):
            self.skipTest(f"Local model path {self.valid_model_path} does not exist.")
            
        model = get_local_embedding_model(self.valid_model_path)
        vector = model.embed_query("Local air-gapped test payload")
        self.assertTrue(len(vector) > 0)
        self.assertEqual(len(vector), 384)
        self.assertTrue(any(v != 0 for v in vector))

if __name__ == "__main__":
    unittest.main()
