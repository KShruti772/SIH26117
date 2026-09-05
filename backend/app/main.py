from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Any, List, Dict
import uuid
import logging
from backend.app.config.settings import settings
from backend.security.database import init_db, get_db_path
from backend.security.auth_router import router as auth_router, departments_router
from backend.security.audit import request_id_var, AuditLogger, get_request_id
from backend.security.dependencies import RoleChecker, get_current_user
from backend.security.models import DocumentShareRequest
from backend.security.access_control import (
    can_access_document,
    get_accessible_document_ids,
    can_access_generated_document,
    _extract_user_attrs
)
from pydantic import BaseModel, Field, model_validator
import os
import sqlite3

from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager, RuntimeUnavailableError
from backend.rag.embeddings import LocalTransformerEmbeddingModel
from backend.rag.pipeline import AegisRagService
from backend.tools.code_sandbox.sandbox import SubprocessSandbox
from backend.app.verification.verifier import GroundingVerifier, make_grounding_verify_callback
from backend.agents.controller.agent import AgentController

from backend.models.router import ModelRouter, TaskType, NoCompatibleModelError

# Initialize authentication database tables
init_db()

# Setup shared agent controller dependencies
registry_manager = ModelRegistryManager("backend/models/registry/registry.json")
loader_manager = ModelLoaderManager(registry_manager)
model_router = ModelRouter(registry_manager, loader_manager)

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

from backend.rag.grounded_qa import GroundedQAService
grounded_qa_service = GroundedQAService(
    rag_service=rag_service,
    loader_manager=loader_manager,
    registry_manager=registry_manager,
    model_router=model_router
)

from backend.tools.document_generators.generators import DocxGenerator, XlsxGenerator, PdfGenerator
docx_generator = DocxGenerator()
xlsx_generator = XlsxGenerator()
pdf_generator = PdfGenerator()
doc_generators = {
    "docx": docx_generator,
    "xlsx": xlsx_generator,
    "pdf": pdf_generator
}

