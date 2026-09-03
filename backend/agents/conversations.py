import json
import uuid
import sqlite3
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from backend.security.database import get_db_path

def generate_deterministic_title(query: str, max_length: int = 40) -> str:
    """
    Generates a clean, human-readable conversation title from the user prompt
    without relying on an external LLM.
    """
    if not query or not query.strip():
        return "New Conversation"
    
    clean = query.strip()
    
    # Strip common leading question / command patterns
    prefixes = [
        "what is the", "what is a", "what is our", "what is", "what are the", "what are",
        "how do i", "how to", "how do we", "how can i", "how can we",
        "please explain", "explain what is", "explain how", "explain",
        "tell me about", "can you tell me about", "can you explain",
        "could you explain", "write a python", "write python", "write a", "write",
        "show me", "search for", "find information about", "find"
    ]
    lower = clean.lower()
    for prefix in prefixes:
        if lower.startswith(prefix + " "):
            clean = clean[len(prefix) + 1:].strip()
            break

    # Remove extra special characters and punctuation
    clean = re.sub(r'[\r\n\t]+', ' ', clean)
    clean = clean.rstrip("?.!;, \t\n")
    
    words = clean.split()
    if not words:
        return "New Conversation"
        
    title = " ".join(w.capitalize() if not w.isupper() else w for w in words)
    
    if len(title) > max_length:
        title = title[:max_length].rstrip() + "..."
        
    return title or "New Conversation"

def validate_session_id(session_id: str) -> str:
    """Validates session_id to prevent path injection and invalid characters."""
    if not session_id or not isinstance(session_id, str):
        raise ValueError("Invalid session_id: Must be a non-empty string.")
    clean = session_id.strip()
    if not re.match(r"^[a-zA-Z0-9_\-]+$", clean) or len(clean) > 64:
        raise ValueError(f"Invalid session_id format: '{clean}'")
    return clean

