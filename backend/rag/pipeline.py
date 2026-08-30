import os
import time
import hashlib
import logging
from typing import List, Dict, Any, Optional
import pypdf
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from backend.rag.embeddings import BaseEmbeddingModel
from backend.multimodal.ocr import BaseOCR

logger = logging.getLogger("aegis.rag")

class RagError(Exception):
    """Base exception for RAG pipeline errors."""
    pass

class SafePathViolationError(RagError):
    """Raised when ingestion path violates configured directory boundary parameters."""
    pass

class DuplicateIngestionError(RagError):
    """Raised when trying to ingest a document that is already parsed and stored."""
    pass

class InsufficientTextError(RagError):
    """Raised when document extraction outputs no text (e.g. scanned image PDFs)."""
    pass

class ChromaEmbeddingAdapter(EmbeddingFunction):
    """Adapts Aegis BaseEmbeddingModel to ChromaDB's internal EmbeddingFunction format."""
    
    def __init__(self, model: BaseEmbeddingModel):
        self.model = model

    def __call__(self, input: Documents) -> Embeddings:
        return self.model.embed_documents(input)

class DocumentLoader:
    """Loads and extracts text contents from local TXT and PDF documents."""
    
    @staticmethod
    def load_document(file_path: str) -> List[Dict[str, Any]]:
        """Resolves file extension and returns list of page dictionaries."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".txt":
            return DocumentLoader.load_txt(file_path)
        elif ext == ".pdf":
            return DocumentLoader.load_pdf(file_path)
        else:
            raise ValueError(f"Unsupported document file extension format: '{ext}'")

    @staticmethod
    def load_txt(file_path: str) -> List[Dict[str, Any]]:
        """Reads plain text file inputs."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                text = f.read()
                
        if not text.strip():
            raise InsufficientTextError("Document is empty or contains no extractable text characters.")
            
        return [{"text": text, "page_number": 1}]

    @staticmethod
    def load_pdf(file_path: str) -> List[Dict[str, Any]]:
        """Extracts text pages from native PDF files using pypdf."""
        pages = []
        total_text = ""
        try:
            reader = pypdf.PdfReader(file_path)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                total_text += text
                pages.append({"text": text, "page_number": idx + 1})
        except Exception as e:
            raise ValueError(f"Failed to parse PDF document contents: {e}")

        # Insufficient text check (indicates a scanned image PDF requiring local OCR)
        if len(total_text.strip()) < 15:
            raise InsufficientTextError("PDF contains no extractable text. Scanned document requires OCR.")
            
        return pages

class RecursiveTextSplitter:
    """Splits large text blocks recursively into overlapping chunk fragments."""
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        """Performs character-based recursive chunk split logic with overlaps."""
        chunks = []
        text = text.strip()
        if not text:
            return []
            
        pos = 0
        text_len = len(text)
        while pos < text_len:
            end = min(pos + self.chunk_size, text_len)
            chunk = text[pos:end]
            chunks.append(chunk)
            pos += self.chunk_size - self.chunk_overlap
            if pos >= text_len - self.chunk_overlap:
                break
        return chunks