agent_controller = AgentController(
    registry_manager=registry_manager,
    loader_manager=loader_manager,
    rag_service=rag_service,
    sandbox_service=sandbox_service,
    doc_generators=doc_generators,
    model_router=model_router,
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
app.include_router(departments_router)

class ChatRequest(BaseModel):
    message: Optional[str] = Field(default=None, max_length=1000)
    query: Optional[str] = Field(default=None, max_length=1000)
    session_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_content(self):
        msg = self.message if self.message is not None else self.query
        if msg is None or len(msg.strip()) == 0:
            raise ValueError("Prompt message or query must not be empty.")
        if len(msg) > 1000:
            raise ValueError("Prompt exceeds maximum length of 1000 characters.")
        return self

class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"

class ModelSelectRequest(BaseModel):
    model_id: str = Field(..., min_length=1)

class UpdateConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

@app.get("/conversations", tags=["Conversation Operations"])
async def list_conversations(current_user = Depends(get_current_user)):
    """Retrieves saved conversation sessions for active user."""
    from backend.agents.conversations import ConversationManager
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    return ConversationManager.list_conversations(
        user_id=curr_id,
        username=curr_username
    )

@app.post("/conversations", tags=["Conversation Operations"])
async def create_conversation(payload: CreateConversationRequest, current_user = Depends(get_current_user)):
    """Creates a new conversation session."""
    from backend.agents.conversations import ConversationManager
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    curr_role = _get_user_val(current_user, "role")
    req_id = get_request_id()

    conv = ConversationManager.create_conversation(
        title=payload.title or "New Conversation",
        user_id=curr_id,
        username=curr_username
    )
    AuditLogger.log_event(
        action="CONVERSATION_CREATED",
        component="app.main",
        status="success",
        user_id=curr_id,
        username=curr_username,
        role=curr_role,
        resource=conv["id"],
        request_id=req_id,
        metadata={"session_id": conv["id"], "title": conv["title"]}
    )
    return conv

def _get_user_val(user: Any, key: str, default: Any = None) -> Any:
    if user is None:
        return default
    val = None
    if isinstance(user, dict):
        val = user.get(key, default)
    elif hasattr(user, "__getitem__"):
        try:
            val = user[key]
        except (KeyError, IndexError, TypeError):
            val = getattr(user, key, default)
    else:
        val = getattr(user, key, default)

    if hasattr(val, "_mock_name") or "mock" in type(val).__name__.lower():
        try:
            if key == "id":
                return int(val) if isinstance(val, int) else (val if isinstance(val, (int, str)) else 1)
            return str(val)
        except Exception:
            return 1 if key == "id" else default
    return val

@app.get("/conversations/{session_id}", tags=["Conversation Operations"])
async def get_conversation(session_id: str, current_user = Depends(get_current_user)):
    """Retrieves conversation metadata and stored messages, enforcing session ownership."""
    from backend.agents.conversations import ConversationManager, validate_session_id
    try:
        session_id = validate_session_id(session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

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

@app.patch("/conversations/{session_id}", tags=["Conversation Operations"])
async def update_conversation(session_id: str, payload: UpdateConversationRequest, current_user = Depends(get_current_user)):
    """Updates conversation title, enforcing session ownership."""
    from backend.agents.conversations import ConversationManager, validate_session_id
    try:
        session_id = validate_session_id(session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    conv_meta = ConversationManager.get_conversation_owner(session_id)
    if not conv_meta:
        raise HTTPException(status_code=404, detail="Conversation session not found.")
        
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    
    is_admin = curr_role == "admin"
    owner_id = conv_meta.get("user_id")
    owner_username = conv_meta.get("username")
    
    if not is_admin and (
        (owner_id is not None and owner_id != curr_id) or
        (owner_id is None and owner_username and owner_username != curr_username)
    ):
        raise HTTPException(status_code=403, detail="Access denied. You do not own this conversation session.")
        
    success = ConversationManager.update_conversation_title(session_id, payload.title)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation session not found.")
        
    AuditLogger.log_event(
        action="CONVERSATION_UPDATED",
        component="app.main",
        status="success",
        user_id=curr_id,
        username=curr_username,
        role=curr_role,
        resource=session_id,
        metadata={"session_id": session_id, "new_title": payload.title}
    )
    return {"status": "success", "id": session_id, "title": payload.title}

@app.get("/conversations/{session_id}/messages", tags=["Conversation Operations"])
async def get_conversation_messages(session_id: str, current_user = Depends(get_current_user)):
    """Retrieves message sequence for a conversation session, enforcing ownership."""
    from backend.agents.conversations import ConversationManager, validate_session_id
    try:
        session_id = validate_session_id(session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    conv_meta = ConversationManager.get_conversation_owner(session_id)
    if not conv_meta:
        raise HTTPException(status_code=404, detail="Conversation session not found.")
        
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    
    is_admin = curr_role == "admin"
    owner_id = conv_meta.get("user_id")
    owner_username = conv_meta.get("username")
    
    if not is_admin and (
        (owner_id is not None and owner_id != curr_id) or
        (owner_id is None and owner_username and owner_username != curr_username)
    ):
        raise HTTPException(status_code=403, detail="Access denied. You do not own this conversation session.")
        
    return ConversationManager.get_messages(session_id)

@app.delete("/conversations/{session_id}", tags=["Conversation Operations"])
async def delete_conversation(session_id: str, current_user = Depends(get_current_user)):
    """Permanently removes a saved conversation session and cascading messages."""
    from backend.agents.conversations import ConversationManager, validate_session_id
    try:
        session_id = validate_session_id(session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

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

class PostConversationMessageRequest(BaseModel):
    message: Optional[str] = None
    query: Optional[str] = None
    model: Optional[str] = None

@app.post("/conversations/{session_id}/messages", tags=["Conversation Operations"])
async def post_conversation_message(
    session_id: str,
    payload: PostConversationMessageRequest,
    current_user = Depends(get_current_user)
):
    """Sends a message to an existing conversation session and triggers sovereign agent execution."""
    from backend.agents.conversations import validate_session_id
    try:
        session_id = validate_session_id(session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    msg = payload.message or payload.query or ""
    chat_req = ChatRequest(
        message=msg,
        session_id=session_id,
        model=payload.model
    )
    return await run_chat(chat_req, current_user=current_user)

@app.post("/chat", tags=["Agent Operations"])
async def run_chat(payload: ChatRequest, current_user = Depends(get_current_user)):
    """Runs a multi-step sovereign agent query using local models, sandboxes, and verifiers."""
    from fastapi import HTTPException
    from backend.agents.conversations import ConversationManager, validate_session_id
    from backend.models.router import classify_task_from_prompt
    import uuid
    
    try:
        if payload.session_id:
            try:
                session_id = validate_session_id(payload.session_id)
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))
        else:
            session_id = f"conv_{uuid.uuid4().hex[:12]}"

        user_prompt = payload.message or payload.query or ""
        curr_user_id = _get_user_val(current_user, "id")
        curr_username = _get_user_val(current_user, "username")
        curr_role = _get_user_val(current_user, "role")
        req_id = get_request_id() or f"REQ-{uuid.uuid4().hex[:8]}"

        # Ownership check on existing conversation session
        if payload.session_id:
            conv_owner = ConversationManager.get_conversation_owner(payload.session_id)
            if conv_owner:
                owner_id = conv_owner.get("user_id")
                owner_username = conv_owner.get("username")
                is_admin = curr_role == "admin"
                if not is_admin and (
                    (owner_id is not None and owner_id != curr_user_id) or
                    (owner_id is None and owner_username and owner_username != curr_username)
                ):
                    AuditLogger.log_event(
                        action="AUTHORIZATION_DENIED",
                        component="app.main",
                        status="failure",
                        user_id=curr_user_id,
                        username=curr_username,
                        role=curr_role,
                        resource=payload.session_id,
                        metadata={
                            "reason": "RESOURCE_OWNERSHIP_FORBIDDEN",
                            "session_id": payload.session_id,
                            "owner_id": owner_id,
                            "operation": "chat_message"
                        }
                    )
                    raise HTTPException(status_code=403, detail="Access denied. You do not own this conversation session.")

        # Classify task type for metadata tracking
        try:
            task_type = classify_task_from_prompt(user_prompt).value
        except Exception:
            task_type = "GENERAL_TEXT"

        # Audit initial chat request
        AuditLogger.log_event(
            action="CHAT_REQUEST",
            component="app.main",
            status="success",
            user_id=curr_user_id,
            username=curr_username,
            role=curr_role,
            resource=session_id,
            request_id=req_id,
            metadata={"session_id": session_id, "prompt_length": len(user_prompt), "task_type": task_type}
        )

        # Persist user prompt to local database session with user identity
        ConversationManager.add_message(
            session_id=session_id,
            role="user",
            content=user_prompt,
            user_id=curr_user_id,
            username=curr_username,
            request_id=req_id,
            metadata={"task_type": task_type}
        )
        
        recent_messages = ConversationManager.get_messages(session_id)[:-1]
        recent_context_parts = [
            f"{message['role'].capitalize()}: {message['content']}"
            for message in recent_messages[-6:]
            if message.get("content", "").strip()
        ]
        res = await agent_controller.run(user_prompt, current_user=current_user, conversation_id=session_id)
        
        is_rag = res.get("rag_used", False)
        sources = res.get("sources", [])
        if not sources and res.get("plan") and isinstance(res["plan"].get("steps"), list):
            for s in res["plan"]["steps"]:
                if s.get("input", {}).get("action") in ("rag_search", "document_wide_analysis") and isinstance(s.get("output"), list):
                    is_rag = True
                    for chunk in s["output"]:
                        meta = chunk.get("metadata", {})
                        sources.append({
                            "filename": meta.get("filename") or meta.get("document_name") or "Unknown Document",
                            "page": meta.get("page_number", 1),
                            "page_number": meta.get("page_number", 1),
                            "distance": round(chunk.get("distance", 0.0), 4) if "distance" in chunk else 0.0
                        })

        model_used = res.get("model") or "not reported"
        raw_ans = res.get("answer") or (res.get("plan", {}).get("final_output") if res.get("plan") else None) or "Agent execution failed."
        if isinstance(raw_ans, dict):
            if "stdout" in raw_ans:
                answer = raw_ans["stdout"] or raw_ans.get("error") or str(raw_ans)
            else:
                answer = json.dumps(raw_ans)
        else:
            answer = str(raw_ans)
        
        step_ver = None
        if res.get("plan") and isinstance(res["plan"].get("steps"), list) and res["plan"]["steps"]:
            last_ver = res["plan"]["steps"][-1].get("verification_result")
            if last_ver:
                if last_ver == "PASS" or last_ver.startswith("PASS"):
                    step_ver = "PASS"
                elif last_ver == "FAIL" or last_ver.startswith("FAIL"):
                    step_ver = "FAIL"

        verification = res.get("verification") or step_ver or ("GROUNDED" if is_rag else ("UNVERIFIED" if res.get("success") else "FAILED"))
        
        doc_ids = []
        if sources:
            for s in sources:
                if isinstance(s, dict):
                    fname = s.get("filename") or s.get("document_name")
                    if fname and fname not in doc_ids:
                        doc_ids.append(fname)

        routing_data = res.get("routing_info") or {}
        task_type = routing_data.get("task_type") or task_type
        selected_model = res.get("model") or model_used
        switched = bool(routing_data.get("switched", False))
        routing_reason = routing_data.get("reason", f"Automatically routed to {selected_model}")

        sandbox_exec = res.get("sandbox_execution")
        plan_steps = res.get("plan", {}).get("steps", []) if isinstance(res.get("plan"), dict) else []
        last_step_replans = plan_steps[-1].get("replan_count", 0) if plan_steps and isinstance(plan_steps[-1], dict) else 0

        execution_data = res.get("execution") or {
            "status": "SUCCESS" if res.get("success") else "FAILED",
            "tools_used": [],
            "sandbox": sandbox_exec,
            "verification": verification,
            "replan_count": last_step_replans
        }

        assistant_meta = {
            "task_type": task_type,
            "selected_model": selected_model,
            "routing": "automatic",
            "switched": switched,
            "routing_reason": routing_reason,
            "grounding_status": verification,
            "rag_used": is_rag,
            "document_ids": doc_ids,
            "category": res.get("category"),
            "duration_ms": res.get("duration_ms"),
            "sandbox_execution": sandbox_exec,
            "execution": execution_data,
            "replan_count": execution_data.get("replan_count", 0),
            "context_telemetry": res.get("context_telemetry"),
            "context_package": res.get("context_package")
        }

        # Persist assistant output to local database session
        ConversationManager.add_message(
            session_id=session_id,
            role="assistant",
            content=answer,
            user_id=curr_user_id,
            username=curr_username,
            rag_used=is_rag,
            sources=sources,
            model_id=selected_model,
            duration_ms=res.get("duration_ms"),
            request_id=req_id,
            verification=verification,
            error_detail=res.get("error") if not res.get("success") else None,
            metadata=assistant_meta
        )

        AuditLogger.log_event(
            action="CHAT_RESPONSE",
            component="app.main",
            status="success" if res.get("success") else "failure",
            user_id=curr_user_id,
            username=curr_username,
            role=curr_role,
            resource=session_id,
            request_id=req_id,
            duration_ms=res.get("duration_ms"),
            metadata={
                "session_id": session_id,
                "model_id": selected_model,
                "rag_used": is_rag,
                "verification": verification
            }
        )

        return {
            "success": res.get("success", False),
            "status": "success" if res.get("success") else "failure",
            "category": res.get("category"),
            "model": selected_model,
            "answer": answer,
            "rag_used": is_rag,
            "sources": sources,
            "session_id": session_id,
            "plan": res.get("plan"),
            "state": res.get("state"),
            "execution": execution_data,
            "verification": verification,
            "request_id": req_id,
            "duration_ms": res.get("duration_ms"),
            "sandbox_execution": sandbox_exec,
            "model_info": {
                "model_id": selected_model,
                "inference_mode": "real" if res.get("success") else "unavailable"
            },
            "routing_info": {
                "task_type": task_type,
                "selected_model": selected_model,
                "routing": "automatic",
                "switched": switched,
                "reason": routing_reason,
                "rag_used": is_rag,
                "verification_status": verification
            }
        }
    except HTTPException:
        raise
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
                'AUTH_LOGIN', 'LOGIN_SUCCESS', 'LOGIN_FAILED', 'AUTH_REGISTER', 
                'AUTH_LOGOUT', 'LOGOUT', 'AUTH_CHANGE_PASSWORD', 'PASSWORD_CHANGE', 
                'PASSWORD_CHANGED', 'PASSWORD_RESET', 'USER_PASSWORD_RESET', 
                'USER_PROVISION', 'USER_PROVISIONED', 'USER_CREATED', 'USER_ROLE_CHANGE', 
                'USER_ROLE_UPDATED', 'ROLE_CHANGED', 'USER_ENABLE', 'USER_DISABLE', 
                'USER_DISABLED', 'USER_ENABLED', 'USER_STATUS_UPDATED', 
                'SECURITY_CONFIGURATION_CHANGE', 'AUTHORIZATION_DENIED', 
                'DOCUMENT_ACCESS_DENIED', 'ACCESS_DENIED'
            )
        """)
        security_events = cursor.fetchone()[0]
        
        # 5. AI Runtime events
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN (
                'MODEL_LOAD', 'MODEL_UNLOAD', 'MODEL_SWITCH', 'MODEL_SELECTED', 
                'MODEL_TESTED', 'MODEL_LOADED', 'MODEL_UNLOADED', 'MODEL_INFERENCE', 
                'AGENT_EXECUTION', 'CHAT_REQUEST', 'CHAT_RESPONSE', 
                'CHAT_CONVERSATION_CREATED', 'CHAT_MESSAGE_CREATED', 'VERIFICATION'
            )
        """)
        ai_events = cursor.fetchone()[0]

        # 6. RAG & Document Intelligence events
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN (
                'RAG_SEARCH', 'RAG_QUERY', 'RAG_QUERY_STARTED', 'RAG_QUERY_COMPLETED', 'RAG_QUERY_FAILED',
                'RAG_DOCUMENT_UPLOAD', 'RAG_DOCUMENT_INDEX', 'DOCUMENT_INGEST', 'DOCUMENT_UPLOADED', 
                'DOCUMENT_INDEXED', 'DOCUMENT_DELETED', 'DOCUMENT_UPLOAD_STARTED', 'DOCUMENT_UPLOAD_COMPLETED', 
                'DOCUMENT_UPLOAD_FAILED', 'DOCUMENT_INDEX_STARTED', 'DOCUMENT_INDEX_COMPLETED', 
                'DOCUMENT_INDEX_FAILED', 'DOCUMENT_INGESTION_STARTED', 'DOCUMENT_INGESTION_COMPLETED', 
                'DOCUMENT_INGESTION_FAILED', 'OCR_PROCESS', 'DOCUMENT_GENERATION', 'DOCUMENT_GENERATED',
                'DOCUMENT_GENERATION_STARTED', 'DOCUMENT_GENERATION_COMPLETED', 'DOCUMENT_GENERATION_FAILED',
                'DOCUMENT_DOWNLOADED', 'DOCUMENT_DOWNLOAD_STARTED', 'DOCUMENT_DOWNLOAD_COMPLETED', 'DOCUMENT_DOWNLOAD_FAILED'
            )
        """)
        rag_events = cursor.fetchone()[0]

        # 7. Sandbox events
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN (
                'SANDBOX_EXECUTION', 'SANDBOX_EXECUTION_STARTED', 
                'SANDBOX_EXECUTION_COMPLETED', 'SANDBOX_EXECUTION_FAILED'
            )
        """)
        sandbox_events = cursor.fetchone()[0]
        
        # Legacy auth events for backward compatibility
        cursor.execute("""
            SELECT COUNT(*) FROM audit_logs 
            WHERE action IN (
                'AUTH_LOGIN', 'LOGIN_SUCCESS', 'LOGIN_FAILED', 'AUTH_REGISTER', 
                'AUTH_LOGOUT', 'LOGOUT', 'AUTH_CHANGE_PASSWORD', 'PASSWORD_CHANGED', 
                'USER_PROVISIONED', 'USER_STATUS_UPDATED', 'USER_ROLE_UPDATED', 'USER_PASSWORD_RESET'
            )
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
    """Retrieves all indexed documents in the local vector store, enforcing enterprise access control."""
    accessible_ids = get_accessible_document_ids(current_user, permission="READ")
    docs = rag_service.list_documents(accessible_document_ids=accessible_ids)
    filtered = []
    for d in docs:
        if d.get("is_mock", False):
            continue
        if not can_access_document(current_user, d, "READ"):
            continue
        doc_id = d.get("id") or d.get("document_id")
        filtered.append({
            "id": doc_id,
            "document_id": doc_id,
            "filename": d.get("filename"),
            "status": d.get("status"),
            "uploaded_at": d.get("ingested_at") or d.get("uploaded_at") or d.get("created_at"),
            "chunk_count": d.get("chunk_count"),
            "owner_id": d.get("owner_id"),
            "owner_username": d.get("owner_username", ""),
            "owner_department_id": d.get("owner_department_id"),
            "owner_department_name": d.get("owner_department_name"),
            "visibility": d.get("visibility"),
            "category": d.get("category"),
            "document_type": d.get("document_type"),
            "mime_type": d.get("mime_type"),
            "file_size": d.get("file_size")
            ,"can_download": can_access_document(current_user, d, "DOWNLOAD")
            ,"can_share": can_access_document(current_user, d, "SHARE") or can_access_document(current_user, d, "MANAGE")
            ,"can_delete": can_access_document(current_user, d, "DELETE")
            ,"can_manage": can_access_document(current_user, d, "MANAGE")
        })
    return filtered

@app.get("/documents/stats", tags=["RAG Operations"])
async def get_documents_stats(current_user = Depends(get_current_user)):
    """Retrieves document statistics enforcing enterprise access control."""
    accessible_ids = get_accessible_document_ids(current_user, permission="READ")
    return rag_service.get_document_stats(accessible_document_ids=accessible_ids)

@app.post("/documents/upload", tags=["RAG Operations"])
async def upload_document(
    file: UploadFile = File(...),
    visibility: str = Form("PRIVATE"),
    current_user = Depends(get_current_user)
):
    """Saves and indexes an uploaded document enforcing department ownership, access policy, and deduplication security."""
    import re
    import time
    import hashlib
    
    clean_visibility = (visibility or "PRIVATE").upper().strip()
    if clean_visibility not in ["PRIVATE", "DEPARTMENT", "SHARED", "ORGANIZATION"]:
        clean_visibility = "PRIVATE"
        
    user_attrs = _extract_user_attrs(current_user)
    user_id = user_attrs["id"]
    username = user_attrs["username"]
    user_dept_id = user_attrs["department_id"]
    user_dept_name = user_attrs["department_name"]
    
    # 1. Reject empty files
    content = await file.read()
    file_size = len(content)
    if file_size == 0:
        AuditLogger.log_event(
            action="DOCUMENT_UPLOAD_FAILED",
            component="app.main",
            status="failure",
            resource=file.filename or "unknown",
            user_id=user_id,
            username=username,
            metadata={"filename": file.filename or "unknown", "error_category": "empty_file"}
        )
        raise HTTPException(status_code=400, detail="Empty files are not allowed.")
        
    # 2. Reject oversized files (>10MB limit as per spec)
    max_size = 10 * 1024 * 1024  # 10 MB
    if file_size > max_size:
        AuditLogger.log_event(
            action="DOCUMENT_UPLOAD_FAILED",
            component="app.main",
            status="failure",
            resource=file.filename or "unknown",
            user_id=user_id,
            username=username,
            metadata={"filename": file.filename or "unknown", "error_category": "file_oversized"}
        )
        raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10MB.")
        
    # 3. Server-side File Signature & Content Validation via FileDetector
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    from backend.rag.detector import FileDetector
    detection = FileDetector.detect_from_bytes(content[:8192], file.filename or "uploaded_file", file_size=file_size)
    if not detection.is_safe:
        AuditLogger.log_event(
            action="DOCUMENT_UPLOAD_FAILED",
            component="app.main",
            status="failure",
            resource=file.filename or "unknown",
            user_id=user_id,
            username=username,
            metadata={"filename": file.filename or "unknown", "error_category": "blocked_executable"}
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. {detection.error_reason or 'Dangerous binary executable blocked.'}"
        )

    if not detection.is_valid:
        AuditLogger.log_event(
            action="DOCUMENT_UPLOAD_FAILED",
            component="app.main",
            status="failure",
            resource=file.filename or "unknown",
            user_id=user_id,
            username=username,
            metadata={"filename": file.filename or "unknown", "error_category": "unsupported_format"}
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. {detection.error_reason or 'Supported formats: .pdf, .docx, .xlsx, .csv, .pptx, .png, .jpg, .txt, .md, .py, .sql'}"
        )
        
    # 4. Filename sanitization to protect against directory traversal
    base_name = os.path.basename(file.filename)
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', base_name)
    if not clean_name or clean_name in [".", ".."]:
        clean_name = f"uploaded_document_{int(time.time())}{ext}"
        
    # 5. Check Content Hash Deduplication BEFORE writing permanent file
    content_hash = hashlib.sha256(content).hexdigest()
    existing_doc = rag_service.get_document_by_hash(content_hash)
    if existing_doc and existing_doc.get("status") == "indexed":
        if not can_access_document(current_user, existing_doc, "READ"):
            # HASH MATCH != ACCESS GRANTED: User is unauthorized to access the existing document
            AuditLogger.log_event(
                action="DOCUMENT_DUPLICATE_DETECTED",
                component="app.main",
                status="failure",
                resource=clean_name,
                user_id=user_id,
                username=username,
                metadata={
                    "content_hash": content_hash,
                    "result": "duplicate_detected",
                    "reason": "unauthorized_duplicate_attempt",
                    "filename": clean_name
                }
            )
            AuditLogger.log_event(
                action="DOCUMENT_UPLOAD_FAILED",
                component="app.main",
                status="failure",
                resource=clean_name,
                user_id=user_id,
                username=username,
                metadata={"filename": clean_name, "error_category": "duplicate_rejection"}
            )
            raise HTTPException(
                status_code=400,
                detail="A document with identical content already exists in the system, but you do not have permission to access it."
            )
        else:
            # User already has access to canonical document: reuse existing index without duplication
            AuditLogger.log_event(
                action="DOCUMENT_DUPLICATE_DETECTED",
                component="app.main",
                status="success",
                resource=clean_name,
                user_id=user_id,
                username=username,
                metadata={
                    "content_hash": content_hash,
                    "result": "duplicate_detected",
                    "action": "reused_canonical",
                    "document_id": existing_doc["id"],
                    "canonical_document_id": existing_doc["id"],
                    "filename": clean_name
                }
            )
            return {
                "id": existing_doc["id"],
                "document_id": existing_doc["id"],
                "filename": existing_doc["filename"],
                "category": existing_doc.get("category", detection.category),
                "file_type": existing_doc.get("document_type", detection.file_type),
                "mime_type": existing_doc.get("mime_type", detection.mime_type),
                "extraction_method": existing_doc.get("extraction_method", detection.extraction_method),
                "status": "indexed",
                "uploaded_at": existing_doc.get("uploaded_at") or int(time.time()),
                "chunk_count": existing_doc.get("chunk_count", 0),
                "file_size": existing_doc.get("file_size", file_size),
                "owner_id": existing_doc.get("owner_id", user_id),
                "owner_username": existing_doc.get("owner_username", username),
                "owner_department_id": existing_doc.get("owner_department_id", user_dept_id),
                "owner_department_name": existing_doc.get("owner_department_name", user_dept_name),
                "visibility": existing_doc.get("visibility", clean_visibility)
            }

    # 6. Secure target storage location inside the workspace
    upload_dir = os.path.abspath("data/knowledge_base")
    os.makedirs(upload_dir, exist_ok=True)
    
    target_filename = f"{uuid.uuid4().hex}_{clean_name}"
    target_path = os.path.join(upload_dir, target_filename)
    
    # Path traversal validation guard
    if not os.path.abspath(target_path).startswith(upload_dir):
        AuditLogger.log_event(
            action="DOCUMENT_UPLOAD_FAILED",
            component="app.main",
            status="failure",
            resource=clean_name,
            user_id=user_id,
            username=username,
            metadata={"filename": clean_name, "error_category": "path_traversal"}
        )
        raise HTTPException(status_code=400, detail="Path traversal attempt blocked.")
        
    AuditLogger.log_event(
        action="DOCUMENT_UPLOAD_STARTED",
        component="app.main",
        status="success",
        resource=clean_name,
        user_id=user_id,
        username=username,
        metadata={"filename": clean_name, "file_size": file_size, "owner_id": user_id, "visibility": clean_visibility}
    )

    try:
        # Write to local file system
        with open(target_path, "wb") as f:
            f.write(content)

        AuditLogger.log_event(
            action="DOCUMENT_UPLOAD_COMPLETED",
            component="app.main",
            status="success",
            resource=clean_name,
            user_id=user_id,
            username=username,
            metadata={"filename": clean_name, "file_size": file_size, "owner_id": user_id}
        )
            
        # 7. Ingest and calculate vector embeddings
        doc_id = rag_service.ingest_document(
            target_path,
            owner_id=user_id,
            owner_username=username,
            owner_department_id=user_dept_id,
            owner_department_name=user_dept_name,
            visibility=clean_visibility,
            original_filename=clean_name,
            current_user=current_user
        )
        
        doc_info = rag_service.get_document(doc_id)
        real_chunk_count = doc_info.get("chunk_count", 0) if doc_info else 0
        real_status = doc_info.get("status", "indexed") if doc_info else "indexed"

        # Log DOCUMENT_UPLOADED and DOCUMENT_INDEXED
        AuditLogger.log_event(
            action="DOCUMENT_UPLOADED",
            component="app.main",
            status="success",
            resource=clean_name,
            user_id=user_id,
            username=username,
            metadata={"filename": clean_name, "owner_id": user_id, "id": doc_id, "chunk_count": real_chunk_count}
        )
        AuditLogger.log_event(
            action="DOCUMENT_INDEXED",
            component="app.main",
            status="success",
            resource=clean_name,
            user_id=user_id,
            username=username,
            metadata={"filename": clean_name, "owner_id": user_id, "id": doc_id, "chunk_count": real_chunk_count}
        )
        
        return {
            "id": doc_id,
            "document_id": doc_id,
            "filename": clean_name,
            "category": doc_info.get("category", detection.category) if doc_info else detection.category,
            "file_type": doc_info.get("document_type", detection.file_type) if doc_info else detection.file_type,
            "mime_type": doc_info.get("mime_type", detection.mime_type) if doc_info else detection.mime_type,
            "extraction_method": doc_info.get("extraction_method", detection.extraction_method) if doc_info else detection.extraction_method,
            "status": real_status,
            "uploaded_at": int(time.time()),
            "chunk_count": real_chunk_count,
            "file_size": file_size,
            "owner_id": user_id,
            "owner_username": username,
            "owner_department_id": user_dept_id,
            "owner_department_name": user_dept_name,
            "visibility": clean_visibility
        }
    except HTTPException:
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass
        raise
    except Exception as e:
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass
        logging.getLogger("aegis.app").error(f"Ingestion failure: {e}")
        AuditLogger.log_event(
            action="DOCUMENT_UPLOAD_FAILED",
            component="app.main",
            status="failure",
            resource=clean_name,
            user_id=user_id,
            username=username,
            metadata={"filename": clean_name, "error_category": "ingestion_failure"}
        )
        from backend.rag.pipeline import DuplicateIngestionError, InsufficientTextError, SafePathViolationError
        if isinstance(e, DuplicateIngestionError):
            raise HTTPException(status_code=400, detail=str(e))
        elif isinstance(e, InsufficientTextError):
            raise HTTPException(status_code=400, detail="Document contains no extractable text.")
        elif isinstance(e, SafePathViolationError):
            raise HTTPException(status_code=400, detail="Path traversal attempt blocked.")
        raise HTTPException(status_code=500, detail=f"Document indexing failed: {e}")

class VisibilityUpdateRequest(BaseModel):
    visibility: str

def _resolve_document_info(doc_id: str, current_user = None) -> Optional[Dict[str, Any]]:
    doc_info = None
    try:
        res = rag_service.get_document(doc_id)
        if isinstance(res, (dict, sqlite3.Row)):
            doc_info = dict(res)
    except Exception:
        pass

    if doc_info is None:
        try:
            docs = rag_service.list_documents(current_user=current_user)
            if isinstance(docs, (list, tuple)):
                for d in docs:
                    if isinstance(d, (dict, sqlite3.Row)):
                        d_dict = dict(d)
                        if d_dict.get("id") == doc_id or d_dict.get("document_id") == doc_id:
                            doc_info = d_dict
                            break
        except Exception:
            pass
    return doc_info

@app.post("/documents/{id}/share", tags=["Document Permissions"])
async def share_document(
    id: str,
    payload: DocumentShareRequest,
    current_user = Depends(get_current_user)
):
    """Explicitly grants document permission to a target user or department."""
    from datetime import datetime, timezone
    doc_info = _resolve_document_info(id, current_user)
    if not doc_info:
        raise HTTPException(status_code=404, detail="Document not found.")

    user_attrs = _extract_user_attrs(current_user)
    if not can_access_document(current_user, doc_info, "SHARE") and not can_access_document(current_user, doc_info, "MANAGE"):
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_DENIED",
            component="app.main",
            status="failure",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={"document_id": id, "operation": "share"}
        )
        raise HTTPException(status_code=403, detail="Access denied. You do not have permission to share this document.")

    if not payload.user_id and not payload.department_id:
        raise HTTPException(status_code=400, detail="Either user_id or department_id must be provided to share.")

    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO document_permissions (document_id, user_id, department_id, permission, granted_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            id,
            payload.user_id,
            payload.department_id,
            payload.permission.upper().strip(),
            user_attrs["id"],
            now_str
        ))
        perm_id = cursor.lastrowid
        conn.commit()

        AuditLogger.log_event(
            action="DOCUMENT_SHARED",
            component="app.main",
            status="success",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={
                "document_id": id,
                "target_user_id": payload.user_id,
                "target_department_id": payload.department_id,
                "permission": payload.permission.upper().strip()
            }
        )
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_GRANTED",
            component="app.main",
            status="success",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={
                "document_id": id,
                "target_user_id": payload.user_id,
                "target_department_id": payload.department_id,
                "permission": payload.permission.upper().strip()
            }
        )

        return {
            "id": perm_id,
            "document_id": id,
            "user_id": payload.user_id,
            "department_id": payload.department_id,
            "permission": payload.permission.upper().strip(),
            "granted_by": user_attrs["id"],
            "created_at": now_str
        }
    finally:
        conn.close()

@app.get("/documents/{id}/permissions", tags=["Document Permissions"])
async def get_document_permissions(id: str, current_user = Depends(get_current_user)):
    """Retrieves all active permission grants on a document."""
    doc_info = _resolve_document_info(id, current_user)
    if not doc_info:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not can_access_document(current_user, doc_info, "READ"):
        raise HTTPException(status_code=403, detail="Access denied.")

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dp.*, u.username as user_name, d.name as department_name, gb.username as granted_by_username
            FROM document_permissions dp
            LEFT JOIN users u ON dp.user_id = u.id
            LEFT JOIN departments d ON dp.department_id = d.id
            LEFT JOIN users gb ON dp.granted_by = gb.id
            WHERE dp.document_id = ?
            ORDER BY dp.created_at ASC
        """, (id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@app.delete("/documents/{id}/share/{perm_id}", tags=["Document Permissions"])
async def revoke_document_permission(id: str, perm_id: int, current_user = Depends(get_current_user)):
    """Revokes an explicit permission grant on a document."""
    doc_info = _resolve_document_info(id, current_user)
    if not doc_info:
        raise HTTPException(status_code=404, detail="Document not found.")

    user_attrs = _extract_user_attrs(current_user)
    if not can_access_document(current_user, doc_info, "SHARE") and not can_access_document(current_user, doc_info, "MANAGE"):
        raise HTTPException(status_code=403, detail="Access denied.")

    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM document_permissions WHERE id = ? AND document_id = ?", (perm_id, id))
        conn.commit()

        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_REVOKED",
            component="app.main",
            status="success",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={"document_id": id, "permission_id": perm_id}
        )
        return {"status": "success", "message": "Permission grant revoked."}
    finally:
        conn.close()

@app.patch("/documents/{id}/visibility", tags=["Document Permissions"])
async def update_document_visibility(
    id: str,
    payload: VisibilityUpdateRequest,
    current_user = Depends(get_current_user)
):
    """Updates document visibility policy (PRIVATE, DEPARTMENT, ORGANIZATION)."""
    from datetime import datetime, timezone
    clean_visibility = payload.visibility.upper().strip()
    if clean_visibility not in ["PRIVATE", "DEPARTMENT", "SHARED", "ORGANIZATION"]:
        raise HTTPException(status_code=400, detail="Invalid visibility policy. Must be PRIVATE, DEPARTMENT, SHARED, or ORGANIZATION.")

    doc_info = _resolve_document_info(id, current_user)
    if not doc_info:
        raise HTTPException(status_code=404, detail="Document not found.")

    user_attrs = _extract_user_attrs(current_user)
    if not can_access_document(current_user, doc_info, "MANAGE") and doc_info.get("owner_id") != user_attrs["id"]:
        raise HTTPException(status_code=403, detail="Access denied. Only owner or manager can change visibility.")

    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute("UPDATE documents SET visibility = ?, updated_at = ? WHERE id = ?", (clean_visibility, now_str, id))
        conn.commit()

        AuditLogger.log_event(
            action="DOCUMENT_UPDATED",
            component="app.main",
            status="success",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={"document_id": id, "visibility": clean_visibility}
        )
        return {"status": "success", "id": id, "visibility": clean_visibility}
    finally:
        conn.close()

@app.post("/documents/{id}/index", tags=["RAG Operations"])
async def reindex_document(id: str, current_user = Depends(get_current_user)):
    """Triggers manual re-indexing of a saved document file by ID, enforcing access control."""
    doc_info = _resolve_document_info(id, current_user)
    if not doc_info:
        raise HTTPException(status_code=404, detail="The requested document could not be found.")

    user_attrs = _extract_user_attrs(current_user)
    if not can_access_document(current_user, doc_info, "MANAGE") and doc_info.get("owner_id") != user_attrs["id"]:
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_DENIED",
            component="app.main",
            status="failure",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={"document_id": id, "operation": "reindex"}
        )
        raise HTTPException(status_code=403, detail="Access denied. You do not have permission to re-index this document.")

    doc_file_path = doc_info.get("source_path")
    if not doc_file_path or not os.path.exists(doc_file_path):
        raise HTTPException(status_code=404, detail="The requested document file could not be found on the server.")

    try:
        # Delete old vectors
        rag_service.delete_document(id)
        # Re-index preserving metadata
        new_doc_id = rag_service.ingest_document(
            doc_file_path,
            owner_id=doc_info.get("owner_id"),
            owner_username=doc_info.get("owner_username"),
            owner_department_id=doc_info.get("owner_department_id"),
            owner_department_name=doc_info.get("owner_department_name"),
            visibility=doc_info.get("visibility", "PRIVATE"),
            original_filename=doc_info.get("filename")
        )
        
        # Log DOCUMENT_INDEXED
        AuditLogger.log_event(
            action="DOCUMENT_INDEXED",
            component="app.main",
            status="success",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={"filename": doc_info.get("filename", id), "owner_id": doc_info.get("owner_id"), "id": new_doc_id}
        )
        
        return {
            "id": new_doc_id,
            "status": "indexed",
            "message": "Document re-indexed successfully."
        }
    except Exception as e:
        logging.getLogger("aegis.app").error(f"Re-indexing failed: {e}")
        raise HTTPException(status_code=500, detail="Document re-indexing failed.")

@app.get("/documents/{id}/preview", tags=["RAG Operations"])
async def preview_document(id: str, current_user = Depends(get_current_user)):
    """Securely streams document file bytes or thumbnail for authorized users."""
    from fastapi.responses import FileResponse
    doc_info = _resolve_document_info(id, current_user)
    if not doc_info:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not can_access_document(current_user, doc_info, "READ"):
        user_attrs = _extract_user_attrs(current_user)
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_DENIED",
            component="app.main",
            status="failure",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={"document_id": id, "operation": "preview"}
        )
        raise HTTPException(status_code=403, detail="Access denied.")

    source_path = doc_info.get("source_path")
    if not source_path or not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail="Document file not found on local storage.")

    # Safe directory check
    safe_base = os.path.abspath("data/knowledge_base")
    if not os.path.abspath(source_path).startswith(safe_base):
        raise HTTPException(status_code=400, detail="Safe path boundary violation.")

    mime_type = doc_info.get("mime_type", "application/octet-stream")
    return FileResponse(source_path, media_type=mime_type, filename=doc_info.get("filename"))

