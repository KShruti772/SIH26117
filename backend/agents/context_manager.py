import os
import re
import json
import time
import sqlite3
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from backend.security.database import get_db_path
from backend.security.audit import AuditLogger
from backend.agents.conversations import ConversationManager

logger = logging.getLogger("aegis.context_manager")
logger.setLevel(logging.INFO)

class ContextType(str, Enum):
    """Standardized taxonomy of context sources in AEGIS."""
    RECENT_CONVERSATION = "RECENT_CONVERSATION"
    TASK_CONTEXT = "TASK_CONTEXT"
    DOCUMENT_CONTEXT = "DOCUMENT_CONTEXT"
    ARTIFACT_CONTEXT = "ARTIFACT_CONTEXT"
    EXECUTION_CONTEXT = "EXECUTION_CONTEXT"
    RAG_CONTEXT = "RAG_CONTEXT"
    MODEL_CONTEXT = "MODEL_CONTEXT"

@dataclass
class ContextPackage:
    """Standardized structured container of bounded, authorized context for an agent turn."""
    conversation_id: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None
    task_type: str = "general"
    recent_messages: List[Dict[str, Any]] = field(default_factory=list)
    task_context: Optional[Dict[str, Any]] = None
    referenced_documents: List[Dict[str, Any]] = field(default_factory=list)
    generated_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    sandbox_executions: List[Dict[str, Any]] = field(default_factory=list)
    rag_evidence: List[Dict[str, Any]] = field(default_factory=list)
    resolved_target_doc: Optional[Dict[str, Any]] = None
    resolved_target_artifact: Optional[Dict[str, Any]] = None
    resolved_execution_result: Optional[Dict[str, Any]] = None
    resolved_model_info: Optional[Dict[str, Any]] = None
    resolved_created_file: Optional[Dict[str, Any]] = None
    context_summary: Optional[str] = None
    authorized: bool = True
    error: Optional[str] = None
    telemetry: Dict[str, Any] = field(default_factory=lambda: {
        "context_messages_used": 0,
        "context_documents_used": 0,
        "context_artifacts_used": 0,
        "context_truncated": False,
        "context_token_estimate": 0,
        "memory_source_count": 0
    })

    def format_for_prompt(self) -> str:
        """
        Formats relevant conversational context into a bounded, sanitized,
        and prompt-injection resistant block. Historical messages and documents
        are presented strictly as untrusted DATA blocks that cannot override system rules.
        """
        sections = []

        # 1. Resolved Execution Results (e.g. factorial result, calculation output)
        if self.resolved_execution_result:
            stdout_txt = (self.resolved_execution_result.get("stdout") or "").strip()
            code_txt = (self.resolved_execution_result.get("code") or "").strip()
            sections.append(
                f"--- PREVIOUS EXECUTION RESULT (DATA ONLY) ---\n"
                f"Execution Output: {stdout_txt}\n"
                f"Script:\n{code_txt}\n"
                f"--- END PREVIOUS EXECUTION RESULT ---"
            )

        # 2. Resolved Artifact Details (e.g. generated DOCX/CSV)
        if self.resolved_target_artifact:
            art_name = self.resolved_target_artifact.get("filename") or "artifact"
            art_path = self.resolved_target_artifact.get("file_path") or self.resolved_target_artifact.get("path") or ""
            art_type = self.resolved_target_artifact.get("format") or self.resolved_target_artifact.get("mime_type") or "file"
            sections.append(
                f"--- PREVIOUS GENERATED ARTIFACT (DATA ONLY) ---\n"
                f"Filename: {art_name}\n"
                f"Format: {art_type}\n"
                f"Path: {art_path}\n"
                f"--- END PREVIOUS GENERATED ARTIFACT ---"
            )

        # 3. Compact Task Summary (for long conversations)
        if self.context_summary:
            sections.append(
                f"--- CONVERSATION TASK SUMMARY (DATA ONLY) ---\n"
                f"{self.context_summary}\n"
                f"--- END CONVERSATION TASK SUMMARY ---"
            )

        # 4. Recent Chronological Messages
        if self.recent_messages:
            msg_lines = []
            for m in self.recent_messages:
                role = "User" if m.get("role") == "user" else "Assistant"
                content = (m.get("content") or "").strip()
                # Sanitize to prevent prompt injection boundary escapes
                safe_content = content.replace("--- END", "--- [DATA] END")
                msg_lines.append(f"{role}: {safe_content}")
            
            sections.append(
                f"--- RECENT CONVERSATION HISTORY (UNTRUSTED DATA) ---\n"
                + "\n".join(msg_lines)
                + "\n--- END RECENT CONVERSATION HISTORY ---"
            )

        return "\n\n".join(sections)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "username": self.username,
            "task_type": self.task_type,
            "recent_messages_count": len(self.recent_messages),
            "referenced_documents_count": len(self.referenced_documents),
            "generated_artifacts_count": len(self.generated_artifacts),
            "sandbox_executions_count": len(self.sandbox_executions),
            "resolved_target_doc": self.resolved_target_doc,
            "resolved_target_artifact": self.resolved_target_artifact,
            "resolved_execution_result": self.resolved_execution_result,
            "resolved_model_info": self.resolved_model_info,
            "resolved_created_file": self.resolved_created_file,
            "context_summary": self.context_summary,
            "telemetry": self.telemetry
        }


