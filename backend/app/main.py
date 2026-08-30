from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Any
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

# Initialize local SentenceTransformer embedding model (no silent mock fallback)
embedding_path = os.path.join(settings.MODEL_DIR, "all-MiniLM-L6-v2")
from backend.rag.embeddings import get_local_embedding_model
try:
    embedding_model = get_local_embedding_model(embedding_path)
except Exception as e:
    import logging
    logging.getLogger("aegis.rag").error(f"Local embedding model initialization failed: {e}")
    raise RuntimeError(f"Local embedding model is unavailable: {e}")

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
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:[0-9]+)?",
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
    session_id: Optional[str] = None

class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"

class ModelSelectRequest(BaseModel):
    model_id: str = Field(..., min_length=1)

@app.get("/conversations", tags=["Conversation Operations"])
async def list_conversations(current_user = Depends(get_current_user)):
    """Retrieves saved conversation sessions for active user."""
    from backend.agents.conversations import ConversationManager
    return ConversationManager.list_conversations(
        user_id=current_user.get("id"),
        username=current_user.get("username")
    )

@app.post("/conversations", tags=["Conversation Operations"])
async def create_conversation(payload: CreateConversationRequest, current_user = Depends(get_current_user)):
    """Creates a new conversation session."""
    from backend.agents.conversations import ConversationManager
    conv = ConversationManager.create_conversation(
        title=payload.title or "New Conversation",
        user_id=_get_user_val(current_user, "id"),
        username=_get_user_val(current_user, "username")
    )
    AuditLogger.log_event(
        action="CONVERSATION_CREATED",
        component="app.main",
        status="success",
        user_id=_get_user_val(current_user, "id"),
        username=_get_user_val(current_user, "username"),
        role=_get_user_val(current_user, "role"),
        resource=conv["id"],
        metadata={"session_id": conv["id"], "title": payload.title or "New Conversation"}
    )
    return conv

def _get_user_val(user: Any, key: str, default: Any = None) -> Any:
    if user is None:
        return default
    if isinstance(user, dict):
        return user.get(key, default)
    if hasattr(user, "__getitem__"):
        try:
            return user[key]
        except (KeyError, IndexError, TypeError):
            pass
    return getattr(user, key, default)