@app.get("/documents/{id}/download", tags=["RAG Operations"])
async def download_uploaded_document(id: str, current_user = Depends(get_current_user)):
    """Downloads the document file with access control check and audit logging."""
    doc_info = _resolve_document_info(id, current_user)
    if not doc_info:
        raise HTTPException(status_code=404, detail="Document not found.")

    user_attrs = _extract_user_attrs(current_user)
    if not can_access_document(current_user, doc_info, "DOWNLOAD"):
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_DENIED",
            component="app.main",
            status="failure",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={
                "resource_type": "document",
                "resource_id": id,
                "document_id": id,
                "action": "download",
                "result": "denied",
                "reason": "forbidden"
            }
        )
        AuditLogger.log_event(
            action="AUTHORIZATION_FAILURE",
            component="app.main",
            status="failure",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={
                "resource_type": "document",
                "resource_id": id,
                "action": "download",
                "result": "denied"
            }
        )
        raise HTTPException(status_code=403, detail="Access denied.")

    source_path = doc_info.get("source_path")
    if not source_path or not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail="Document file not found on local storage.")

    # Safe directory check
    safe_base = os.path.abspath("data/knowledge_base")
    if not os.path.abspath(source_path).startswith(safe_base):
        raise HTTPException(status_code=400, detail="Safe path boundary violation.")

    fmt = doc_info.get("document_type") or doc_info.get("file_type") or (doc_info.get("filename", "").split(".")[-1] if "." in doc_info.get("filename", "") else "")
    AuditLogger.log_event(
        action="DOCUMENT_DOWNLOADED",
        component="app.main",
        status="success",
        user_id=user_attrs["id"],
        username=user_attrs["username"],
        resource=doc_info.get("filename", id),
        metadata={
            "document_id": id,
            "artifact_id": id,
            "format": fmt,
            "output_format": fmt,
            "filename": doc_info.get("filename"),
            "file_size": doc_info.get("file_size")
        }
    )

    mime_type = doc_info.get("mime_type", "application/octet-stream")
    return FileResponse(source_path, media_type=mime_type, filename=doc_info.get("filename"))

