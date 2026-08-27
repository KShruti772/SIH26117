import os
from typing import List

class BaseEmbeddingModel:
    """Interface class defining methods for document and query vector embedding generators."""
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError

class MockEmbeddingModel(BaseEmbeddingModel):
    """
    A deterministic mock embedding model for testing RAG pipelines completely offline.
    Generates unit-norm vectors of a fixed dimension based on text content.
    """
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _mock_embed(self, text: str) -> List[float]:
        # Generate a deterministic vector based on characters in text
        val = sum(ord(c) for c in text) / 1000.0
        vec = []
        for i in range(self.dimension):
            vec.append((val + i) % 1.0)
        
        # Normalize vector to unit length
        norm = sum(x*x for x in vec) ** 0.5
        if norm > 0:
            return [x / norm for x in vec]
        return [0.0] * self.dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._mock_embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._mock_embed(text)

class LocalTransformerEmbeddingModel(BaseEmbeddingModel):
    """
    Local embedding model loading weights from sentence-transformers model files on disk.
    
    ---------------------------------------------------------------------------
    OFFLINE AIR-GAP SETUP INSTRUCTIONS:
    ---------------------------------------------------------------------------
    1. Download 'all-MiniLM-L6-v2' model files from HuggingFace
       (https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
    2. Extract it into your local models directory (e.g., './models/all-MiniLM-L6-v2')
    3. Ensure no network connection is triggered during initialization.
    ---------------------------------------------------------------------------
    """
    
    def __init__(self, model_path: str):
        self.model_path = os.path.abspath(model_path)
        self._model = None
        self._load_model()

    def _load_model(self):
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"Local embedding model folder was not found at: '{self.model_path}'.\n"
                f"Offline / Air-Gapped Setup Requirements:\n"
                f"1. Download the 'all-MiniLM-L6-v2' files from HuggingFace Hub.\n"
                f"2. Save the files to: '{self.model_path}'\n"
                f"3. Re-run ingestion."
            )
        from sentence_transformers import SentenceTransformer
        # Forces CPU offloading for development compatibility (No CUDA requirement)
        self._model = SentenceTransformer(self.model_path, device="cpu")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