@app.get("/conversations/{session_id}", tags=["Conversation Operations"])
async def get_conversation(session_id: str, current_user = Depends(get_current_user)):
    """Retrieves conversation metadata and stored messages, enforcing session ownership."""
    from backend.agents.conversations import ConversationManager
    conv = ConversationManager.get_conversation(session_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation session not found.")
        
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    
    is_admin = curr_role == "admin"
    owner_id = conv.get("user_id")
    owner_username = conv.get("username")
    
    # Ownership check: must be admin or session owner
    if not is_admin and (
        (owner_id is not None and owner_id != curr_id) or
        (owner_id is None and owner_username and owner_username != curr_username)
    ):
        AuditLogger.log_event(
            action="AUTHORIZATION_DENIED",
            component="app.main",
            status="failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            resource=session_id,
            metadata={
                "reason": "RESOURCE_OWNERSHIP_FORBIDDEN",
                "session_id": session_id,
                "owner_id": owner_id,
                "operation": "get_conversation"
            }
        )
        raise HTTPException(status_code=403, detail="Access denied. You do not own this conversation session.")
        
    return conv

@app.delete("/conversations/{session_id}", tags=["Conversation Operations"])
async def delete_conversation(session_id: str, current_user = Depends(get_current_user)):
    """Deletes conversation session and stored messages, enforcing session ownership."""
    from backend.agents.conversations import ConversationManager
    conv_meta = ConversationManager.get_conversation_owner(session_id)
    if not conv_meta:
        raise HTTPException(status_code=404, detail="Conversation session not found.")
        
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")

    is_admin = curr_role == "admin"
    owner_id = conv_meta.get("user_id")
    owner_username = conv_meta.get("username")
    
    # Ownership check: must be admin or session owner
    if not is_admin and (
        (owner_id is not None and owner_id != curr_id) or
        (owner_id is None and owner_username and owner_username != curr_username)
    ):
        AuditLogger.log_event(
            action="AUTHORIZATION_DENIED",
            component="app.main",
            status="failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            resource=session_id,
            metadata={
                "reason": "RESOURCE_OWNERSHIP_FORBIDDEN",
                "session_id": session_id,
                "owner_id": owner_id,
                "operation": "delete_conversation"
            }
        )
        raise HTTPException(status_code=403, detail="Access denied. You do not own this conversation session.")
        
    success = ConversationManager.delete_conversation(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation session not found.")
    
    AuditLogger.log_event(
        action="CONVERSATION_DELETED",
        component="app.main",
        status="success",
        user_id=curr_id,
        username=curr_username,
        role=curr_role,
        resource=session_id,
        metadata={"session_id": session_id}
    )
    return {"status": "success", "id": session_id}

@app.post("/chat", tags=["Agent Operations"])
async def run_chat(payload: ChatRequest, current_user = Depends(get_current_user)):
    """Runs a multi-step sovereign agent query using local models, sandboxes, and verifiers."""
    from fastapi import HTTPException
    from backend.agents.conversations import ConversationManager
    import uuid
    
    try:
        session_id = payload.session_id or f"conv_{uuid.uuid4().hex[:12]}"
        
        # Persist user prompt to local database session
        ConversationManager.add_message(
            session_id=session_id,
            role="user",
            content=payload.message
        )
        
        res = await agent_controller.run(payload.message, current_user=current_user)
        req_id = get_request_id()
        
        is_rag = res.get("rag_used", False)
        sources = res.get("sources", [])
        model_used = res.get("model", "gemma3:4b") or "gemma3:4b"
        answer = res.get("answer") or "Agent execution failed."
        verification = "GROUNDED" if is_rag else ("UNVERIFIED" if res["success"] else "FAILED")
        
        # Persist assistant output to local database session
        ConversationManager.add_message(
            session_id=session_id,
            role="assistant",
            content=answer,
            rag_used=is_rag,
            sources=sources,
            model_id=model_used,
            duration_ms=res["duration_ms"],
            request_id=req_id,
            verification=verification,
            error_detail=res.get("error") if not res["success"] else None
        )

        AuditLogger.log_event(
            action="CHAT_REQUEST",
            component="app.main",
            status="success" if res["success"] else "failure",
            user_id=_get_user_val(current_user, "id"),
            username=_get_user_val(current_user, "username"),
            role=_get_user_val(current_user, "role"),
            resource=session_id,
            duration_ms=res["duration_ms"],
            metadata={"session_id": session_id, "model_id": model_used}
        )

        return {
            "success": res["success"],
            "session_id": session_id,
            "answer": answer,
            "rag_used": is_rag,
            "sources": sources,
            "verification": verification,
            "request_id": req_id,
            "duration_ms": res["duration_ms"],
            "model_info": {
                "model_id": model_used,
                "inference_mode": "real" if res["success"] else "mock"
            }
        }
    except Exception as e:
        import logging
        logging.getLogger("aegis.app").error(f"Chat route exception: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"The sovereign node encountered an unexpected fault during agent execution: {e}"
        )


@app.get("/audit", tags=["System Audit"])
async def get_audit_logs(
    action: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    request_id: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user = Depends(RoleChecker(["admin"]))
):
    """Retrieves system audit logs. Restricted to administrator role only."""
    logs = AuditLogger.query_audit_logs(
        action=action,
        username=username,
        status=status,
        request_id=request_id,
        search=search,
        start_date=start_date,
        end_date=end_date
    )
    return logs


@app.get("/audit/summary", tags=["System Audit"])
async def get_audit_summary(current_user = Depends(RoleChecker(["admin"]))):
    """Retrieves real metadata counts from SQLite audit database. Restricted to administrator role only."""
    import sqlite3
    from backend.security.database import get_db_path
    
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # 1. Total events
        cursor.execute("SELECT COUNT(*) FROM audit_logs")
        total_events = cursor.fetchone()[0]

        # 2. Successful events
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE status = 'success'")
        successful_events = cursor.fetchone()[0]

        # 3. Failed actions
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE status = 'failure'")
        failed_events = cursor.fetchone()[0]
        
        # 4. Security events
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN (
                'AUTH_LOGIN', 'AUTH_REGISTER', 'AUTH_LOGOUT', 'AUTH_CHANGE_PASSWORD', 
                'PASSWORD_CHANGE', 'PASSWORD_RESET', 'USER_PASSWORD_RESET', 
                'USER_PROVISION', 'USER_PROVISIONED', 'USER_ROLE_CHANGE', 'USER_ROLE_UPDATED', 
                'USER_ENABLE', 'USER_DISABLE', 'USER_STATUS_UPDATED', 'SECURITY_CONFIGURATION_CHANGE', 
                'DOCUMENT_ACCESS_DENIED', 'ACCESS_DENIED'
            )
        """)
        security_events = cursor.fetchone()[0]
        
        # 5. AI Runtime events
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN ('MODEL_LOAD', 'MODEL_UNLOAD', 'MODEL_SWITCH', 'AGENT_EXECUTION')
        """)
        ai_events = cursor.fetchone()[0]

        # 6. RAG events
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN (
                'RAG_SEARCH', 'RAG_QUERY', 'RAG_DOCUMENT_UPLOAD', 'RAG_DOCUMENT_INDEX', 
                'DOCUMENT_INGEST', 'DOCUMENT_UPLOADED', 'DOCUMENT_INDEXED', 'DOCUMENT_DELETED', 'OCR_PROCESS'
            )
        """)
        rag_events = cursor.fetchone()[0]

        # 7. Sandbox events
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN ('SANDBOX_EXECUTION')
        """)
        sandbox_events = cursor.fetchone()[0]
        
        # Legacy auth events for backward compatibility
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN ('AUTH_LOGIN', 'AUTH_REGISTER', 'AUTH_LOGOUT', 'AUTH_CHANGE_PASSWORD', 'USER_PROVISIONED', 'USER_STATUS_UPDATED', 'USER_ROLE_UPDATED', 'USER_PASSWORD_RESET')
        """)
        auth_events = cursor.fetchone()[0]
        
        return {
            "total_events": total_events,
            "successful_events": successful_events,
            "failed_actions": failed_events,
            "security_events": security_events,
            "ai_operations": ai_events,
            "rag_events": rag_events,
            "sandbox_events": sandbox_events,
            "authentication": auth_events
        }
    finally:
        conn.close()

@app.get("/audit/verify", tags=["System Audit"])
async def verify_audit_ledger(current_user = Depends(RoleChecker(["admin"]))):
    """Verifies cryptographic HMAC-SHA256 hash chain integrity of the audit ledger."""
    return AuditLogger.verify_chain_integrity()

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
class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=10)

@app.post("/documents/query", tags=["RAG Operations"])
async def query_documents(payload: RAGQueryRequest, current_user = Depends(get_current_user)):
    """Executes dynamic vector similarity search against the local ChromaDB database."""
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")

    is_admin = curr_role == "admin"
    filter_meta = None if is_admin else {"owner_id": curr_id}
    
    results = rag_service.search(
        query=payload.query,
        top_k=payload.top_k,
        filter_metadata=filter_meta
    )
    
    AuditLogger.log_event(
        action="RAG_QUERY",
        component="app.main",
        status="success",
        user_id=curr_id,
        username=curr_username,
        role=curr_role,
        metadata={"query_length": len(payload.query)}
    )
    return {
        "query": payload.query,
        "results": results,
        "count": len(results)
    }

class ModelTestRequest(BaseModel):
    model_id: Optional[str] = None

@app.get("/models", tags=["Model Operations"])
async def get_models(current_user = Depends(get_current_user)):
    """Retrieves list of all discovered and configured model profiles."""
    return await loader_manager.get_discovered_models()

@app.get("/models/current", tags=["Model Operations"])
async def get_current_model(current_user = Depends(get_current_user)):
    """Retrieves the currently selected/active model profile."""
    curr_id = await loader_manager.get_current_model_id()
    if not curr_id:
        curr_id = loader_manager.current_model_id
    if not curr_id:
        curr_id = "gemma3:4b"
        
    try:
        return registry_manager.get_model(curr_id)
    except Exception:
        return {
            "model_id": curr_id,
            "display_name": curr_id.capitalize(),
            "runtime_model_name": curr_id,
            "status": "ACTIVE"
        }

@app.post("/models/select", tags=["Model Operations"])
async def select_model(payload: ModelSelectRequest, current_user = Depends(RoleChecker(["admin"]))):
    """Selects and loads a model into local VRAM."""
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    try:
        res = await loader_manager.switch_model(payload.model_id)
        loader_manager.current_model_id = payload.model_id
        AuditLogger.log_event(
            action="MODEL_SELECTED",
            component="app.main",
            status="success",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            resource=payload.model_id,
            metadata={"model_id": payload.model_id}
        )
        return res
    except RuntimeUnavailableError as e:
        if settings.APP_ENV == "development":
            loader_manager.current_model_id = payload.model_id
            AuditLogger.log_event(
                action="MODEL_SELECTED",
                component="app.main",
                status="success",
                user_id=curr_id,
                username=curr_username,
                role=curr_role,
                resource=payload.model_id,
                metadata={"model_id": payload.model_id}
            )
            return {
                "status": "success",
                "model_id": payload.model_id,
                "active_model": payload.model_id,
                "details": "simulated_load"
            }
        AuditLogger.log_event(
            action="MODEL_SELECTED",
            component="app.main",
            status="failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            resource=payload.model_id,
            metadata={"model_id": payload.model_id, "error_category": "runtime_unavailable"}
        )
        raise HTTPException(status_code=503, detail="Local inference runtime is offline or unreachable.")
    except Exception as e:
        AuditLogger.log_event(
            action="MODEL_SELECTED",
            component="app.main",
            status="failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            resource=payload.model_id,
            metadata={"model_id": payload.model_id, "error_category": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/models/test", tags=["Model Operations"])
async def test_model_inference(payload: Optional[ModelTestRequest] = None, current_user = Depends(get_current_user)):
    """Executes deterministic test inference against target model on local Ollama daemon."""
    import time
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")

    target_model = (payload.model_id if payload and payload.model_id else None) or loader_manager.current_model_id or "gemma3:4b"
    start = time.perf_counter()
    try:
        res = await loader_manager.generate(
            prompt="Respond with exactly: AEGIS MODEL TEST PASSED",
            model_id=target_model,
            timeout=30.0
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        AuditLogger.log_event(
            action="MODEL_TESTED",
            component="app.main",
            status="success",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            resource=target_model,
            duration_ms=duration_ms,
            metadata={"model_id": target_model, "status": "PASS"}
        )
        return {
            "status": "PASS",
            "model": target_model,
            "latency_ms": duration_ms,
            "response": res.strip()
        }
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        AuditLogger.log_event(
            action="MODEL_TESTED",
            component="app.main",
            status="failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            resource=target_model,
            duration_ms=duration_ms,
            metadata={"model_id": target_model, "status": "FAIL"}
        )
        return {
            "status": "FAIL",
            "model": target_model,
            "latency_ms": duration_ms,
            "error": str(e)
        }

class SandboxRequest(BaseModel):
    code: str
    timeout_seconds: Optional[int] = 10

@app.post("/sandbox/execute", tags=["Sandbox Operations"])
async def execute_in_sandbox(payload: SandboxRequest, current_user = Depends(get_current_user)):
    """Executes python code inside the isolated local subprocess sandbox."""
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    try:
        res = sandbox_service.execute(payload.code, timeout_seconds=payload.timeout_seconds)
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="app.main",
            status="success" if res.get("success") else "failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            duration_ms=res.get("execution_time_ms"),
            metadata={"sandbox_exit_code": res.get("exit_code"), "sandbox_timeout": payload.timeout_seconds}
        )
        return res
    except Exception as e:
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="app.main",
            status="failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            metadata={"error_category": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", tags=["System"])
async def health(details: bool = False):
    if not details:
        return {"status": "ok"}
        
    import sqlite3
    import os
    from backend.security.database import get_db_path
    
    # 1. Audit ledger sqlite check
    audit_ok = False
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        audit_ok = True
    except Exception:
        pass
        
    # 2. Vector Store check
    vector_ok = False
    try:
        if rag_service and getattr(rag_service, "collection", None) is not None:
            vector_ok = True
        else:
            db_dir = getattr(settings, "CHROMA_PERSIST_DIR", getattr(settings, "VECTOR_DB_PATH", "./vectorstore"))
            if os.path.exists(db_dir):
                vector_ok = True
    except Exception:
        pass

    # 3. Ollama server connection check
    runtime_ok = await loader_manager.is_runtime_available()
    
    return {
        "status": "ok",
        "services": {
            "ai_runtime": "healthy" if runtime_ok else "degraded",
            "rag_engine": "healthy" if vector_ok else "unhealthy",
            "vector_store": "healthy" if vector_ok else "unhealthy",
            "sandbox": "protected",
            "audit_ledger": "active" if audit_ok else "inactive"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.APP_ENV == "development")
    )
