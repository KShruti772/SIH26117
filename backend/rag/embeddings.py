import os
import logging
from typing import List, Optional

logger = logging.getLogger("aegis.rag.embeddings")

class BaseEmbeddingModel:
    """Interface class defining methods for document and query vector embedding generators."""
    
    def embed_text(self, text: str) -> List[float]:
        return self.embed_query(text)

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
        self.model_name = "mock-embedding-384"
        self.is_mock = True

    def _mock_embed(self, text: str) -> List[float]:
        val = sum(ord(c) for c in text) / 1000.0
        vec = []
        for i in range(self.dimension):
            vec.append((val + i) % 1.0)
        
        norm = sum(x*x for x in vec) ** 0.5
        if norm > 0:
            return [x / norm for x in vec]
        return [0.0] * self.dimension

    def embed_text(self, text: str) -> List[float]:
        return self._mock_embed(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._mock_embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._mock_embed(text)

class LocalTransformerEmbeddingModel(BaseEmbeddingModel):
    """
    Local embedding model loading weights from sentence-transformers model files on disk.
    Ensures zero cloud API calls and single-instance memory allocation.
    """
    
    def __init__(self, model_path: str):
        self.model_path = os.path.abspath(model_path)
        self.model_name = "all-MiniLM-L6-v2"
        self.is_mock = False
        self.dimension = 384
        self._model = None
        self._load_model()

    def _load_model(self):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        if not os.path.exists(self.model_path):
            raise RuntimeError(
                f"Local embedding model is unavailable. Directory not found at: '{self.model_path}'.\n"
                f"Air-Gapped Requirements: Download 'all-MiniLM-L6-v2' and place files into '{self.model_path}'."
            )
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading local SentenceTransformer model weights from: '{self.model_path}'...")
            # CPU offloading for local workstation compatibility
            self._model = SentenceTransformer(self.model_path, device="cpu", local_files_only=True)
            logger.info("Local SentenceTransformer embedding model initialized successfully.")
        except Exception as e:
            raise RuntimeError(f"Local embedding model is unavailable: {e}")

    def embed_text(self, text: str) -> List[float]:
        return self.embed_query(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self._model:
            raise RuntimeError("Local embedding model is unavailable.")
        if not texts:
            return []
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        if not self._model:
            raise RuntimeError("Local embedding model is unavailable.")
        if not text:
            return [0.0] * self.dimension
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()


_singleton_embedding_model: Optional[LocalTransformerEmbeddingModel] = None

def get_local_embedding_model(model_path: str = "./models/all-MiniLM-L6-v2") -> LocalTransformerEmbeddingModel:
    """Returns singleton instance of LocalTransformerEmbeddingModel to avoid reloading weights per request."""
    global _singleton_embedding_model
    abs_path = os.path.abspath(model_path)
    if _singleton_embedding_model is None or _singleton_embedding_model.model_path != abs_path:
        _singleton_embedding_model = LocalTransformerEmbeddingModel(abs_path)
    return _singleton_embedding_model

