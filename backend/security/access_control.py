import sqlite3
import logging
from typing import Dict, Any, Optional, List, Union
from backend.security.database import get_db_path
from backend.security.audit import AuditLogger

logger = logging.getLogger("aegis.security.access_control")

def _extract_user_attrs(current_user: Any) -> Dict[str, Any]:
    """Safely normalizes user identity, role, and department from dict or sqlite3.Row."""
    if current_user is None:
        return {"id": None, "username": "anonymous", "role": "user", "department_id": None, "department_name": None, "is_admin": False}

    user_id = None
    username = None
    role = "user"
    dept_id = None
    dept_name = None

    if isinstance(current_user, dict):
        user_id = current_user.get("id")
        username = current_user.get("username")
        role = current_user.get("role", "user")
        dept_id = current_user.get("department_id")
        dept_name = current_user.get("department_name")
    elif hasattr(current_user, "keys") or hasattr(current_user, "__getitem__"):
        try:
            user_id = current_user["id"]
        except Exception:
            user_id = getattr(current_user, "id", None)
        try:
            username = current_user["username"]
        except Exception:
            username = getattr(current_user, "username", "anonymous")
        try:
            role = current_user["role"]
        except Exception:
            role = getattr(current_user, "role", "user")
        try:
            dept_id = current_user["department_id"]
        except Exception:
            dept_id = getattr(current_user, "department_id", None)
        try:
            dept_name = current_user["department_name"]
        except Exception:
            dept_name = getattr(current_user, "department_name", None)
    else:
        user_id = getattr(current_user, "id", None)
        username = getattr(current_user, "username", "anonymous")
        role = getattr(current_user, "role", "user")
        dept_id = getattr(current_user, "department_id", None)
        dept_name = getattr(current_user, "department_name", None)

    # If department_id is missing, query database to resolve fresh department membership
    if user_id is not None and (dept_id is None or dept_name is None):
        try:
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT department_id, department_name FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                dept_id = row[0]
                dept_name = row[1]
            conn.close()
        except Exception:
            pass

    return {
        "id": user_id,
        "username": username,
        "role": role,
        "department_id": dept_id,
        "department_name": dept_name,
        "is_admin": role == "admin"
    }

