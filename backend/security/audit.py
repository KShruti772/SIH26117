import os
import json
import sqlite3
import logging
import contextvars
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from backend.app.config.settings import settings
from backend.security.database import get_db_path

logger = logging.getLogger("aegis.audit")
logger.setLevel(logging.INFO)

# Context variables for automatic request correlation and user tracking
request_id_var = contextvars.ContextVar("request_id", default="")
current_user_var = contextvars.ContextVar("current_user", default=None)

# Allowed actions taxonomy
VALID_ACTIONS = {
    "AUTH_LOGIN",
    "AUTH_REGISTER",
    "MODEL_LOAD",
    "MODEL_UNLOAD",
    "MODEL_SWITCH",
    "RAG_SEARCH",
    "DOCUMENT_INGEST",
    "OCR_PROCESS",
    "SANDBOX_EXECUTION",
    "DOCUMENT_GENERATION",
    "AGENT_EXECUTION",
    "VERIFICATION",
    "ADMIN_OPERATION"
}

# Allowed status taxonomy
VALID_STATUSES = {
    "success",
    "failure"
}

# Allowed metadata keys allowlist to prevent leaks
ALLOWED_METADATA_KEYS = {
    "model_id",
    "capability",
    "duration_ms",
    "status",
    "error_category",
    "filename",
    "file_size",
    "chunk_count",
    "page_count",
    "query_length",
    "sandbox_exit_code",
    "sandbox_timeout",
    "step_id",
    "reasons",
    "score",
    "citation_count",
    "replan_count",
    "request_id"
}

def get_request_id() -> str:
    """Retrieves current request ID from context."""
    return request_id_var.get() or ""

def set_request_id(request_id: str) -> None:
    """Sets current request ID in context."""
    request_id_var.set(request_id)

def get_current_audit_user() -> Optional[Dict[str, Any]]:
    """Retrieves current authenticated user details from context."""
    return current_user_var.get()

def set_current_audit_user(user: Any) -> None:
    """Sets current authenticated user in context."""
    current_user_var.set(user)

class AuditLogger:
    """Service providing local append-only audit trail logging in SQLite database."""
    
    @staticmethod
    def log_event(
        action: str,
        component: str,
        status: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        role: Optional[str] = None,
        resource: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Appends audit event to SQLite database. Parameterized SQL prevents injection."""
        
        # 1. Validate action & status taxonomy
        if action not in VALID_ACTIONS:
            logger.error(f"Audit Log Rejected: Invalid action name '{action}'")
            return
            
        if status not in VALID_STATUSES:
            logger.error(f"Audit Log Rejected: Invalid status value '{status}'")
            return

        # 2. Extract correlation attributes from context if omitted by caller
        req_id = get_request_id()
        
        ctx_user = get_current_audit_user()
        if ctx_user:
            try:
                # Support sqlite3.Row dict-like mapping
                if user_id is None:
                    user_id = ctx_user["id"]
                if username is None:
                    username = ctx_user["username"]
                if role is None:
                    role = ctx_user["role"]
            except Exception:
                pass

        # 3. Sanitize metadata (strictly allowlist keys, exclude prompts/tokens/hashes)
        sanitized_meta = {}
        if metadata:
            for k, v in metadata.items():
                if k in ALLOWED_METADATA_KEYS:
                    sanitized_meta[k] = v
                    
        # Limit metadata size
        serialized_meta = None
        if sanitized_meta:
            serialized_meta = json.dumps(sanitized_meta)
            if len(serialized_meta) > 1000:
                serialized_meta = serialized_meta[:997] + "..."

        # 4. Insert into database. Parameterized variables protect against SQL injection.
        try:
            db_path = get_db_path()
            conn = sqlite3.connect(db_path, check_same_thread=False)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_logs (
                        user_id, username, role, action, component, 
                        resource, status, request_id, duration_ms, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, username, role, action, component,
                    resource, status, req_id, duration_ms, serialized_meta
                ))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            # Fall-safe: Log error to stderr but prevent crashing main application thread
            logger.error(f"Fail-Safe Audit Logging Alert: Database insert failed: {e}")

    @staticmethod
    def query_audit_logs(
        action: Optional[str] = None,
        username: Optional[str] = None,
        status: Optional[str] = None,
        request_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Queries local audit logs using parameterized queries for admin dashboards."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM audit_logs WHERE 1=1"
            params = []
            
            if action:
                query += " AND action = ?"
                params.append(action)
            if username:
                query += " AND username = ?"
                params.append(username)
            if status:
                query += " AND status = ?"
                params.append(status)
            if request_id:
                query += " AND request_id = ?"
                params.append(request_id)
                
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
