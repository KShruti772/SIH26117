from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uuid
import logging
from backend.app.config.settings import settings
from backend.security.database import init_db
from backend.security.auth_router import router as auth_router
from backend.security.audit import request_id_var, AuditLogger, get_request_id
from backend.security.dependencies import RoleChecker, get_current_user
from pydantic import BaseModel, Field
import os

from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager, RuntimeUnavailableError
from backend.rag.embeddings import MockEmbeddingModel, LocalTransformerEmbeddingModel
from backend.rag.pipeline import AegisRagService
from backend.tools.code_sandbox.sandbox import SubprocessSandbox
from backend.app.verification.verifier import GroundingVerifier, make_grounding_verify_callback
from backend.agents.controller.agent import AgentController

# Initialize authentication database tables
init_db()

# Setup shared agent controller dependencies
registry_manager = ModelRegistryManager("backend/models/registry/registry.json")
loader_manager = ModelLoaderManager(registry_manager)

# In-memory mock/local embedding model fallback helper
embedding_path = os.path.join(settings.MODEL_DIR, "all-MiniLM-L6-v2")
try:
    if os.path.exists(embedding_path):
        embedding_model = LocalTransformerEmbeddingModel(embedding_path)
    else:
        embedding_model = MockEmbeddingModel()
except Exception:
    embedding_model = MockEmbeddingModel()

rag_service = AegisRagService(
    embedding_model=embedding_model,
    persist_directory=settings.VECTOR_DB_PATH
)
sandbox_service = SubprocessSandbox()
verifier = GroundingVerifier()
verify_callback = make_grounding_verify_callback(verifier)

agent_controller = AgentController(
    registry_manager=registry_manager,
    loader_manager=loader_manager,
    rag_service=rag_service,
    sandbox_service=sandbox_service,
    verify_callback=verify_callback
)

app = FastAPI(
    title="AEGIS Sovereign AI Workbench",
    description="On-Premise Agentic AI Workbench for Confidential Industrial Work",
    version="0.1.0"
)

