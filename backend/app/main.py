from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uuid
from backend.app.config.settings import settings
from backend.security.database import init_db
from backend.security.auth_router import router as auth_router
from backend.security.audit import request_id_var, AuditLogger
from backend.security.dependencies import RoleChecker

# Initialize authentication database tables
init_db()

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