class AegisRagService:
    """Core local RAG service orchestrating vector indexes, embeddings, and similarity retrieval."""
    
    def __init__(self, embedding_model: BaseEmbeddingModel, persist_directory: str = "vectorstore", safe_directories: Optional[List[str]] = None, ocr_service: Optional[BaseOCR] = None):
        self.embedding_model = embedding_model
        self.persist_directory = os.path.abspath(persist_directory)
        self.ocr_service = ocr_service
        
        # Enforce local workspace path boundaries to prevent traversal leakage
        self.safe_directories = [os.path.abspath(d) for d in (safe_directories or [os.getcwd()])]
        
        # Initialize local persistent SQLite Chroma Client
        self.chroma_client = chromadb.PersistentClient(path=self.persist_directory)
        self.embedding_fn = ChromaEmbeddingAdapter(self.embedding_model)
        
        # Get or create vector collection
        self.collection = self.chroma_client.get_or_create_collection(
            name="aegis_knowledge",
            embedding_function=self.embedding_fn
        )
        self._verify_collection_compatibility()

    def _verify_collection_compatibility(self):
        """Safely detects and purges stale mock vector data if embedding model upgraded to real transformer weights."""
        try:
            if self.collection.count() > 0:
                sample = self.collection.get(limit=1)
                if sample and sample.get("metadatas") and sample["metadatas"]:
                    meta = sample["metadatas"][0]
                    was_mock = meta.get("is_mock", False) or meta.get("embedding_model") == "mock-embedding-384"
                    is_now_real = not getattr(self.embedding_model, "is_mock", False)
                    if was_mock and is_now_real:
                        logger.warning("Mock embeddings detected in ChromaDB collection. Rebuilding collection for real transformer model.")
                        self.chroma_client.delete_collection("aegis_knowledge")
                        self.collection = self.chroma_client.get_or_create_collection(
                            name="aegis_knowledge",
                            embedding_function=self.embedding_fn
                        )
        except Exception as e:
            logger.warning(f"Collection compatibility verification notice: {e}")

    def _validate_safe_path(self, file_path: str) -> str:
        """Validates that ingestion target lies strictly inside configured directories."""
        abs_path = os.path.abspath(file_path)
        is_safe = any(abs_path.startswith(safe_dir) for safe_dir in self.safe_directories)
        if not is_safe:
            from backend.security.audit import AuditLogger
            AuditLogger.log_event(
                action="DOCUMENT_INGEST",
                component="rag.pipeline",
                status="failure",
                resource=os.path.basename(file_path),
                metadata={"filename": os.path.basename(file_path), "error_category": "safe_path_violation"}
            )
            raise SafePathViolationError(
                f"Path traversal check failed. File path '{file_path}' is outside safe directories."
            )
        return abs_path

    def _generate_doc_id(self, file_path: str) -> str:
        """Computes unique SHA-256 ID based on the document basename to prevent path-shifting duplicate issues."""
        basename = os.path.basename(file_path)
        return hashlib.sha256(basename.encode("utf-8")).hexdigest()

    def ingest_document(
        self, 
        file_path: str, 
        chunk_size: int = 500, 
        chunk_overlap: int = 50,
        owner_id: Optional[int] = None,
        owner_username: Optional[str] = None
    ) -> str:
        """Reads document, splits text, embeds chunks locally, and commits records to persistent ChromaDB with owner controls."""
        from backend.security.audit import AuditLogger
        
        # 1. Path Safety & Existence validations
        try:
            abs_path = self._validate_safe_path(file_path)
            if not os.path.exists(abs_path):
                raise FileNotFoundError(f"Document file does not exist on disk: '{file_path}'")
                
            doc_id = self._generate_doc_id(abs_path)
            filename = os.path.basename(abs_path)
        except Exception as e:
            # Let the exception propagate but make sure to log it if it was not handled by _validate_safe_path
            if not isinstance(e, SafePathViolationError):
                AuditLogger.log_event(
                    action="DOCUMENT_INGEST",
                    component="rag.pipeline",
                    status="failure",
                    resource=os.path.basename(file_path),
                    metadata={"filename": os.path.basename(file_path), "error_category": "path_resolution_error"}
                )
            raise

        # 2. Duplicate Ingestion Verification
        existing = self.collection.get(
            where={"document_id": doc_id},
            limit=1
        )
        if existing and existing.get("ids"):
            AuditLogger.log_event(
                action="DOCUMENT_INGEST",
                component="rag.pipeline",
                status="failure",
                resource=filename,
                metadata={"filename": filename, "error_category": "duplicate_rejection"}
            )
            raise DuplicateIngestionError(f"Ingestion rejected. Document '{filename}' is already indexed.")

        # 3. Read Page Contents
        try:
            pages = DocumentLoader.load_document(abs_path)
        except InsufficientTextError as e:
            if self.ocr_service and self.ocr_service.is_available():
                logger.info(f"Normal text extraction failed (insufficient text). Falling back to OCR for '{filename}'.")
                
                # Audit OCR process start/success
                AuditLogger.log_event(
                    action="OCR_PROCESS",
                    component="rag.pipeline",
                    status="success",
                    resource=filename,
                    metadata={"filename": filename}
                )
                
                ocr_result = self.ocr_service.ocr_pdf(abs_path)
                pages = ocr_result["pages"]
            else:
                AuditLogger.log_event(
                    action="DOCUMENT_INGEST",
                    component="rag.pipeline",
                    status="failure",
                    resource=filename,
                    metadata={"filename": filename, "error_category": "insufficient_text"}
                )
                raise e
        except Exception as e:
            AuditLogger.log_event(
                action="DOCUMENT_INGEST",
                component="rag.pipeline",
                status="failure",
                resource=filename,
                metadata={"filename": filename, "error_category": "parse_failure"}
            )
            raise e

        # 4. Perform Chunking Split
        splitter = RecursiveTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        ids = []
        documents = []
        metadatas = []
        
        ingest_time = time.time()
        chunk_idx = 0
        
        for page in pages:
            text = page["text"]
            page_num = page["page_number"]
            
            chunks = splitter.split_text(text)
            for chunk in chunks:
                chunk_id = f"{doc_id}_c{chunk_idx}"
                ids.append(chunk_id)
                documents.append(chunk)
                metadatas.append({
                    "document_id": doc_id,
                    "filename": filename,
                    "document_name": filename,
                    "source_path": abs_path,
                    "source": abs_path,
                    "page_number": page_num,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_idx,
                    "ingested_at": ingest_time,
                    "embedding_model": getattr(self.embedding_model, "model_name", "all-MiniLM-L6-v2"),
                    "is_mock": getattr(self.embedding_model, "is_mock", False),
                    "owner_id": owner_id if owner_id is not None else -1,
                    "owner_username": owner_username if owner_username is not None else ""
                })
                chunk_idx += 1
                
        # 5. Insert to vector index
        if ids:
            try:
                self.collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
                logger.info(f"Ingested document '{filename}' successfully ({chunk_idx} chunks indexed).")
                
                AuditLogger.log_event(
                    action="DOCUMENT_INGEST",
                    component="rag.pipeline",
                    status="success",
                    resource=filename,
                    metadata={"filename": filename, "file_size": os.path.getsize(abs_path), "chunk_count": chunk_idx}
                )
            except Exception as e:
                AuditLogger.log_event(
                    action="DOCUMENT_INGEST",
                    component="rag.pipeline",
                    status="failure",
                    resource=filename,
                    metadata={"filename": filename, "error_category": "vector_insert_failure"}
                )
                raise e
            
        return doc_id

    def search(
        self, 
        query: str, 
        top_k: int = 3, 
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Queries the persistent database, matches vectors, and returns grounded passage text metadata with ownership filters."""
        from backend.security.audit import AuditLogger
        import time
        start_time = time.perf_counter()
        
        if not query or not query.strip():
            AuditLogger.log_event(
                action="RAG_SEARCH",
                component="rag.pipeline",
                status="failure",
                metadata={"error_category": "empty_query"}
            )
            return []

        # Return empty list if collection has no items (prevents Chroma warnings)
        if self.collection.count() == 0:
            AuditLogger.log_event(
                action="RAG_SEARCH",
                component="rag.pipeline",
                status="success",
                metadata={"query_length": len(query), "chunk_count": 0}
            )
            return []

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=filter_metadata
            )
        except Exception as e:
            AuditLogger.log_event(
                action="RAG_SEARCH",
                component="rag.pipeline",
                status="failure",
                metadata={"query_length": len(query), "error_category": "query_failure"}
            )
            logger.error(f"ChromaDB similarity query run failed: {e}")
            return []

        formatted_results = []
        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)
            
            for idx in range(len(ids)):
                formatted_results.append({
                    "chunk_id": ids[idx],
                    "text": docs[idx],
                    "metadata": metas[idx],
                    "distance": distances[idx]
                })
                
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        AuditLogger.log_event(
            action="RAG_SEARCH",
            component="rag.pipeline",
            status="success",
            duration_ms=duration_ms,
            metadata={"query_length": len(query), "chunk_count": len(formatted_results), "duration_ms": duration_ms}
        )
                
        return formatted_results

    def delete_document(self, doc_id: str) -> None:
        """Deletes all chunks associated with a specific document ID."""
        existing = self.collection.get(
            where={"document_id": doc_id}
        )
        if not existing or not existing.get("ids"):
            raise ValueError(f"Document ID '{doc_id}' was not found in the vector store database.")
            
        self.collection.delete(
            where={"document_id": doc_id}
        )
        logger.info(f"Successfully deleted document ID '{doc_id}' from vector store database.")

    def list_documents(self) -> List[Dict[str, Any]]:
        """Retrieves list of all unique documents currently indexed in vector store database."""
        if self.collection.count() == 0:
            return []
            
        data = self.collection.get()
        if not data or not data.get("metadatas"):
            return []
            
        seen_docs = {}
        for meta in data["metadatas"]:
            doc_id = meta["document_id"]
            if doc_id not in seen_docs:
                seen_docs[doc_id] = {
                    "document_id": doc_id,
                    "filename": meta["filename"],
                    "source_path": meta["source_path"],
                    "ingested_at": meta["ingested_at"],
                    "owner_id": meta.get("owner_id") if meta.get("owner_id") is not None else -1,
                    "owner_username": meta.get("owner_username") if meta.get("owner_username") is not None else ""
                }
        return list(seen_docs.values())