def _fetch_document_row(document_or_id: Union[str, Dict[str, Any], sqlite3.Row], db: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """Fetches full document record from SQLite if passed as ID string, or normalizes if passed as dict/row."""
    if isinstance(document_or_id, dict):
        return document_or_id
    if isinstance(document_or_id, sqlite3.Row):
        return dict(document_or_id)

    doc_id = str(document_or_id)
    should_close = False
    conn = db
    if conn is None:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        should_close = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        if should_close and conn:
            conn.close()

def can_access_document(
    current_user: Any,
    document_or_id: Union[str, Dict[str, Any], sqlite3.Row],
    required_permission: str = "READ",
    db: Optional[sqlite3.Connection] = None,
    permission: Optional[str] = None
) -> bool:
    """
    Authoritative single backend authorization gate for all document access.
    
    Evaluates:
    1. Authenticated User Identity & Role
    2. Document Ownership
    3. Document Visibility Policy (PRIVATE, DEPARTMENT, SHARED, ORGANIZATION)
    4. Explicit Access Control List (document_permissions)
    5. Administrative Governance & Least-Privilege Rules
    
    Permissions supported:
    - READ
    - DOWNLOAD
    - USE_IN_RAG
    - EDIT
    - DELETE
    - SHARE
    """
    user_attrs = _extract_user_attrs(current_user)
    user_id = user_attrs["id"]
    username = user_attrs["username"]
    is_admin = user_attrs["is_admin"]
    user_dept_id = user_attrs["department_id"]

    doc = _fetch_document_row(document_or_id, db=db)
    if not doc:
        return False

    doc_id = doc.get("id") or doc.get("document_id")
    owner_id = doc.get("owner_id")
    owner_username = doc.get("owner_username")
    owner_dept_id = doc.get("owner_department_id")
    visibility = (doc.get("visibility") or "PRIVATE").upper().strip()
    req_perm = (permission or required_permission).upper().strip()

    # 1. Administrator has access to all operations
    if is_admin:
        return True

    # 2. Document Owner has full access to all operations
    if user_id is not None and owner_id is not None and (owner_id == user_id or str(owner_id) == str(user_id)):
        return True
    if username and owner_username and username == owner_username:
        return True

    # 3. Read permissions category: READ, DOWNLOAD, USE_IN_RAG
    read_permissions = {"READ", "DOWNLOAD", "USE_IN_RAG"}

    # 4. Explicit ACL Check (document_permissions)
    should_close = False
    conn = db
    if conn is None:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        should_close = True

    try:
        cursor = conn.cursor()
        # Check explicit user-level permission
        if user_id is not None:
            cursor.execute(
                "SELECT permission FROM document_permissions WHERE document_id = ? AND user_id = ?",
                (doc_id, user_id)
            )
            for row in cursor.fetchall():
                p = (row["permission"] if isinstance(row, sqlite3.Row) else row[0]).upper().strip()
                if p in ["ALL", "FULL_CONTROL", "MANAGE"]:
                    return True
                if p == req_perm:
                    return True
                if p == "READ" and req_perm in read_permissions:
                    return True

        # Check explicit department-level permission
        if user_dept_id is not None:
            cursor.execute(
                "SELECT permission FROM document_permissions WHERE document_id = ? AND department_id = ?",
                (doc_id, user_dept_id)
            )
            for row in cursor.fetchall():
                p = (row["permission"] if isinstance(row, sqlite3.Row) else row[0]).upper().strip()
                if p in ["ALL", "FULL_CONTROL", "MANAGE"]:
                    return True
                if p == req_perm:
                    return True
                if p == "READ" and req_perm in read_permissions:
                    return True
    finally:
        if should_close and conn:
            conn.close()

    # 5. Organization Policy: all authenticated users can READ / DOWNLOAD / USE_IN_RAG
    if visibility == "ORGANIZATION" and req_perm in read_permissions:
        return True

    # 6. Department Policy: users belonging to the document's owner department can READ / DOWNLOAD / USE_IN_RAG
    if visibility == "DEPARTMENT" and req_perm in read_permissions:
        if user_dept_id is not None and owner_dept_id is not None and user_dept_id == owner_dept_id:
            return True

    # 7. Otherwise, Access Denied
    return False

def get_accessible_document_ids(
    current_user: Any,
    required_permission: str = "READ",
    db: Optional[sqlite3.Connection] = None,
    permission: Optional[str] = None
) -> List[str]:
    """
    Returns the complete list of document IDs the current authenticated user is authorized to access.
    Used for server-side document listing and pre-retrieval vector filtering in RAG.
    """
    user_attrs = _extract_user_attrs(current_user)
    user_id = user_attrs["id"]
    user_dept_id = user_attrs["department_id"]
    req_perm = (permission or required_permission).upper().strip()

    if user_id is None:
        return []

    should_close = False
    conn = db
    if conn is None:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        should_close = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE status = 'indexed'")
        rows = cursor.fetchall()
        
        accessible_ids = []
        for r in rows:
            doc_dict = dict(r)
            if can_access_document(current_user, doc_dict, required_permission=req_perm, db=conn):
                accessible_ids.append(doc_dict["id"])
                
        return accessible_ids
    finally:
        if should_close and conn:
            conn.close()

def can_access_generated_document(
    current_user: Any,
    generated_doc_or_id: Union[str, Dict[str, Any], sqlite3.Row],
    required_permission: str = "READ",
    db: Optional[sqlite3.Connection] = None
) -> bool:
    """
    Authoritative access gate for generated documents (PDF/DOCX reports).
    Ensures generated reports inherit and respect source document confidentiality.
    """
    user_attrs = _extract_user_attrs(current_user)
    user_id = user_attrs["id"]
    is_admin = user_attrs["is_admin"]
    user_dept_id = user_attrs["department_id"]

    should_close = False
    conn = db
    if conn is None:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        should_close = True

    try:
        cursor = conn.cursor()
        doc = None
        if isinstance(generated_doc_or_id, dict):
            doc = generated_doc_or_id
        elif isinstance(generated_doc_or_id, sqlite3.Row):
            doc = dict(generated_doc_or_id)
        else:
            cursor.execute("SELECT * FROM generated_documents WHERE id = ?", (str(generated_doc_or_id),))
            row = cursor.fetchone()
            doc = dict(row) if row else None

        if not doc:
            return False

        owner_id = doc.get("owner_id")
        owner_dept_id = doc.get("owner_department_id")
        visibility = (doc.get("visibility") or "PRIVATE").upper().strip()

        # 1. Owner has full access
        if user_id is not None and owner_id is not None and owner_id == user_id:
            return True

        # 2. Administrator has access
        if is_admin:
            return True

        # 3. Organization policy
        if visibility == "ORGANIZATION":
            return True

        # 4. Department policy
        if visibility == "DEPARTMENT" and user_dept_id is not None and owner_dept_id is not None and user_dept_id == owner_dept_id:
            return True

        # 5. Check if derived from accessible source documents
        src_ids = doc.get("source_document_ids", "")
        if src_ids:
            src_list = [s.strip() for s in src_ids.split(",") if s.strip()]
            if src_list:
                # If user can access all source documents, grant access
                can_access_sources = all(can_access_document(current_user, s_id, "READ", db=conn) for s_id in src_list)
                if can_access_sources:
                    return True

        return False
    finally:
        if should_close and conn:
            conn.close()