# CORS Configuration using loaded environment settings
origins = settings.CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Correlation request-id middleware
@app.middleware("http")
async def add_request_id_header(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_var.set(req_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        request_id_var.reset(token)

app.include_router(auth_router)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)

class ModelSelectRequest(BaseModel):
    model_id: str = Field(..., min_length=1)

@app.post("/chat", tags=["Agent Operations"])
async def run_chat(payload: ChatRequest, current_user = Depends(get_current_user)):
    """Runs a multi-step sovereign agent query using local models, sandboxes, and verifiers."""
    from fastapi import HTTPException
    try:
        res = await agent_controller.run(payload.message, current_user=current_user)
        req_id = get_request_id()
        
        sources = []
        verification = None
        
        if res.get("plan"):
            plan_data = res["plan"]
            for step in plan_data.get("steps", []):
                # RAG search step
                if step.get("capability") == "text_generation" and step.get("input", {}).get("action") == "rag_search":
                    output_data = step.get("output")
                    if isinstance(output_data, list):
                        for chunk in output_data:
                            sources.append({
                                "filename": chunk.get("metadata", {}).get("filename", "Unknown Document"),
                                "page_number": chunk.get("metadata", {}).get("page_number", 1)
                            })
                # Citations verification step
                if step.get("verification_result") and step.get("verification_result") != "PASS":
                    verification = step["verification_result"]
                    
        # Add model_info dynamically
        active_id = await loader_manager.get_current_model_id() or loader_manager.current_model_id or "qwen2.5-3b-instruct"
        inference_mode = "real"
        if res.get("plan", {}).get("inference_mode", "real") == "mock" or (
            loader_manager.current_model_id == active_id and not await loader_manager.is_runtime_available()
        ):
            inference_mode = "mock"

        return {
            "success": res["success"],
            "answer": res["plan"]["final_output"] if res["success"] else (res["error"] or "Agent execution failed."),
            "sources": sources,
            "verification": verification or "PASS",
            "request_id": req_id,
            "duration_ms": res["duration_ms"],
            "model_info": {
                "model_id": active_id,
                "inference_mode": inference_mode
            }
        }
    except Exception as e:
        import logging
        logging.getLogger("aegis.app").error(f"Chat route exception: {e}")
        raise HTTPException(
            status_code=500,
            detail="The sovereign node encountered an unexpected fault during agent execution."
        )


@app.get("/audit", tags=["System Audit"])
async def get_audit_logs(
    action: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    request_id: Optional[str] = None,
    current_user = Depends(RoleChecker(["admin"]))
):
    """Retrieves system audit logs. Restricted to administrator role only."""
    logs = AuditLogger.query_audit_logs(
        action=action,
        username=username,
        status=status,
        request_id=request_id
    )
    return logs

@app.get("/", tags=["General"])
async def root():
    return {
        "application": "AEGIS Sovereign AI Workbench",
        "description": "On-Premise Agentic AI Workbench for Confidential Industrial Work",
        "status": "running",
        "version": "0.1.0"
    }

@app.get("/documents", tags=["RAG Operations"])
async def get_documents(current_user = Depends(get_current_user)):
    """Retrieves all indexed documents in the local vector store, enforcing ownership boundaries."""
    docs = rag_service.list_documents()
    filtered = []
    is_admin = current_user.get("role") == "admin"
    for d in docs:
        doc_owner_id = d.get("owner_id")
        # Legacy documents (owner_id = -1 or None) are NOT visible to normal users
        # Admins can view all documents
        if is_admin or (doc_owner_id is not None and doc_owner_id == current_user.get("id")):
            filtered.append({
                "id": d["document_id"],
                "filename": d["filename"],
                "status": "indexed",
                "uploaded_at": d["ingested_at"]
            })
    return filtered

@app.post("/documents/upload", tags=["RAG Operations"])
async def upload_document(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user)
):
    """Saves and indexes an uploaded TXT or PDF document inside the local workspace."""
    import re
    import time
    
    # 1. Reject empty files
    content = await file.read()
    file_size = len(content)
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty files are not allowed.")
        
    # 2. Reject oversized files (>10MB)
    max_size = 10 * 1024 * 1024  # 10 MB
    if file_size > max_size:
        raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10MB.")
        
    # 3. Allowed extensions check (.pdf, .txt)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".txt", ".pdf"]:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file extension. Only plain text (.txt) and PDF (.pdf) documents are supported."
        )
        
    # 4. Filename sanitization to protect against directory traversal
    base_name = os.path.basename(file.filename)
    # Strip dangerous characters, leaving only alphanumeric, dot, dashes, and underscores
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', base_name)
    if not clean_name or clean_name in [".", ".."]:
        clean_name = f"uploaded_document_{int(time.time())}{ext}"
        
    # 5. Secure target storage location inside the workspace
    upload_dir = os.path.abspath("data/knowledge_base")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Prefix with a random token to prevent namespace collision attacks
    target_filename = f"{uuid.uuid4().hex}_{clean_name}"
    target_path = os.path.join(upload_dir, target_filename)
    
    # Path traversal validation guard
    if not os.path.abspath(target_path).startswith(upload_dir):
        raise HTTPException(status_code=400, detail="Path traversal attempt blocked.")
        
    try:
        # Write to local file system
        with open(target_path, "wb") as f:
            f.write(content)
            
        # 6. Ingest and calculate vector embeddings
        doc_id = rag_service.ingest_document(
            target_path,
            owner_id=current_user.get("id"),
            owner_username=current_user.get("username")
        )
        
        # Log DOCUMENT_UPLOADED and DOCUMENT_INDEXED
        AuditLogger.log_event(
            action="DOCUMENT_UPLOADED",
            component="app.main",
            status="success",
            resource=clean_name,
            metadata={"filename": clean_name, "owner_id": current_user.get("id")}
        )
        AuditLogger.log_event(
            action="DOCUMENT_INDEXED",
            component="app.main",
            status="success",
            resource=clean_name,
            metadata={"filename": clean_name, "owner_id": current_user.get("id"), "id": doc_id}
        )
        
        return {
            "id": doc_id,
            "filename": clean_name,
            "status": "indexed",
            "uploaded_at": int(time.time())
        }
    except Exception as e:
        # Clean up files on disk upon validation failure
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass
        # Suppress internal raw trace, returning safe user-facing message
        logging.getLogger("aegis.app").error(f"Ingestion failure: {e}")
        raise HTTPException(status_code=500, detail="parsing failed or file is corrupted")

