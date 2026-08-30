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
    # Authentication Actions
    "AUTH_LOGIN",
    "LOGIN_SUCCESS",
    "LOGIN_FAILED",
    "AUTH_REGISTER",
    "AUTH_LOGOUT",
    "LOGOUT",
    "AUTH_CHANGE_PASSWORD",
    "PASSWORD_CHANGE",
    "PASSWORD_CHANGED",
    "PASSWORD_RESET",
    "USER_PASSWORD_RESET",

    # Model Operations
    "MODEL_LOAD",
    "MODEL_UNLOAD",
    "MODEL_SWITCH",
    "MODEL_SELECTED",
    "MODEL_TESTED",

    # RAG Actions
    "RAG_SEARCH",
    "RAG_QUERY",
    "RAG_DOCUMENT_UPLOAD",
    "RAG_DOCUMENT_INDEX",
    "DOCUMENT_INGEST",
    "DOCUMENT_UPLOADED",
    "DOCUMENT_INDEXED",
    "DOCUMENT_DELETED",
    "DOCUMENT_ACCESS_DENIED",
    "OCR_PROCESS",

    # Execution & Workflows
    "SANDBOX_EXECUTION",
    "DOCUMENT_GENERATION",
    "AGENT_EXECUTION",
    "CHAT_REQUEST",
    "VERIFICATION",

    # User Administration & System Security
    "ADMIN_OPERATION",
    "USER_PROVISION",
    "USER_PROVISIONED",
    "USER_CREATED",
    "USER_ROLE_CHANGE",
    "USER_ROLE_UPDATED",
    "ROLE_CHANGED",
    "USER_ENABLE",
    "USER_DISABLE",
    "USER_DISABLED",
    "USER_ENABLED",
    "USER_STATUS_UPDATED",
    "SECURITY_CONFIGURATION_CHANGE",
    "AUTHORIZATION_DENIED",

    # Conversation Actions
    "CONVERSATION_CREATED",
    "CONVERSATION_DELETED"
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
    "reason",
    "allowed_roles",
    "attempted_role",
    "owner_id",
    "operation",
    "session_id",
    "score",
    "citation_count",
    "replan_count",
    "request_id",
    "username",
    "role",
    "is_active",
    "action",
    "target_user",
    "details",
    "title",
    "success",
    "latency_ms",
    "query"
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

        # 4. Insert into database with HMAC-SHA256 hash chaining for cryptographic tamper-evidence
        try:
            import hmac
            import hashlib
            db_path = get_db_path()
            conn = sqlite3.connect(db_path, check_same_thread=False)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT entry_hash FROM audit_logs ORDER BY id DESC LIMIT 1")
                last_row = cursor.fetchone()
                prev_hash = last_row[0] if (last_row and last_row[0]) else "GENESIS_ROOT_HASH"
                
                timestamp_str = datetime.now(timezone.utc).isoformat()
                data_to_hash = f"{prev_hash}|{timestamp_str}|{user_id}|{username}|{role}|{action}|{component}|{resource}|{status}|{req_id}|{duration_ms}|{serialized_meta}"
                entry_hash = hmac.new(
                    settings.SECRET_KEY.encode("utf-8"),
                    data_to_hash.encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()

                cursor.execute("""
                    INSERT INTO audit_logs (
                        timestamp, user_id, username, role, action, component, 
                        resource, status, request_id, duration_ms, metadata_json,
                        previous_hash, entry_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp_str, user_id, username, role, action, component,
                    resource, status, req_id, duration_ms, serialized_meta,
                    prev_hash, entry_hash
                ))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            # Fail-safe: Log error to stderr but prevent crashing main application thread
            logger.error(f"Fail-Safe Audit Logging Alert: Database insert failed: {e}")

    @staticmethod
    def query_audit_logs(
        action: Optional[str] = None,
        username: Optional[str] = None,
        status: Optional[str] = None,
        request_id: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 200
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
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            if search:
                query += " AND (username LIKE ? OR action LIKE ? OR component LIKE ? OR request_id LIKE ?)"
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param, search_param])
                
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def verify_chain_integrity() -> Dict[str, Any]:
        """Recalculates cryptographic HMAC hash chain across all audit entries to verify tamper-evidence."""
        import hmac
        import hashlib
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs ORDER BY id ASC")
            rows = cursor.fetchall()
            
            expected_prev = "GENESIS_ROOT_HASH"
            total = len(rows)
            
            for row in rows:
                row_dict = dict(row)
                prev_h = row_dict.get("previous_hash")
                entry_h = row_dict.get("entry_hash")
                
                # Unchained legacy records
                if not entry_h:
                    continue

                if prev_h != expected_prev:
                    return {
                        "status": "TAMPERED",
                        "total_records": total,
                        "tampered_record_id": row_dict["id"],
                        "reason": f"Previous hash mismatch on record ID {row_dict['id']}"
                    }
                    
                data_to_hash = f"{prev_h}|{row_dict['timestamp']}|{row_dict['user_id']}|{row_dict['username']}|{row_dict['role']}|{row_dict['action']}|{row_dict['component']}|{row_dict['resource']}|{row_dict['status']}|{row_dict['request_id']}|{row_dict['duration_ms']}|{row_dict['metadata_json']}"
                expected_entry = hmac.new(
                    settings.SECRET_KEY.encode("utf-8"),
                    data_to_hash.encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()

                if entry_h != expected_entry:
                    return {
                        "status": "TAMPERED",
                        "total_records": total,
                        "tampered_record_id": row_dict["id"],
                        "reason": f"Entry hash mismatch on record ID {row_dict['id']}"
                    }
                    
                expected_prev = entry_h

            return {
                "status": "INTACT",
                "total_records": total,
                "tampered_record_id": None,
                "reason": "Cryptographic HMAC chain verified successfully across all audit entries."
            }
        finally:
            conn.close()
