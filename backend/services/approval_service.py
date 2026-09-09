import os
import json
import uuid
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union, Tuple, Set

from backend.security.database import get_db_path
from backend.security.models import ApprovalStatus, ApprovalActionType
from backend.security.audit import AuditLogger
from backend.security.access_control import _extract_user_attrs

logger = logging.getLogger("aegis.services.approval_service")

# Authorized roles permitted to review and resolve approval requests
AUTHORIZED_REVIEWER_ROLES: Set[str] = {"admin", "reviewer", "supervisor", "lead"}

# Forbidden sensitive patterns that must not appear in payloads or rejection notes
FORBIDDEN_PAYLOAD_PATTERNS = {
    "password", "passhash", "token", "secret", "jwt",
    "private_key", "api_key", "bearer ", "sk-", "ghp_"
}

# Maximum byte sizes for security bounding
MAX_PAYLOAD_JSON_BYTES = 65536  # 64 KB
MAX_REJECTION_REASON_CHARS = 1000


class ApprovalError(Exception):
    """Base exception for all Human-In-The-Loop approval operations."""
    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval request ID cannot be found."""
    pass


class InvalidStateTransitionError(ApprovalError):
    """Raised when an invalid lifecycle state transition is attempted."""
    pass


class ApprovalAuthorizationError(ApprovalError):
    """Raised when a reviewer is unauthorized by role, department isolation, or segregation of duties."""
    pass


class ApprovalValidationError(ApprovalError):
    """Raised when approval request data, payloads, or rejection reasons fail validation."""
    pass


# State Machine Transition Rules
VALID_STATE_TRANSITIONS: Dict[str, Set[str]] = {
    ApprovalStatus.PENDING.value: {
        ApprovalStatus.WAITING_FOR_HUMAN.value,
        ApprovalStatus.FAILED.value
    },
    ApprovalStatus.WAITING_FOR_HUMAN.value: {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.MODIFIED.value,
        ApprovalStatus.REJECTED.value,
        ApprovalStatus.EXPIRED.value,
        ApprovalStatus.FAILED.value
    },
    ApprovalStatus.APPROVED.value: set(),   # Terminal
    ApprovalStatus.MODIFIED.value: set(),   # Terminal for approval review phase
    ApprovalStatus.REJECTED.value: set(),   # Terminal
    ApprovalStatus.EXPIRED.value: set(),    # Terminal
    ApprovalStatus.FAILED.value: set()      # Terminal
}


def _sanitize_dict_or_json(raw_payload: Union[Dict[str, Any], str, Any]) -> str:
    """
    Validates, strips confidential/forbidden patterns, bounds size, and serializes payload to JSON.
    """
    if raw_payload is None:
        return "{}"

    data: Any = raw_payload
    if isinstance(raw_payload, str):
        raw_str = raw_payload.strip()
        if not raw_str:
            return "{}"
        if len(raw_str.encode("utf-8")) > MAX_PAYLOAD_JSON_BYTES:
            raise ApprovalValidationError(
                f"Approval payload exceeds maximum allowed size of {MAX_PAYLOAD_JSON_BYTES} bytes."
            )
        try:
            data = json.loads(raw_str)
        except Exception as e:
            raise ApprovalValidationError(f"Invalid JSON in approval payload: {str(e)}")

    if not isinstance(data, dict):
        raise ApprovalValidationError("Approval payload must be a JSON object / dictionary.")

    # Preliminary byte check on dict before processing
    try:
        raw_dump = json.dumps(data, default=str)
        if len(raw_dump.encode("utf-8")) > MAX_PAYLOAD_JSON_BYTES:
            raise ApprovalValidationError(
                f"Approval payload exceeds maximum allowed size of {MAX_PAYLOAD_JSON_BYTES} bytes."
            )
    except ApprovalValidationError:
        raise
    except Exception:
        pass

    # Deep sanitization of dictionary
    def _clean_node(node: Any) -> Any:
        if isinstance(node, dict):
            cleaned = {}
            for k, v in node.items():
                k_lower = str(k).lower()
                if any(p in k_lower for p in FORBIDDEN_PAYLOAD_PATTERNS):
                    continue
                cleaned[str(k)] = _clean_node(v)
            return cleaned
        elif isinstance(node, list):
            return [_clean_node(item) for item in node[:100]]
        elif isinstance(node, str):
            val_lower = node.lower()
            if (val_lower.startswith("bearer ") or
                val_lower.startswith("sk-") or
                val_lower.startswith("ghp_") or
                val_lower.startswith("eyjhbgci") or
                val_lower.startswith("api_key_") or
                val_lower.startswith("sec_key_")):
                return "[REDACTED_SENSITIVE_CREDENTIAL]"
            return node
        else:
            return node

    sanitized = _clean_node(data)
    serialized = json.dumps(sanitized, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > MAX_PAYLOAD_JSON_BYTES:
        raise ApprovalValidationError(
            f"Approval payload exceeds maximum allowed size of {MAX_PAYLOAD_JSON_BYTES} bytes."
        )
    return serialized


def _sanitize_text_field(text: str, max_chars: int = MAX_REJECTION_REASON_CHARS) -> str:
    """Sanitizes text fields such as rejection reasons."""
    if not text or not isinstance(text, str):
        return ""
    clean = text.strip()
    val_lower = clean.lower()
    if any(p in val_lower for p in ["password", "bearer ", "eyjhbgci", "private_key"]):
        # Remove or mask sensitive phrases
        for p in ["password", "bearer ", "private_key"]:
            clean = clean.replace(p, "[REDACTED]")
    return clean[:max_chars]


class ApprovalService:
    """
    Sovereign Human-In-The-Loop (HITL) Approval Service.
    Enforces atomic state transitions, strict RBAC reviewer roles, department isolation boundaries,
    segregation of duties, payload sanitization, and cryptographic HMAC-SHA256 audit chaining.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()

    def _get_connection(self, db: Optional[sqlite3.Connection] = None) -> Tuple[sqlite3.Connection, bool]:
        """Returns active sqlite3 connection and a boolean indicating if it should be closed by caller."""
        if db is not None:
            return db, False
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn, True

    def create_request(
        self,
        requester: Any,
        action_type: Union[str, ApprovalActionType],
        proposed_payload: Union[Dict[str, Any], str],
        plan_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        step_id: Optional[str] = None,
        department_id: Optional[int] = None,
        department_name: Optional[str] = None,
        expires_at: Optional[str] = None,
        db: Optional[sqlite3.Connection] = None
    ) -> Dict[str, Any]:
        """
        Creates a new HITL approval request in WAITING_FOR_HUMAN state and records APPROVAL_REQUESTED audit event.
        """
        user_attrs = _extract_user_attrs(requester)
        req_id = user_attrs["id"]
        req_username = user_attrs["username"] or "anonymous"
        req_role = user_attrs["role"]

        resolved_dept_id = department_id if department_id is not None else user_attrs["department_id"]
        resolved_dept_name = department_name or user_attrs["department_name"] or ""

        # Validate action_type
        if isinstance(action_type, ApprovalActionType):
            action_type_val = action_type.value
        else:
            action_type_str = str(action_type).upper().strip()
            try:
                action_type_val = ApprovalActionType(action_type_str).value
            except ValueError:
                raise ApprovalValidationError(f"Invalid approval action_type: '{action_type}'")

        # Sanitize and serialize proposed payload
        serialized_payload = _sanitize_dict_or_json(proposed_payload)

        # Validate expires_at format if provided
        if expires_at is not None:
            try:
                # Ensure valid ISO timestamp
                datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except Exception as e:
                raise ApprovalValidationError(f"Invalid ISO-8601 format for expires_at: '{expires_at}' ({str(e)})")

        approval_id = f"appr_{uuid.uuid4().hex[:12]}"
        now_utc = datetime.now(timezone.utc).isoformat()
        initial_status = ApprovalStatus.WAITING_FOR_HUMAN.value

        conn, should_close = self._get_connection(db)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO approval_requests (
                    id, plan_id, conversation_id, step_id,
                    requester_id, requester_username,
                    reviewer_id, reviewer_username, reviewer_role,
                    department_id, department_name,
                    status, action_type,
                    proposed_payload_json, modified_payload_json,
                    rejection_reason, created_at, reviewed_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, ?)
            """, (
                approval_id, plan_id, conversation_id, step_id,
                req_id, req_username,
                resolved_dept_id, resolved_dept_name,
                initial_status, action_type_val,
                serialized_payload, now_utc, expires_at
            ))
            conn.commit()

            # Record tamper-evident cryptographic audit log
            AuditLogger.log_event(
                action="APPROVAL_REQUESTED",
                component="services.approval_service",
                status="success",
                user_id=req_id,
                username=req_username,
                role=req_role,
                resource=f"approval:{approval_id}",
                metadata={
                    "approval_id": approval_id,
                    "requester_id": req_id,
                    "requester_username": req_username,
                    "action_type": action_type_val,
                    "department_id": resolved_dept_id,
                    "department_name": resolved_dept_name,
                    "plan_id": plan_id,
                    "step_id": step_id,
                    "conversation_id": conversation_id,
                    "approval_status": initial_status
                }
            )

            cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,))
            row = cursor.fetchone()
            return dict(row)
        finally:
            if should_close:
                conn.close()

    def _check_and_apply_expiration(self, row_dict: Dict[str, Any], conn: sqlite3.Connection) -> Dict[str, Any]:
        """Checks if a WAITING_FOR_HUMAN request has expired and updates database atomically."""
        if row_dict["status"] != ApprovalStatus.WAITING_FOR_HUMAN.value:
            return row_dict

        expires_at_str = row_dict.get("expires_at")
        if not expires_at_str:
            return row_dict

        try:
            exp_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if now_dt > exp_dt:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE approval_requests
                    SET status = ?
                    WHERE id = ? AND status = ?
                """, (
                    ApprovalStatus.EXPIRED.value,
                    row_dict["id"],
                    ApprovalStatus.WAITING_FOR_HUMAN.value
                ))
                if cursor.rowcount > 0:
                    conn.commit()
                    row_dict["status"] = ApprovalStatus.EXPIRED.value

                    AuditLogger.log_event(
                        action="APPROVAL_EXPIRED",
                        component="services.approval_service",
                        status="success",
                        resource=f"approval:{row_dict['id']}",
                        metadata={
                            "approval_id": row_dict["id"],
                            "approval_status": ApprovalStatus.EXPIRED.value,
                            "action_type": row_dict.get("action_type"),
                            "requester_id": row_dict.get("requester_id"),
                            "department_id": row_dict.get("department_id"),
                            "plan_id": row_dict.get("plan_id"),
                            "step_id": row_dict.get("step_id"),
                            "conversation_id": row_dict.get("conversation_id"),
                            "reason": "TIMEOUT_EXPIRED"
                        }
                    )
        except Exception as e:
            logger.warning(f"Error checking expiration for approval {row_dict.get('id')}: {e}")

        return row_dict

    def get_request(self, approval_id: str, db: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        """Retrieves an approval request by ID, evaluating expiration deterministically."""
        if not approval_id:
            return None

        conn, should_close = self._get_connection(db)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            return self._check_and_apply_expiration(res, conn)
        finally:
            if should_close:
                conn.close()

    def get_active_approval_for_plan(
        self,
        plan_id: str,
        step_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        db: Optional[sqlite3.Connection] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves any active WAITING_FOR_HUMAN approval request bound to the specified plan/step.
        Prevents duplicate approval request creation across re-runs or retries.
        """
        if not plan_id:
            return None
        conn, should_close = self._get_connection(db)
        try:
            query = "SELECT * FROM approval_requests WHERE plan_id = ? AND status = ?"
            params: List[Any] = [plan_id, ApprovalStatus.WAITING_FOR_HUMAN.value]
            if step_id:
                query += " AND step_id = ?"
                params.append(step_id)
            if conversation_id:
                query += " AND conversation_id = ?"
                params.append(conversation_id)
            query += " ORDER BY created_at DESC LIMIT 1"
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            if not row:
                return None
            return self._check_and_apply_expiration(dict(row), conn)
        finally:
            if should_close:
                conn.close()

    def list_requests(
        self,
        requester_id: Optional[int] = None,
        department_id: Optional[int] = None,
        status: Optional[Union[str, ApprovalStatus]] = None,
        action_type: Optional[Union[str, ApprovalActionType]] = None,
        plan_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        limit: int = 100,
        db: Optional[sqlite3.Connection] = None
    ) -> List[Dict[str, Any]]:
        """Lists approval requests matching specified filters."""
        conn, should_close = self._get_connection(db)
        try:
            query = "SELECT * FROM approval_requests WHERE 1=1"
            params: List[Any] = []

            if requester_id is not None:
                query += " AND requester_id = ?"
                params.append(requester_id)
            if department_id is not None:
                query += " AND department_id = ?"
                params.append(department_id)
            if status is not None:
                st_val = status.value if isinstance(status, ApprovalStatus) else str(status)
                query += " AND status = ?"
                params.append(st_val)
            if action_type is not None:
                act_val = action_type.value if isinstance(action_type, ApprovalActionType) else str(action_type)
                query += " AND action_type = ?"
                params.append(act_val)
            if plan_id is not None:
                query += " AND plan_id = ?"
                params.append(plan_id)
            if conversation_id is not None:
                query += " AND conversation_id = ?"
                params.append(conversation_id)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                row_dict = dict(r)
                results.append(self._check_and_apply_expiration(row_dict, conn))
            return results
        finally:
            if should_close:
                conn.close()

    def _validate_reviewer_authorization(
        self,
        request_row: Dict[str, Any],
        reviewer: Any,
        operation: str = "review"
    ) -> Dict[str, Any]:
        """
        Enforces:
        1. Authenticated reviewer identity
        2. Authorized role check (admin, reviewer, supervisor, lead)
        3. Department isolation boundary (non-admin reviewer must match request department)
        4. Segregation of duties (requester cannot approve/modify/reject their own request)
        """
        user_attrs = _extract_user_attrs(reviewer)
        rev_id = user_attrs["id"]
        rev_username = user_attrs["username"]
        rev_role = (user_attrs["role"] or "user").lower()
        rev_dept_id = user_attrs["department_id"]
        is_admin = user_attrs["is_admin"]

        # 1. Identity Check
        if rev_id is None and (not rev_username or rev_username == "anonymous"):
            raise ApprovalAuthorizationError("Unauthenticated reviewer: a valid authenticated user identity is required.")

        # 2. Role Check
        if not is_admin and rev_role not in AUTHORIZED_REVIEWER_ROLES:
            raise ApprovalAuthorizationError(
                f"Unauthorized reviewer role '{rev_role}'. Permitted roles: {sorted(list(AUTHORIZED_REVIEWER_ROLES))}"
            )

        # 3. Segregation of Duties
        req_id = request_row.get("requester_id")
        req_username = request_row.get("requester_username")

        if rev_id is not None and req_id is not None and str(rev_id) == str(req_id):
            raise ApprovalAuthorizationError(
                "Segregation of duties violation: requester cannot approve or review their own request."
            )
        if rev_username and req_username and rev_username.lower().strip() == req_username.lower().strip():
            raise ApprovalAuthorizationError(
                "Segregation of duties violation: requester cannot approve or review their own request."
            )

        # 4. Department Isolation
        req_dept_id = request_row.get("department_id")
        if not is_admin:
            if req_dept_id is not None and rev_dept_id is not None:
                if int(req_dept_id) != int(rev_dept_id):
                    raise ApprovalAuthorizationError(
                        f"Cross-department review prohibited: reviewer department ({rev_dept_id}) "
                        f"does not match request department ({req_dept_id})."
                    )
            elif req_dept_id is not None and rev_dept_id is None:
                raise ApprovalAuthorizationError(
                    "Department isolation violation: reviewer has no department assigned."
                )

        return user_attrs

    def approve(
        self,
        approval_id: str,
        reviewer: Any,
        db: Optional[sqlite3.Connection] = None
    ) -> Dict[str, Any]:
        """
        Authorizes reviewer and transitions request from WAITING_FOR_HUMAN -> APPROVED.
        Atomically updates database and records APPROVAL_GRANTED in HMAC audit log.
        """
        conn, should_close = self._get_connection(db)
        try:
            req = self.get_request(approval_id, db=conn)
            if not req:
                raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

            # Validate authorization rules
            rev_attrs = self._validate_reviewer_authorization(req, reviewer, operation="approve")
            rev_id = rev_attrs["id"]
            rev_username = rev_attrs["username"]
            rev_role = rev_attrs["role"]

            # Validate lifecycle state transition
            current_status = req["status"]
            if current_status != ApprovalStatus.WAITING_FOR_HUMAN.value:
                raise InvalidStateTransitionError(
                    f"Cannot transition approval '{approval_id}' from '{current_status}' to 'APPROVED'. "
                    f"Only requests in '{ApprovalStatus.WAITING_FOR_HUMAN.value}' can be approved."
                )

            now_utc = datetime.now(timezone.utc).isoformat()

            # Concurrency-safe atomic update
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE approval_requests
                SET status = ?,
                    reviewer_id = ?,
                    reviewer_username = ?,
                    reviewer_role = ?,
                    reviewed_at = ?
                WHERE id = ? AND status = ?
            """, (
                ApprovalStatus.APPROVED.value,
                rev_id,
                rev_username,
                rev_role,
                now_utc,
                approval_id,
                ApprovalStatus.WAITING_FOR_HUMAN.value
            ))

            if cursor.rowcount == 0:
                # State was concurrently changed by another reviewer
                latest = self.get_request(approval_id, db=conn)
                latest_status = latest["status"] if latest else "UNKNOWN"
                raise InvalidStateTransitionError(
                    f"Concurrent modification conflict: approval '{approval_id}' status changed to '{latest_status}'."
                )

            conn.commit()

            # Record cryptographic audit entry
            AuditLogger.log_event(
                action="APPROVAL_GRANTED",
                component="services.approval_service",
                status="success",
                user_id=rev_id,
                username=rev_username,
                role=rev_role,
                resource=f"approval:{approval_id}",
                metadata={
                    "approval_id": approval_id,
                    "reviewer_id": rev_id,
                    "reviewer_username": rev_username,
                    "reviewer_role": rev_role,
                    "approval_status": ApprovalStatus.APPROVED.value,
                    "requester_id": req.get("requester_id"),
                    "requester_username": req.get("requester_username"),
                    "action_type": req.get("action_type"),
                    "department_id": req.get("department_id"),
                    "plan_id": req.get("plan_id"),
                    "step_id": req.get("step_id"),
                    "conversation_id": req.get("conversation_id")
                }
            )

            cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,))
            return dict(cursor.fetchone())
        finally:
            if should_close:
                conn.close()

    def modify(
        self,
        approval_id: str,
        reviewer: Any,
        modified_payload: Union[Dict[str, Any], str],
        db: Optional[sqlite3.Connection] = None
    ) -> Dict[str, Any]:
        """
        Authorizes reviewer and transitions request from WAITING_FOR_HUMAN -> MODIFIED.
        Persists sanitized modified_payload_json and records APPROVAL_MODIFIED in HMAC audit log.
        """
        conn, should_close = self._get_connection(db)
        try:
            req = self.get_request(approval_id, db=conn)
            if not req:
                raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

            # Validate authorization rules
            rev_attrs = self._validate_reviewer_authorization(req, reviewer, operation="modify")
            rev_id = rev_attrs["id"]
            rev_username = rev_attrs["username"]
            rev_role = rev_attrs["role"]

            # Validate lifecycle state transition
            current_status = req["status"]
            if current_status != ApprovalStatus.WAITING_FOR_HUMAN.value:
                raise InvalidStateTransitionError(
                    f"Cannot transition approval '{approval_id}' from '{current_status}' to 'MODIFIED'. "
                    f"Only requests in '{ApprovalStatus.WAITING_FOR_HUMAN.value}' can be modified."
                )

            # Sanitize and serialize modified payload
            serialized_mod = _sanitize_dict_or_json(modified_payload)
            now_utc = datetime.now(timezone.utc).isoformat()

            # Concurrency-safe atomic update
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE approval_requests
                SET status = ?,
                    modified_payload_json = ?,
                    reviewer_id = ?,
                    reviewer_username = ?,
                    reviewer_role = ?,
                    reviewed_at = ?
                WHERE id = ? AND status = ?
            """, (
                ApprovalStatus.MODIFIED.value,
                serialized_mod,
                rev_id,
                rev_username,
                rev_role,
                now_utc,
                approval_id,
                ApprovalStatus.WAITING_FOR_HUMAN.value
            ))

            if cursor.rowcount == 0:
                latest = self.get_request(approval_id, db=conn)
                latest_status = latest["status"] if latest else "UNKNOWN"
                raise InvalidStateTransitionError(
                    f"Concurrent modification conflict: approval '{approval_id}' status changed to '{latest_status}'."
                )

            conn.commit()

            # Record cryptographic audit entry
            AuditLogger.log_event(
                action="APPROVAL_MODIFIED",
                component="services.approval_service",
                status="success",
                user_id=rev_id,
                username=rev_username,
                role=rev_role,
                resource=f"approval:{approval_id}",
                metadata={
                    "approval_id": approval_id,
                    "reviewer_id": rev_id,
                    "reviewer_username": rev_username,
                    "reviewer_role": rev_role,
                    "approval_status": ApprovalStatus.MODIFIED.value,
                    "requester_id": req.get("requester_id"),
                    "requester_username": req.get("requester_username"),
                    "action_type": req.get("action_type"),
                    "department_id": req.get("department_id"),
                    "plan_id": req.get("plan_id"),
                    "step_id": req.get("step_id"),
                    "conversation_id": req.get("conversation_id")
                }
            )

            cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,))
            return dict(cursor.fetchone())
        finally:
            if should_close:
                conn.close()

    def reject(
        self,
        approval_id: str,
        reviewer: Any,
        rejection_reason: str,
        db: Optional[sqlite3.Connection] = None
    ) -> Dict[str, Any]:
        """
        Authorizes reviewer and transitions request from WAITING_FOR_HUMAN -> REJECTED.
        Persists sanitized rejection_reason and records APPROVAL_REJECTED in HMAC audit log.
        """
        if not rejection_reason or not isinstance(rejection_reason, str) or not rejection_reason.strip():
            raise ApprovalValidationError("Rejection reason is required and cannot be empty.")

        sanitized_reason = _sanitize_text_field(rejection_reason)
        if not sanitized_reason.strip():
            raise ApprovalValidationError("Rejection reason cannot consist entirely of filtered sensitive terms.")

        conn, should_close = self._get_connection(db)
        try:
            req = self.get_request(approval_id, db=conn)
            if not req:
                raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

            # Validate authorization rules
            rev_attrs = self._validate_reviewer_authorization(req, reviewer, operation="reject")
            rev_id = rev_attrs["id"]
            rev_username = rev_attrs["username"]
            rev_role = rev_attrs["role"]

            # Validate lifecycle state transition
            current_status = req["status"]
            if current_status != ApprovalStatus.WAITING_FOR_HUMAN.value:
                raise InvalidStateTransitionError(
                    f"Cannot transition approval '{approval_id}' from '{current_status}' to 'REJECTED'. "
                    f"Only requests in '{ApprovalStatus.WAITING_FOR_HUMAN.value}' can be rejected."
                )

            now_utc = datetime.now(timezone.utc).isoformat()

            # Concurrency-safe atomic update
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE approval_requests
                SET status = ?,
                    rejection_reason = ?,
                    reviewer_id = ?,
                    reviewer_username = ?,
                    reviewer_role = ?,
                    reviewed_at = ?
                WHERE id = ? AND status = ?
            """, (
                ApprovalStatus.REJECTED.value,
                sanitized_reason,
                rev_id,
                rev_username,
                rev_role,
                now_utc,
                approval_id,
                ApprovalStatus.WAITING_FOR_HUMAN.value
            ))

            if cursor.rowcount == 0:
                latest = self.get_request(approval_id, db=conn)
                latest_status = latest["status"] if latest else "UNKNOWN"
                raise InvalidStateTransitionError(
                    f"Concurrent modification conflict: approval '{approval_id}' status changed to '{latest_status}'."
                )

            conn.commit()

            # Record cryptographic audit entry
            AuditLogger.log_event(
                action="APPROVAL_REJECTED",
                component="services.approval_service",
                status="success",
                user_id=rev_id,
                username=rev_username,
                role=rev_role,
                resource=f"approval:{approval_id}",
                metadata={
                    "approval_id": approval_id,
                    "reviewer_id": rev_id,
                    "reviewer_username": rev_username,
                    "reviewer_role": rev_role,
                    "approval_status": ApprovalStatus.REJECTED.value,
                    "rejection_reason": sanitized_reason,
                    "requester_id": req.get("requester_id"),
                    "requester_username": req.get("requester_username"),
                    "action_type": req.get("action_type"),
                    "department_id": req.get("department_id"),
                    "plan_id": req.get("plan_id"),
                    "step_id": req.get("step_id"),
                    "conversation_id": req.get("conversation_id")
                }
            )

            cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,))
            return dict(cursor.fetchone())
        finally:
            if should_close:
                conn.close()

    def expire(
        self,
        approval_id: str,
        reason: str = "EXPIRED_TIMEOUT",
        db: Optional[sqlite3.Connection] = None
    ) -> Dict[str, Any]:
        """Explicitly transitions a WAITING_FOR_HUMAN approval request to EXPIRED."""
        conn, should_close = self._get_connection(db)
        try:
            req = self.get_request(approval_id, db=conn)
            if not req:
                raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

            current_status = req["status"]
            if current_status == ApprovalStatus.EXPIRED.value:
                return req

            if current_status != ApprovalStatus.WAITING_FOR_HUMAN.value:
                raise InvalidStateTransitionError(
                    f"Cannot expire approval '{approval_id}' in state '{current_status}'."
                )

            cursor = conn.cursor()
            cursor.execute("""
                UPDATE approval_requests
                SET status = ?
                WHERE id = ? AND status = ?
            """, (
                ApprovalStatus.EXPIRED.value,
                approval_id,
                ApprovalStatus.WAITING_FOR_HUMAN.value
            ))

            if cursor.rowcount == 0:
                latest = self.get_request(approval_id, db=conn)
                latest_status = latest["status"] if latest else "UNKNOWN"
                raise InvalidStateTransitionError(
                    f"Concurrent conflict: approval '{approval_id}' changed to '{latest_status}'."
                )

            conn.commit()

            AuditLogger.log_event(
                action="APPROVAL_EXPIRED",
                component="services.approval_service",
                status="success",
                resource=f"approval:{approval_id}",
                metadata={
                    "approval_id": approval_id,
                    "approval_status": ApprovalStatus.EXPIRED.value,
                    "action_type": req.get("action_type"),
                    "requester_id": req.get("requester_id"),
                    "department_id": req.get("department_id"),
                    "plan_id": req.get("plan_id"),
                    "step_id": req.get("step_id"),
                    "conversation_id": req.get("conversation_id"),
                    "reason": reason
                }
            )

            cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,))
            return dict(cursor.fetchone())
        finally:
            if should_close:
                conn.close()

    def fail(
        self,
        approval_id: str,
        error_message: str,
        db: Optional[sqlite3.Connection] = None
    ) -> Dict[str, Any]:
        """
        Transitions request to FAILED due to a technical/system error.
        Records APPROVAL_FAILED in HMAC audit log.
        """
        conn, should_close = self._get_connection(db)
        try:
            req = self.get_request(approval_id, db=conn)
            if not req:
                raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

            current_status = req["status"]
            if current_status in [ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value, ApprovalStatus.EXPIRED.value]:
                raise InvalidStateTransitionError(
                    f"Cannot fail finalized approval '{approval_id}' in state '{current_status}'."
                )

            clean_error = _sanitize_text_field(error_message, max_chars=500)

            cursor = conn.cursor()
            cursor.execute("""
                UPDATE approval_requests
                SET status = ?
                WHERE id = ?
            """, (
                ApprovalStatus.FAILED.value,
                approval_id
            ))
            conn.commit()

            AuditLogger.log_event(
                action="APPROVAL_FAILED",
                component="services.approval_service",
                status="failure",
                resource=f"approval:{approval_id}",
                metadata={
                    "approval_id": approval_id,
                    "approval_status": ApprovalStatus.FAILED.value,
                    "action_type": req.get("action_type"),
                    "requester_id": req.get("requester_id"),
                    "department_id": req.get("department_id"),
                    "plan_id": req.get("plan_id"),
                    "step_id": req.get("step_id"),
                    "conversation_id": req.get("conversation_id"),
                    "error": clean_error
                }
            )

            cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,))
            return dict(cursor.fetchone())
        finally:
            if should_close:
                conn.close()