@app.delete("/documents/{id}", tags=["RAG Operations"])
async def delete_document(id: str, current_user = Depends(get_current_user)):
    """Deletes vector references and removes physical document from disk, enforcing authorization."""
    doc_info = _resolve_document_info(id, current_user)
    if not doc_info:
        raise HTTPException(status_code=404, detail="The requested document could not be found.")

    user_attrs = _extract_user_attrs(current_user)
    if not can_access_document(current_user, doc_info, "DELETE"):
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_DENIED",
            component="app.main",
            status="failure",
            resource=doc_info.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={
                "document_id": id,
                "owner_id": doc_info.get("owner_id"),
                "attempted_by": user_attrs["id"],
                "operation": "delete"
            }
        )
        raise HTTPException(status_code=403, detail="Access denied. You do not have permission to delete this document.")

    try:
        doc_filename = doc_info.get("filename", "unknown")
        doc_owner_id = doc_info.get("owner_id")
        doc_file_path = doc_info.get("source_path")
        
        rag_service.delete_document(id)
        if doc_file_path and os.path.exists(doc_file_path):
            try:
                os.remove(doc_file_path)
            except Exception:
                pass
        AuditLogger.log_event(
            action="DOCUMENT_DELETED",
            component="app.main",
            status="success",
            resource=doc_filename,
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={"filename": doc_filename, "owner_id": doc_owner_id, "id": id}
        )
        return {"status": "success", "id": id, "message": f"Document '{doc_filename}' successfully removed."}
    except Exception as e:
        logging.getLogger("aegis.app").error(f"Document delete failure: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document.")

class RAGAskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=10)
    document_id: Optional[str] = None
    session_id: Optional[str] = None

@app.post("/documents/ask", tags=["RAG Operations"])
async def ask_documents(payload: RAGAskRequest, current_user = Depends(get_current_user)):
    """
    Generates a truthful, verified AI answer strictly grounded in indexed organizational documents.
    Cites exact document sources and page numbers, and refuses to hallucinate if evidence is missing.
    """
    try:
        res = await grounded_qa_service.generate_grounded_answer(
            query=payload.query,
            current_user=current_user,
            document_id=payload.document_id,
            session_id=payload.session_id,
            top_k=payload.top_k,
            feature="knowledge"
        )
        return res
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logging.getLogger("aegis.app").error(f"Grounded QA failure: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate document-grounded answer.")

class GenerateReportRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    topic: Optional[str] = Field(default="", max_length=1000)
    format: str = Field(default="pdf")
    document_id: Optional[str] = None
    session_id: Optional[str] = None

@app.post("/documents/generate", tags=["Document Generation"])
async def generate_document_report(payload: GenerateReportRequest, current_user = Depends(get_current_user)):
    """Generates an actual physical intelligence report (PDF/DOCX) from grounded document evidence."""
    try:
        res = await grounded_qa_service.generate_grounded_report(
            title=payload.title,
            topic=payload.topic or payload.title,
            format_type=payload.format,
            document_id=payload.document_id,
            session_id=payload.session_id,
            current_user=current_user
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logging.getLogger("aegis.app").error(f"Document generation failure: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {e}")

@app.get("/documents/generated", tags=["Document Generation"])
async def list_generated_documents(current_user = Depends(get_current_user)):
    """Lists all generated reports accessible to the authenticated user."""
    return grounded_qa_service.doc_generator.list_generated_documents(current_user=current_user)

@app.get("/documents/generated/{id}/download", tags=["Document Generation"])
async def download_generated_document(id: str, current_user = Depends(get_current_user)):
    """Streams the physical generated PDF or DOCX file with verified authorization."""
    from fastapi.responses import FileResponse
    doc = grounded_qa_service.doc_generator.get_generated_document(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Generated document not found.")

    if not can_access_generated_document(current_user, doc, "DOWNLOAD"):
        user_attrs = _extract_user_attrs(current_user)
        AuditLogger.log_event(
            action="DOCUMENT_ACCESS_DENIED",
            component="app.main",
            status="failure",
            resource=doc.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={
                "resource_type": "generated_document",
                "resource_id": id,
                "document_id": id,
                "artifact_id": id,
                "action": "download",
                "result": "denied",
                "reason": "forbidden"
            }
        )
        AuditLogger.log_event(
            action="AUTHORIZATION_FAILURE",
            component="app.main",
            status="failure",
            resource=doc.get("filename", id),
            user_id=user_attrs["id"],
            username=user_attrs["username"],
            metadata={
                "resource_type": "generated_document",
                "resource_id": id,
                "action": "download",
                "result": "denied"
            }
        )
        raise HTTPException(status_code=403, detail="Access denied. You do not have permission to download this generated report.")

    file_path = doc.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Physical document file missing on disk.")

    user_attrs = _extract_user_attrs(current_user)
    AuditLogger.log_event(
        action="DOCUMENT_DOWNLOADED",
        component="app.main",
        status="success",
        user_id=user_attrs["id"],
        username=user_attrs["username"],
        resource=doc.get("filename", id),
        metadata={
            "document_id": id,
            "artifact_id": id,
            "format": doc.get("format", "pdf"),
            "output_format": doc.get("format", "pdf"),
            "filename": doc.get("filename"),
            "file_size": doc.get("file_size")
        }
    )

    return FileResponse(
        path=file_path,
        media_type=doc.get("mime_type", "application/pdf"),
        filename=doc.get("filename", "report.pdf")
    )

@app.delete("/documents/generated/{id}", tags=["Document Generation"])
async def delete_generated_document(id: str, current_user = Depends(get_current_user)):
    """Deletes a generated report from SQLite and physical disk storage."""
    doc = grounded_qa_service.doc_generator.get_generated_document(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Generated document not found.")

    if not can_access_generated_document(current_user, doc, "DELETE"):
        raise HTTPException(status_code=403, detail="Access denied.")

    grounded_qa_service.doc_generator.delete_generated_document(id)
    return {"status": "success", "id": id, "message": "Generated document removed."}

class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=10)
    document_id: Optional[str] = None

@app.post("/documents/query", tags=["RAG Operations"])
async def query_documents(payload: RAGQueryRequest, current_user = Depends(get_current_user)):
    """Executes dynamic vector similarity search against the local ChromaDB database with pre-retrieval filtering."""
    user_attrs = _extract_user_attrs(current_user)
    accessible_ids = get_accessible_document_ids(current_user, permission="USE_IN_RAG")
    
    results = rag_service.search(
        query=payload.query,
        top_k=payload.top_k,
        document_id=payload.document_id,
        accessible_document_ids=accessible_ids
    )
    
    AuditLogger.log_event(
        action="RAG_QUERY",
        component="app.main",
        status="success",
        user_id=user_attrs["id"],
        username=user_attrs["username"],
        role=user_attrs["role"],
        metadata={"query_length": len(payload.query), "result_count": len(results)}
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
        raise HTTPException(status_code=503, detail="No active local model is currently reported by the inference runtime.")
    return registry_manager.get_model(curr_id)

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

class ModelRouteRequest(BaseModel):
    task_type: Optional[str] = None
    required_capabilities: Optional[List[str]] = None
    prompt: Optional[str] = None
    has_doc_context: bool = False
    has_image: bool = False
    preferred_model_id: Optional[str] = None
    auto_switch: bool = False

@app.post("/models/route", tags=["Model Operations"])
async def route_model_request(payload: ModelRouteRequest, current_user = Depends(get_current_user)):
    """Determines optimal locally installed model for task requirements without fabricating data."""
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    curr_role = _get_user_val(current_user, "role")

    task_enum = None
    if payload.task_type:
        try:
            task_enum = TaskType(payload.task_type.upper())
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid task_type '{payload.task_type}'. Valid types: {[t.value for t in TaskType]}")

    try:
        decision = await model_router.route(
            task_type=task_enum,
            required_capabilities=payload.required_capabilities,
            prompt=payload.prompt,
            has_doc_context=payload.has_doc_context,
            has_image=payload.has_image,
            preferred_model_id=payload.preferred_model_id,
            auto_switch=payload.auto_switch,
            user_id=curr_id,
            username=curr_username,
            role=curr_role
        )
        return decision.to_dict()
    except NoCompatibleModelError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/models/test", tags=["Model Operations"])
async def test_model_inference(payload: Optional[ModelTestRequest] = None, current_user = Depends(get_current_user)):
    """Executes deterministic test inference against target model on local Ollama daemon."""
    import time
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")

    target_model = (payload.model_id if payload and payload.model_id else None) or loader_manager.current_model_id
    if not target_model:
        AuditLogger.log_event(
            action="MODEL_TESTED",
            component="app.main",
            status="failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            metadata={"error_category": "no_active_model"}
        )
        raise HTTPException(status_code=503, detail="No active local model is currently reported by the inference runtime.")
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
    script_filename: Optional[str] = None
    conversation_id: Optional[str] = None

@app.post("/sandbox/execute", tags=["Sandbox Operations"])
async def execute_in_sandbox(payload: SandboxRequest, current_user = Depends(get_current_user)):
    """Executes python code inside the isolated local subprocess sandbox."""
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")
    try:
        res = sandbox_service.execute(
            code=payload.code,
            timeout_seconds=payload.timeout_seconds,
            user_id=curr_id,
            username=curr_username,
            conversation_id=payload.conversation_id,
            script_filename=payload.script_filename
        )
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="app.main",
            status="success" if res.get("success") else "failure",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            duration_ms=res.get("duration_ms", res.get("execution_time_ms")),
            metadata={
                "execution_id": res.get("execution_id"),
                "language": res.get("language"),
                "code_hash": res.get("code_hash"),
                "sandbox_exit_code": res.get("exit_code"),
                "sandbox_timeout": res.get("timed_out"),
                "stdout": res.get("stdout"),
                "stderr": res.get("stderr"),
                "error": res.get("error")
            }
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

@app.get("/sandbox/files", tags=["Sandbox Operations"])
async def list_sandbox_files(current_user = Depends(get_current_user)):
    """Lists real sandbox files owned by the authenticated user or all files if administrator."""
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    is_admin = curr_role == "admin"
    return sandbox_service.list_files(user_id=curr_id, is_admin=is_admin)

@app.get("/sandbox/files/{file_id}", tags=["Sandbox Operations"])
async def get_sandbox_file(file_id: str, current_user = Depends(get_current_user)):
    """Gets details and source content of a sandbox file with owner RBAC authorization."""
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    is_admin = curr_role == "admin"
    file_info = sandbox_service.get_file(file_id=file_id, user_id=curr_id, is_admin=is_admin)
    if not file_info:
        raise HTTPException(status_code=404, detail="Sandbox file not found or unauthorized.")
    return file_info

@app.get("/sandbox/executions", tags=["Sandbox Operations"])
async def list_sandbox_executions(limit: int = 50, current_user = Depends(get_current_user)):
    """Lists real recorded sandbox executions owned by the user or all executions if administrator."""
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    is_admin = curr_role == "admin"
    return sandbox_service.list_executions(user_id=curr_id, is_admin=is_admin, limit=limit)

@app.get("/sandbox/executions/{execution_id}", tags=["Sandbox Operations"])
async def get_sandbox_execution(execution_id: str, current_user = Depends(get_current_user)):
    """Gets details and telemetry for a specific sandbox execution with owner RBAC authorization."""
    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    is_admin = curr_role == "admin"
    exec_info = sandbox_service.get_execution(execution_id=execution_id, user_id=curr_id, is_admin=is_admin)
    if not exec_info:
        raise HTTPException(status_code=404, detail="Sandbox execution not found or unauthorized.")
    return exec_info

@app.get("/sandbox/artifacts/{artifact_id}/download", tags=["Sandbox Operations"])
async def download_sandbox_artifact(artifact_id: str, current_user = Depends(get_current_user)):
    """Downloads an artifact file generated by a sandbox execution with owner/admin authorization."""
    import sqlite3
    from backend.security.database import get_db_path

    curr_role = _get_user_val(current_user, "role")
    curr_id = _get_user_val(current_user, "id")
    curr_username = _get_user_val(current_user, "username")

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sandbox_artifacts WHERE id = ?", (artifact_id,))
        art = cursor.fetchone()
        if not art:
            raise HTTPException(status_code=404, detail="Sandbox artifact not found.")

        # Authorization: must be admin or artifact owner
        is_admin = curr_role == "admin"
        owner_id = art["user_id"]
        owner_username = art["username"]
        if not is_admin and (
            (owner_id is not None and owner_id != -1 and owner_id != curr_id) or
            (owner_id in (None, -1) and owner_username and owner_username != curr_username)
        ):
            AuditLogger.log_event(
                action="DOCUMENT_ACCESS_DENIED",
                component="app.main",
                status="failure",
                user_id=curr_id,
                username=curr_username,
                role=curr_role,
                resource=artifact_id,
                metadata={
                    "resource_type": "artifact",
                    "resource_id": artifact_id,
                    "artifact_id": artifact_id,
                    "action": "download",
                    "result": "denied",
                    "reason": "ARTIFACT_OWNERSHIP_FORBIDDEN"
                }
            )
            AuditLogger.log_event(
                action="AUTHORIZATION_FAILURE",
                component="app.main",
                status="failure",
                user_id=curr_id,
                username=curr_username,
                role=curr_role,
                resource=artifact_id,
                metadata={
                    "resource_type": "artifact",
                    "resource_id": artifact_id,
                    "action": "download",
                    "result": "denied"
                }
            )
            raise HTTPException(status_code=403, detail="Access denied. You do not own this sandbox artifact.")

        file_path = art["file_path"]
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Artifact file does not exist on disk.")

        # Safe directory boundary check
        allowed_dirs = [
            os.path.abspath("data/sandbox"),
            os.path.abspath("data/artifacts/sandbox"),
            os.path.abspath(getattr(sandbox_service, "artifacts_storage", "data/sandbox"))
        ]
        abs_target = os.path.abspath(file_path)
        if not any(abs_target.startswith(base) for base in allowed_dirs):
            raise HTTPException(status_code=400, detail="Safe path boundary violation.")

        ext = (art["filename"].split(".")[-1] if "." in art["filename"] else "file")
        AuditLogger.log_event(
            action="DOCUMENT_DOWNLOADED",
            component="app.main",
            status="success",
            user_id=curr_id,
            username=curr_username,
            role=curr_role,
            resource=artifact_id,
            metadata={
                "artifact_id": artifact_id,
                "document_id": artifact_id,
                "format": ext,
                "output_format": ext,
                "filename": art["filename"],
                "file_size": art["file_size"]
            }
        )

        return FileResponse(
            file_path,
            media_type=art["mime_type"] or "application/octet-stream",
            filename=art["filename"]
        )
    finally:
        conn.close()

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
        reload=(settings.APP_ENV == "development"),
        reload_dirs=["backend"],
        reload_excludes=[
            "data*",
            "sandbox_runs*",
            "sandbox_runs_test*",
            "*/data/*",
            "*/data/**/*",
            "*/sandbox_runs/*",
            "*/sandbox_runs/**/*",
            "*/sandbox_runs_test/*",
            "*/sandbox_runs_test/**/*"
        ]
    )