@app.post("/documents/{id}/index", tags=["RAG Operations"])
async def reindex_document(id: str, current_user = Depends(get_current_user)):
    """Triggers manual re-indexing of a saved document file by ID, enforcing ownership."""
    docs = rag_service.list_documents()
    doc_file_path = None
    doc_owner_id = None
    doc_filename = "unknown"
    for d in docs:
        if d["document_id"] == id:
            doc_file_path = d["source_path"]
            doc_owner_id = d.get("owner_id")
            doc_filename = d["filename"]
            break
            
    if not doc_file_path or not os.path.exists(doc_file_path):
        raise HTTPException(status_code=404, detail="The requested document file could not be found on the server.")
        
    # Authorization checks: owner or admin role
    is_admin = current_user.get("role") == "admin"
    if not is_admin and (doc_owner_id is None or doc_owner_id != current_user.get("id")):
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_DENIED",
            component="app.main",
            status="failure",
            resource=doc_filename,
            metadata={"filename": doc_filename, "owner_id": doc_owner_id, "attempted_by": current_user.get("id"), "operation": "reindex"}
        )
        raise HTTPException(status_code=403, detail="Access denied. You do not own this document.")
        
    try:
        # Delete old vectors
        rag_service.delete_document(id)
        # Re-index preserving metadata
        new_doc_id = rag_service.ingest_document(
            doc_file_path,
            owner_id=doc_owner_id,
            owner_username=current_user.get("username")
        )
        
        # Log DOCUMENT_INDEXED
        AuditLogger.log_event(
            action="DOCUMENT_INDEXED",
            component="app.main",
            status="success",
            resource=doc_filename,
            metadata={"filename": doc_filename, "owner_id": doc_owner_id, "id": new_doc_id}
        )
        
        return {
            "id": new_doc_id,
            "status": "indexed",
            "message": "Document re-indexed successfully."
        }
    except Exception as e:
        logging.getLogger("aegis.app").error(f"Re-indexing failed: {e}")
        raise HTTPException(status_code=500, detail="Document re-indexing failed.")

@app.delete("/documents/{id}", tags=["RAG Operations"])
async def delete_document(id: str, current_user = Depends(get_current_user)):
    """Deletes vector references and removes the physical document from the disk, enforcing ownership."""
    docs = rag_service.list_documents()
    doc_file_path = None
    doc_filename = "unknown"
    doc_owner_id = None
    for d in docs:
        if d["document_id"] == id:
            doc_file_path = d["source_path"]
            doc_filename = d["filename"]
            doc_owner_id = d.get("owner_id")
            break
            
    if not doc_file_path:
        raise HTTPException(status_code=404, detail="The requested document could not be found.")
        
    # Authorization checks: owner or admin role
    is_admin = current_user.get("role") == "admin"
    if not is_admin and (doc_owner_id is None or doc_owner_id != current_user.get("id")):
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_DENIED",
            component="app.main",
            status="failure",
            resource=doc_filename,
            metadata={"filename": doc_filename, "owner_id": doc_owner_id, "attempted_by": current_user.get("id"), "operation": "delete"}
        )
        raise HTTPException(status_code=403, detail="Access denied. You do not own this document.")
        
    try:
        # 1. Delete vector database mappings
        rag_service.delete_document(id)
        
        # 2. Delete physical storage document file
        if os.path.exists(doc_file_path):
            os.remove(doc_file_path)
            
        # 3. Append to system audit log ledger using the new action type
        AuditLogger.log_event(
            action="DOCUMENT_DELETED",
            component="app.main",
            status="success",
            resource=doc_filename,
            metadata={"filename": doc_filename, "owner_id": doc_owner_id, "deleted_by": current_user.get("id")}
        )
        return {
            "status": "success",
            "message": f"Document '{doc_filename}' successfully removed."
        }
    except Exception as e:
        logging.getLogger("aegis.app").error(f"Document delete failure: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document from storage.")

@app.get("/models", tags=["Model Operations"])
async def get_models(current_user = Depends(get_current_user)):
    """Retrieves list of all configured model profiles in the registry."""
    return registry_manager.get_all_models(include_disabled=False)

@app.get("/models/current", tags=["Model Operations"])
async def get_current_model(current_user = Depends(get_current_user)):
    """Retrieves the currently selected/active model profile."""
    curr_id = await loader_manager.get_current_model_id()
    if not curr_id:
        curr_id = loader_manager.current_model_id
    if not curr_id:
        curr_id = "qwen2.5-3b-instruct"
        
    try:
        return registry_manager.get_model(curr_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Current model profile not found in registry.")

@app.post("/models/select", tags=["Model Operations"])
async def select_model(payload: ModelSelectRequest, current_user = Depends(get_current_user)):
    """Selects and loads a model into local VRAM, with simulated development fallbacks."""
    try:
        res = await loader_manager.switch_model(payload.model_id)
        loader_manager.current_model_id = payload.model_id
        return res
    except RuntimeUnavailableError as e:
        if settings.APP_ENV == "development":
            loader_manager.current_model_id = payload.model_id
            try:
                profile = registry_manager.get_model(payload.model_id)
                runtime_name = profile["runtime_model_name"]
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid model_id.")
                
            return {
                "status": "success",
                "model_id": payload.model_id,
                "active_model": runtime_name,
                "details": "simulated_load"
            }
        raise HTTPException(status_code=503, detail="Local inference runtime is offline or unreachable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.APP_ENV == "development")
    )