def _extract_user_field(user: Any, key: str, default: Any = None) -> Any:
    if user is None:
        return default
    if isinstance(user, dict):
        return user.get(key, default)
    if hasattr(user, "__getitem__"):
        try:
            val = user[key]
            if val is not None:
                return val
        except (KeyError, IndexError, TypeError):
            pass
    return getattr(user, key, default)


class ContextManager:
    """
    Sovereign Persistent Agent Memory and Dynamic Context Manager for AEGIS.
    Enforces strict user isolation, deterministic reference resolution,
    model-aware context budgeting, and authoritative source hierarchy.
    """

    def __init__(
        self,
        registry_manager: Optional[Any] = None,
        rag_service: Optional[Any] = None,
        default_context_budget: int = 16384,
        max_messages_window: int = 10
    ):
        self.registry_manager = registry_manager
        self.rag_service = rag_service
        self.default_context_budget = default_context_budget
        self.max_messages_window = max_messages_window

    def get_model_context_limit(self, model_id: Optional[str] = None) -> int:
        """Retrieves configured context window capacity for the target model."""
        if self.registry_manager and model_id:
            try:
                profile = self.registry_manager.get_model(model_id)
                if profile and hasattr(profile, "context_length") and profile.context_length:
                    return int(profile.context_length)
                if isinstance(profile, dict) and profile.get("context_length"):
                    return int(profile["context_length"])
            except Exception as e:
                logger.warning(f"Could not read context length for model '{model_id}': {e}")
        return self.default_context_budget

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Deterministic conservative token count estimate (approx. 4 characters per token)."""
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)

    def _authorize_session(self, session_id: str, user_id: Optional[int], username: Optional[str], is_admin: bool) -> bool:
        """Verifies session belongs to authenticated user or caller is admin."""
        if not session_id:
            return True
        owner = ConversationManager.get_conversation_owner(session_id)
        if not owner:
            return True
        if is_admin:
            return True
        owner_id = owner.get("user_id")
        owner_username = owner.get("username")
        if owner_id is None and not owner_username:
            return True
        if owner_id is not None and user_id is not None:
            return owner_id == user_id
        if owner_username and username:
            return owner_username == username
        return False

    def _fetch_session_generated_artifacts(self, session_id: str, user_id: Optional[int], is_admin: bool) -> List[Dict[str, Any]]:
        """Retrieves verified generated documents (DOCX, PDF, XLSX) for this session and user."""
        if not session_id:
            return []
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            if is_admin or user_id is None:
                cursor.execute("""
                    SELECT id, owner_id, owner_username, filename, title, format, file_size, mime_type, file_path, created_at, conversation_id
                    FROM generated_documents
                    WHERE conversation_id = ?
                    ORDER BY created_at ASC
                """, (session_id,))
            else:
                cursor.execute("""
                    SELECT id, owner_id, owner_username, filename, title, format, file_size, mime_type, file_path, created_at, conversation_id
                    FROM generated_documents
                    WHERE conversation_id = ? AND (owner_id = ? OR owner_id = -1)
                    ORDER BY created_at ASC
                """, (session_id, user_id))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def _fetch_session_sandbox_artifacts(self, session_id: str, user_id: Optional[int], is_admin: bool) -> List[Dict[str, Any]]:
        """Retrieves verified sandbox artifacts (CSV, TXT, JSON, etc.) for this session and user."""
        if not session_id:
            return []
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            if is_admin or user_id is None:
                cursor.execute("""
                    SELECT id, execution_id, user_id, username, conversation_id, filename, file_path, file_size, mime_type, created_at
                    FROM sandbox_artifacts
                    WHERE conversation_id = ?
                    ORDER BY created_at ASC
                """, (session_id,))
            else:
                cursor.execute("""
                    SELECT id, execution_id, user_id, username, conversation_id, filename, file_path, file_size, mime_type, created_at
                    FROM sandbox_artifacts
                    WHERE conversation_id = ? AND (user_id = ? OR user_id = -1)
                    ORDER BY created_at ASC
                """, (session_id, user_id))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def build_context(
        self,
        conversation_id: Optional[str],
        current_user: Optional[Any],
        current_request: str,
        task_category: str = "general",
        model_id: Optional[str] = None
    ) -> ContextPackage:
        """
        Builds an authorized, model-aware, and bounded context package
        for the current user turn.
        """
        user_id = _extract_user_field(current_user, "id")
        username = _extract_user_field(current_user, "username")
        role = _extract_user_field(current_user, "role")
        is_admin = (role == "admin")

        package = ContextPackage(
            conversation_id=conversation_id,
            user_id=user_id,
            username=username,
            role=role,
            task_type=task_category
        )

        # 1. Authorization Guard
        if conversation_id:
            authorized = self._authorize_session(conversation_id, user_id=user_id, username=username, is_admin=is_admin)
            if not authorized:
                AuditLogger.log_event(
                    action="AUTHORIZATION_DENIED",
                    component="agents.context_manager",
                    status="failure",
                    user_id=user_id,
                    username=username,
                    role=role,
                    resource=conversation_id,
                    metadata={"reason": "CONVERSATION_ACCESS_FORBIDDEN", "session_id": conversation_id}
                )
                logger.warning(f"Unauthorized context access blocked for user {username} on session {conversation_id}")
                package.authorized = False
                package.error = "Access denied: Unauthorized conversation session."
                return package

        # If no conversation session, return clean initial package
        if not conversation_id:
            return package

        # 2. Retrieve chronological messages
        all_messages = ConversationManager.get_messages(conversation_id) or []

        # 3. Retrieve session artifacts
        gen_docs = self._fetch_session_generated_artifacts(conversation_id, user_id=user_id, is_admin=is_admin)
        sb_artifacts = self._fetch_session_sandbox_artifacts(conversation_id, user_id=user_id, is_admin=is_admin)
        package.generated_artifacts = gen_docs
        package.sandbox_executions = []

        # 4. Extract previous execution results & referenced documents from message history
        sandbox_runs = []
        referenced_docs_map = {}

        for m in all_messages:
            meta = m.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            
            # Extract sandbox execution outputs
            sb_exec = meta.get("sandbox_execution") or (meta.get("execution", {}).get("sandbox") if isinstance(meta.get("execution"), dict) else None)
            if sb_exec and isinstance(sb_exec, dict) and sb_exec.get("stdout") is not None:
                sandbox_runs.append(sb_exec)
                
            # Extract referenced documents
            doc_ids = list(meta.get("document_ids") or [])
            if meta.get("document_id") and meta.get("document_id") not in doc_ids:
                doc_ids.append(meta.get("document_id"))
            if m.get("document_id") and m.get("document_id") not in doc_ids:
                doc_ids.append(m.get("document_id"))
            if m.get("document_ids"):
                for did in m.get("document_ids"):
                    if did not in doc_ids:
                        doc_ids.append(did)
            for s in (m.get("sources") or []):
                if isinstance(s, dict) and (s.get("filename") or s.get("document_name")):
                    fname = s.get("filename") or s.get("document_name")
                    if fname not in doc_ids:
                        doc_ids.append(fname)
                        
            for did in doc_ids:
                if did and did not in referenced_docs_map:
                    referenced_docs_map[did] = {"id": did, "filename": did}

        package.sandbox_executions = sandbox_runs
        package.referenced_documents = list(referenced_docs_map.values())

        # 5. Deterministic Reference & Anaphora Resolution
        q_lower = (current_request or "").lower().strip()

        # A. Resolve Execution Result follow-ups (e.g. "What result did you get?", "What was the result?")
        exec_inquiry_patterns = [
            "what result did you get", "what was the result", "what is the result", "show the result",
            "what did you calculate", "what did it calculate", "what was the output", "what output did you get",
            "earlier result", "previous result", "what did you compute", "result did you get"
        ]
        if any(p in q_lower for p in exec_inquiry_patterns) and sandbox_runs:
            # Most recent successful execution result
            for srun in reversed(sandbox_runs):
                if srun.get("stdout") is not None:
                    package.resolved_execution_result = srun
                    AuditLogger.log_event(
                        action="TASK_CONTEXT_RESOLVED",
                        component="agents.context_manager",
                        status="success",
                        user_id=user_id,
                        username=username,
                        role=role,
                        resource=conversation_id,
                        metadata={"resolution_type": "execution_result", "session_id": conversation_id}
                    )
                    break

        # B. Resolve Artifact follow-ups (e.g. "Convert that report to PDF", "Use the CSV you generated earlier")
        # Check for CSV artifact reference
        csv_inquiry_patterns = ["the csv", "that csv", "csv you generated", "generated csv", "use the csv"]
        if any(p in q_lower for p in csv_inquiry_patterns) and sb_artifacts:
            for sba in reversed(sb_artifacts):
                if sba.get("filename", "").lower().endswith(".csv"):
                    package.resolved_target_artifact = sba
                    AuditLogger.log_event(
                        action="TASK_CONTEXT_RESOLVED",
                        component="agents.context_manager",
                        status="success",
                        user_id=user_id,
                        username=username,
                        role=role,
                        resource=conversation_id,
                        metadata={"resolution_type": "sandbox_artifact", "target_artifact_id": sba.get("id"), "filename": sba.get("filename")}
                    )
                    break

        # Check for Document conversion / follow-up (e.g. "Convert that to PDF", "Export that report as PDF")
        convert_patterns = [
            r"\b(convert|export|transform)\b.*\b(to pdf|as pdf|to docx|as docx)\b",
            r"\b(convert that|convert the report|export that|convert it)\b"
        ]
        if any(bool(re.search(pat, q_lower)) for pat in convert_patterns) and gen_docs:
            for gd in reversed(gen_docs):
                package.resolved_target_artifact = gd
                AuditLogger.log_event(
                    action="TASK_CONTEXT_RESOLVED",
                    component="agents.context_manager",
                    status="success",
                    user_id=user_id,
                    username=username,
                    role=role,
                    resource=conversation_id,
                    metadata={"resolution_type": "generated_document", "target_artifact_id": gd.get("id"), "filename": gd.get("filename")}
                )
                break

        # C. Resolve Document follow-ups (e.g. "What were the main findings?", "Analyze those findings")
        doc_anaphora_patterns = [
            "those findings", "the findings", "main findings", "three most important findings",
            "important findings", "key findings", "safety findings", "that document", "this document",
            "the document", "that report", "this report", "the report", "same document", "same report",
            "from that document", "from that report", "in that document", "in that report",
            "according to the document", "according to the report", "approval note from those",
            "approval note based on those", "recommendations in that", "recommendations from that",
            "maintenance recommendations"
        ]
        if any(p in q_lower for p in doc_anaphora_patterns) and package.referenced_documents:
            # Resolve to the most recently active document in this conversation
            package.resolved_target_doc = package.referenced_documents[-1]
            AuditLogger.log_event(
                action="TASK_CONTEXT_RESOLVED",
                component="agents.context_manager",
                status="success",
                user_id=user_id,
                username=username,
                role=role,
                resource=conversation_id,
                metadata={"resolution_type": "referenced_document", "target_doc_id": package.resolved_target_doc.get("id")}
            )

        # D. Resolve Model Selection Inquiries (e.g. "What model did you use for the previous image?", "Which model was used?")
        model_inquiry_patterns = [
            "what model did you use", "which model did you use", "what model was used", "which model was selected",
            "what model did you select", "model did you use", "model was used", "what model handled"
        ]
        if any(p in q_lower for p in model_inquiry_patterns) and all_messages:
            is_vision_inquiry = any(w in q_lower for w in ["image", "vision", "p&id", "diagram", "scanned", "photo"])
            target_model_entry = None
            for m in reversed(all_messages):
                if m.get("role") == "assistant":
                    meta = m.get("metadata") or {}
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except Exception:
                            meta = {}
                    r_info = meta.get("routing_info") or {}
                    m_model = meta.get("selected_model") or meta.get("model") or r_info.get("selected_model")
                    m_task = meta.get("task_type") or r_info.get("task_type") or "task"
                    if m_model:
                        if is_vision_inquiry:
                            if m_task in ("VISION_ANALYSIS", "CATEGORY_OCR", "IMAGE_ANALYSIS") or "vl" in m_model:
                                target_model_entry = {"selected_model": m_model, "task_type": m_task}
                                break
                        else:
                            target_model_entry = {"selected_model": m_model, "task_type": m_task}
                            break

            if target_model_entry:
                package.resolved_model_info = target_model_entry
                AuditLogger.log_event(
                    action="TASK_CONTEXT_RESOLVED",
                    component="agents.context_manager",
                    status="success",
                    user_id=user_id,
                    username=username,
                    role=role,
                    resource=conversation_id,
                    metadata={"resolution_type": "model_selection", "selected_model": target_model_entry.get("selected_model")}
                )

        # E. Resolve Created File / Artifact Inquiries (e.g. "What file did you create during the Python execution?")
        created_file_patterns = [
            "what file did you create", "which file did you create", "what file was created",
            "file did you create during", "files did you create", "what file did you generate",
            "what script did you write", "which script did you create"
        ]
        if any(p in q_lower for p in created_file_patterns):
            target_file = None
            if sb_artifacts:
                target_file = sb_artifacts[-1]
            elif gen_docs:
                target_file = gen_docs[-1]
            if target_file:
                package.resolved_created_file = target_file
                AuditLogger.log_event(
                    action="TASK_CONTEXT_RESOLVED",
                    component="agents.context_manager",
                    status="success",
                    user_id=user_id,
                    username=username,
                    role=role,
                    resource=conversation_id,
                    metadata={"resolution_type": "created_file", "filename": target_file.get("filename")}
                )

        # 6. Task Summary Compilation (if conversation has > 6 messages)
        if len(all_messages) > 6:
            summary_parts = []
            if package.referenced_documents:
                doc_names = ", ".join(d.get("filename", "") for d in package.referenced_documents)
                summary_parts.append(f"Documents Analyzed: {doc_names}")
            if package.generated_artifacts:
                art_names = ", ".join(a.get("filename", "") for a in package.generated_artifacts)
                summary_parts.append(f"Generated Artifacts: {art_names}")
            if sandbox_runs:
                summary_parts.append(f"Executions Completed: {len(sandbox_runs)} sandbox runs")
            if not summary_parts:
                summary_parts.append(f"Multi-turn conversation history with {len(all_messages)} previous exchanges")
            package.context_summary = " | ".join(summary_parts)

        # 7. Model-Aware Context Window Budgeting & Priority Trimming
        model_limit = self.get_model_context_limit(model_id)
        # Reserve budget for system prompt & generation output (e.g. 2048 tokens)
        max_history_budget = min(self.default_context_budget, max(1024, model_limit - 2048))

        # Start with recent messages up to window limit
        candidate_messages = all_messages[-self.max_messages_window:]
        total_estimated_tokens = self.estimate_tokens(current_request)
        if package.context_summary:
            total_estimated_tokens += self.estimate_tokens(package.context_summary)
        if package.resolved_execution_result:
            total_estimated_tokens += self.estimate_tokens(str(package.resolved_execution_result.get("stdout", "")))

        bounded_messages = []
        truncated = False

        # Pack messages newest to oldest within token budget
        for msg in reversed(candidate_messages):
            msg_tokens = self.estimate_tokens(msg.get("content", ""))
            if total_estimated_tokens + msg_tokens <= max_history_budget:
                bounded_messages.insert(0, msg)
                total_estimated_tokens += msg_tokens
            else:
                truncated = True

        if len(all_messages) > len(bounded_messages):
            truncated = True

        package.recent_messages = bounded_messages

        # 8. Compute Observability Telemetry
        sources_count = len(bounded_messages) + (1 if package.resolved_target_doc else 0) + (1 if package.resolved_target_artifact else 0) + (1 if package.resolved_execution_result else 0)
        package.telemetry = {
            "context_messages_used": len(bounded_messages),
            "context_documents_used": len(package.referenced_documents),
            "context_artifacts_used": len(package.generated_artifacts),
            "context_truncated": truncated,
            "context_token_estimate": total_estimated_tokens,
            "memory_source_count": sources_count
        }

        # Log Context Retrieval Event
        AuditLogger.log_event(
            action="CONTEXT_RETRIEVED",
            component="agents.context_manager",
            status="success",
            user_id=user_id,
            username=username,
            role=role,
            resource=conversation_id,
            metadata={
                "session_id": conversation_id,
                "context_messages_used": len(bounded_messages),
                "context_documents_used": len(package.referenced_documents),
                "context_artifacts_used": len(package.generated_artifacts),
                "context_truncated": truncated,
                "context_token_estimate": total_estimated_tokens,
                "memory_source_count": sources_count
            }
        )

        if truncated:
            AuditLogger.log_event(
                action="CONTEXT_TRUNCATED",
                component="agents.context_manager",
                status="success",
                user_id=user_id,
                username=username,
                role=role,
                resource=conversation_id,
                metadata={
                    "session_id": conversation_id,
                    "context_token_estimate": total_estimated_tokens,
                    "max_history_budget": max_history_budget
                }
            )

        return package