class ConversationManager:
    """Manages multi-session conversation lifecycle and message history using local SQLite."""

    @staticmethod
    def list_conversations(user_id: Optional[int] = None, username: Optional[str] = None, is_admin: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieves list of conversations ordered by most recently updated.
        Strictly scopes results to the authenticated user unless is_admin is explicitly requested.
        """
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            if is_admin:
                cursor.execute("""
                    SELECT id, user_id, username, title, feature, status, created_at, updated_at, last_message_at 
                    FROM conversations 
                    ORDER BY updated_at DESC
                """)
            elif user_id is not None or username is not None:
                cursor.execute("""
                    SELECT id, user_id, username, title, feature, status, created_at, updated_at, last_message_at 
                    FROM conversations 
                    WHERE (user_id = ? AND user_id IS NOT NULL) OR (username = ? AND username IS NOT NULL)
                    ORDER BY updated_at DESC
                """, (user_id, username))
            else:
                # Unauthenticated or non-specified user should receive empty list
                return []
                
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def create_conversation(
        title: Optional[str] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        session_id: Optional[str] = None,
        feature: str = "chat"
    ) -> Dict[str, Any]:
        """Creates a new persistent conversation session record."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        now_str = datetime.now(timezone.utc).isoformat()
        sid = session_id or f"conv_{uuid.uuid4().hex[:12]}"
        conv_title = title or "New Conversation"
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversations (id, user_id, username, title, feature, status, created_at, updated_at, last_message_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sid, user_id, username, conv_title, feature, "active", now_str, now_str, now_str))
            conn.commit()
            return {
                "id": sid,
                "user_id": user_id,
                "username": username,
                "title": conv_title,
                "feature": feature,
                "status": "active",
                "created_at": now_str,
                "updated_at": now_str,
                "last_message_at": now_str,
                "messages": []
            }
        finally:
            conn.close()

    @staticmethod
    def get_conversation_owner(session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves user ownership metadata (id, user_id, username) for a conversation session."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, user_id, username FROM conversations WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def get_conversation(session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves conversation metadata and formatted message sequence in chronological order."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, username, title, feature, status, created_at, updated_at, last_message_at 
                FROM conversations 
                WHERE id = ?
            """, (session_id,))
            conv_row = cursor.fetchone()
            if not conv_row:
                return None

            conv = dict(conv_row)
            cursor.execute("""
                SELECT id, conversation_id, user_id, username, role, content, timestamp, rag_used, sources_json, 
                       model_id, duration_ms, request_id, verification, error_detail, feature, metadata_json
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """, (session_id,))
            msg_rows = cursor.fetchall()
            
            messages = []
            for r in msg_rows:
                sources = []
                if r["sources_json"]:
                    try:
                        sources = json.loads(r["sources_json"])
                    except Exception:
                        sources = []
                meta = {}
                if r["metadata_json"]:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        meta = {}
                messages.append({
                    "id": r["id"],
                    "conversation_id": r["conversation_id"],
                    "user_id": r["user_id"],
                    "username": r["username"],
                    "role": r["role"],
                    "content": r["content"],
                    "timestamp": r["timestamp"],
                    "created_at": r["timestamp"],
                    "rag_used": bool(r["rag_used"]),
                    "sources": sources,
                    "model_id": r["model_id"],
                    "duration_ms": r["duration_ms"],
                    "request_id": r["request_id"],
                    "verification": r["verification"],
                    "error_detail": r["error_detail"],
                    "task_type": meta.get("task_type"),
                    "document_id": meta.get("document_id"),
                    "document_ids": meta.get("document_ids", []),
                    "feature": r["feature"] or "chat",
                    "metadata": meta
                })
            conv["messages"] = messages
            return conv
        finally:
            conn.close()

    @staticmethod
    def add_message(
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        msg_id: Optional[str] = None,
        rag_used: bool = False,
        sources: Optional[List[Dict[str, Any]]] = None,
        model_id: Optional[str] = None,
        model: Optional[str] = None,
        duration_ms: Optional[int] = None,
        request_id: Optional[str] = None,
        verification: Optional[str] = None,
        error_detail: Optional[str] = None,
        feature: str = "chat",
        document_id: Optional[str] = None,
        task_type: Optional[str] = None,
        routing_info: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Appends a message to a conversation session, maintaining timestamps, ownership, and deterministic titles."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        now_str = datetime.now(timezone.utc).isoformat()
        mid = msg_id or f"msg_{uuid.uuid4().hex[:12]}"
        sources_str = json.dumps(sources, default=str) if sources else None
        
        meta = metadata.copy() if metadata else {}
        if document_id:
            meta["document_id"] = document_id
        if task_type:
            meta["task_type"] = task_type
        if routing_info:
            meta["routing_info"] = routing_info
        meta_str = json.dumps(meta, default=str) if meta else None
        effective_model = str(model_id or model) if (model_id or model) else None
        
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT title, user_id, username FROM conversations WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                # Auto-create conversation if missing
                auto_title = generate_deterministic_title(content) if role == "user" else "New Conversation"
                cursor.execute("""
                    INSERT INTO conversations (id, user_id, username, title, feature, status, created_at, updated_at, last_message_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (session_id, user_id, username, auto_title, feature, "active", now_str, now_str, now_str))
            else:
                current_title, existing_user_id, existing_username = row[0], row[1], row[2]
                new_user_id = user_id if existing_user_id is None else existing_user_id
                new_username = username if existing_username is None else existing_username
                
                if current_title in ("New Conversation", "") and role == "user":
                    new_title = generate_deterministic_title(content)
                    cursor.execute("""
                        UPDATE conversations 
                        SET title = ?, user_id = ?, username = ?, updated_at = ?, last_message_at = ? 
                        WHERE id = ?
                    """, (new_title, new_user_id, new_username, now_str, now_str, session_id))
                else:
                    cursor.execute("""
                        UPDATE conversations 
                        SET user_id = ?, username = ?, updated_at = ?, last_message_at = ? 
                        WHERE id = ?
                    """, (new_user_id, new_username, now_str, now_str, session_id))

            cursor.execute("""
                INSERT INTO messages (
                    id, conversation_id, user_id, username, role, content, timestamp, rag_used, sources_json, 
                    model_id, duration_ms, request_id, verification, error_detail, feature, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mid, session_id, user_id, username, role, content, now_str, 1 if rag_used else 0,
                sources_str, effective_model, duration_ms, request_id, verification, error_detail, feature, meta_str
            ))
            conn.commit()

            return {
                "id": mid,
                "conversation_id": session_id,
                "user_id": user_id,
                "username": username,
                "role": role,
                "content": content,
                "timestamp": now_str,
                "created_at": now_str,
                "rag_used": rag_used,
                "sources": sources or [],
                "model_id": model_id,
                "duration_ms": duration_ms,
                "request_id": request_id,
                "verification": verification,
                "error_detail": error_detail,
                "feature": feature,
                "metadata": metadata or {}
            }
        finally:
            conn.close()

    @staticmethod
    def update_conversation_title(session_id: str, new_title: str) -> bool:
        """Updates the conversation title and updated_at timestamp."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE conversations 
                SET title = ?, updated_at = ?
                WHERE id = ?
            """, (new_title.strip(), now_str, session_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def get_messages(session_id: str) -> List[Dict[str, Any]]:
        """Retrieves raw message history list for a conversation."""
        conv = ConversationManager.get_conversation(session_id)
        return conv.get("messages", []) if conv else []

    @staticmethod
    def delete_conversation(session_id: str) -> bool:
        """Deletes conversation and associated messages."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (session_id,))
            cursor.execute("DELETE FROM conversations WHERE id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
