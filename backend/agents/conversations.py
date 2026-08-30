import json
import uuid
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from backend.security.database import get_db_path

class ConversationManager:
    """Manages multi-session conversation lifecycle and message history using local SQLite."""

    @staticmethod
    def list_conversations(user_id: Optional[int] = None, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves list of conversations ordered by most recently updated."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            if username and username != "admin":
                cursor.execute("""
                    SELECT id, title, created_at, updated_at 
                    FROM conversations 
                    WHERE username = ? OR user_id = ?
                    ORDER BY updated_at DESC
                """, (username, user_id))
            else:
                cursor.execute("""
                    SELECT id, title, created_at, updated_at 
                    FROM conversations 
                    ORDER BY updated_at DESC
                """)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def create_conversation(title: str = "New Conversation", user_id: Optional[int] = None, username: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new conversation session record."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        now_str = datetime.now(timezone.utc).isoformat()
        sid = session_id or f"conv_{uuid.uuid4().hex[:12]}"
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversations (id, user_id, username, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sid, user_id, username, title, now_str, now_str))
            conn.commit()
            return {
                "id": sid,
                "title": title,
                "created_at": now_str,
                "updated_at": now_str,
                "messages": []
            }
        finally:
            conn.close()

    @staticmethod
    def get_conversation_owner(session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves user ownership metadata (user_id, username) for a conversation session."""
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
        """Retrieves conversation metadata and formatted message sequence."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, user_id, username, title, created_at, updated_at FROM conversations WHERE id = ?", (session_id,))
            conv_row = cursor.fetchone()
            if not conv_row:
                return None

            conv = dict(conv_row)
            cursor.execute("""
                SELECT id, conversation_id, role, content, timestamp, rag_used, sources_json, model_id, duration_ms, request_id, verification, error_detail
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
                messages.append({
                    "id": r["id"],
                    "role": r["role"],
                    "content": r["content"],
                    "timestamp": r["timestamp"],
                    "rag_used": bool(r["rag_used"]),
                    "sources": sources,
                    "model_id": r["model_id"],
                    "duration_ms": r["duration_ms"],
                    "request_id": r["request_id"],
                    "verification": r["verification"],
                    "error_detail": r["error_detail"]
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
        msg_id: Optional[str] = None,
        rag_used: bool = False,
        sources: Optional[List[Dict[str, Any]]] = None,
        model_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        request_id: Optional[str] = None,
        verification: Optional[str] = None,
        error_detail: Optional[str] = None
    ) -> Dict[str, Any]:
        """Appends a message to an existing conversation session, updating timestamp and title."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        now_str = datetime.now(timezone.utc).isoformat()
        mid = msg_id or f"msg_{uuid.uuid4().hex[:12]}"
        sources_str = json.dumps(sources) if sources else None
        
        try:
            cursor = conn.cursor()
            # Ensure conversation exists
            cursor.execute("SELECT title FROM conversations WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                # Auto-create conversation if missing
                auto_title = content[:35] + ("..." if len(content) > 35 else "") if role == "user" else "New Conversation"
                cursor.execute("""
                    INSERT INTO conversations (id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (session_id, auto_title, now_str, now_str))
            else:
                current_title = row[0]
                if current_title == "New Conversation" and role == "user":
                    new_title = content[:35] + ("..." if len(content) > 35 else "")
                    cursor.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (new_title, now_str, session_id))
                else:
                    cursor.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_str, session_id))

            cursor.execute("""
                INSERT INTO messages (
                    id, conversation_id, role, content, timestamp, rag_used, sources_json, 
                    model_id, duration_ms, request_id, verification, error_detail
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mid, session_id, role, content, now_str, 1 if rag_used else 0,
                sources_str, model_id, duration_ms, request_id, verification, error_detail
            ))
            conn.commit()

            return {
                "id": mid,
                "conversation_id": session_id,
                "role": role,
                "content": content,
                "timestamp": now_str,
                "rag_used": rag_used,
                "sources": sources or [],
                "model_id": model_id,
                "duration_ms": duration_ms,
                "request_id": request_id,
                "verification": verification,
                "error_detail": error_detail
            }
        finally:
            conn.close()

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
