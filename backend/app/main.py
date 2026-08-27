from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uuid
from backend.app.config.settings import settings
from backend.security.database import init_db
from backend.security.auth_router import router as auth_router
from backend.security.audit import request_id_var, AuditLogger, get_request_id
from backend.security.dependencies import RoleChecker, get_current_user
from pydantic import BaseModel, Field
import os

from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
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

@app.post("/chat", tags=["Agent Operations"])
async def run_chat(payload: ChatRequest, current_user = Depends(get_current_user)):
    """Runs a multi-step sovereign agent query using local models, sandboxes, and verifiers."""
    from fastapi import HTTPException
    try:
        res = await agent_controller.run(payload.message)
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
                    
        return {
            "success": res["success"],
            "answer": res["plan"]["final_output"] if res["success"] else (res["error"] or "Agent execution failed."),
            "sources": sources,
            "verification": verification or "PASS",
            "request_id": req_id,
            "duration_ms": res["duration_ms"]
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
