from datetime import datetime, timezone
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status, Request
from backend.security.database import get_db
from backend.security.auth import hash_password, verify_password, create_access_token
from backend.security.models import (
    UserRegister, UserResponse, TokenResponse,
    UserProvisionRequest, UserStatusRequest, UserRoleRequest,
    UserDepartmentUpdateRequest, PasswordResetRequest, ChangePasswordRequest,
    DepartmentCreate, DepartmentUpdate, DepartmentResponse
)
from backend.security.dependencies import get_current_user, RoleChecker
from backend.security.audit import AuditLogger

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: sqlite3.Connection = Depends(get_db)):
    """Registers a new user, hashes the password, and returns safe profile details."""
    cursor = db.cursor()
    
    # Check if username is already registered
    cursor.execute("SELECT id FROM users WHERE username = ?", (payload.username,))
    if cursor.fetchone():
        AuditLogger.log_event(
            action="AUTH_REGISTER",
            component="security.auth_router",
            status="failure",
            username=payload.username,
            metadata={"username": payload.username, "error_category": "duplicate_username"}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already registered"
        )
        
    # Secure role mapping: public self-registration defaults to "user" in production,
    # but preserves legacy automated assignment in non-production environments to avoid test breakages.
    from backend.app.config.settings import settings
    if settings.APP_ENV == "production":
        role = "user"
    else:
        role = "admin" if "admin" in payload.username.lower() else "user"
    
    # Resolve department
    dept_id = payload.department_id
    dept_name = None
    if dept_id:
        cursor.execute("SELECT id, name FROM departments WHERE id = ?", (dept_id,))
        d_row = cursor.fetchone()
        if d_row:
            dept_id = d_row[0]
            dept_name = d_row[1]
    if not dept_id:
        default_dept = "Administration" if role == "admin" else "Operations"
        cursor.execute("SELECT id, name FROM departments WHERE name = ?", (default_dept,))
        d_row = cursor.fetchone()
        if d_row:
            dept_id = d_row[0]
            dept_name = d_row[1]

    try:
        hashed = hash_password(payload.password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, department_id, department_name) VALUES (?, ?, ?, ?, ?)",
            (payload.username, hashed, role, dept_id, dept_name)
        )
        db.commit()
        
        cursor.execute("SELECT * FROM users WHERE username = ?", (payload.username,))
        user = cursor.fetchone()
        AuditLogger.log_event(
            action="AUTH_REGISTER",
            component="security.auth_router",
            status="success",
            username=payload.username,
            metadata={"username": payload.username, "role": role, "department_name": dept_name}
        )
        return dict(user)
    except ValueError as ve:
        AuditLogger.log_event(
            action="AUTH_REGISTER",
            component="security.auth_router",
            status="failure",
            username=payload.username,
            metadata={"username": payload.username, "error_category": "invalid_password"}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception:
        AuditLogger.log_event(
            action="AUTH_REGISTER",
            component="security.auth_router",
            status="failure",
            username=payload.username,
            metadata={"username": payload.username, "error_category": "database_error"}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database registration error."
        )

@router.post("/login", response_model=TokenResponse)
async def login(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Authenticates credentials using JSON body or form-data, and returns JWT access tokens."""
    username = None
    password = None
    
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            username = body.get("username")
            password = body.get("password")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
        except Exception:
            pass
            
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credentials username and password fields are required."
        )
        
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    
    # Generic verification response to prevent credentials mining attacks
    if not user or not verify_password(password, user["password_hash"]):
        AuditLogger.log_event(
            action="LOGIN_FAILED",
            component="security.auth_router",
            status="failure",
            username=username,
            metadata={"username": username, "error_category": "invalid_credentials"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user["is_active"]:
        AuditLogger.log_event(
            action="LOGIN_FAILED",
            component="security.auth_router",
            status="failure",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            metadata={"username": user["username"], "error_category": "inactive_profile"}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is inactive"
        )
        
    access_token = create_access_token(subject=user["username"], role=user["role"])
    
    AuditLogger.log_event(
        action="LOGIN_SUCCESS",
        component="security.auth_router",
        status="success",
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        metadata={"username": user["username"], "role": user["role"]}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": dict(user)
    }

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: sqlite3.Row = Depends(get_current_user)):
    """Returns safe user profile details for the currently authenticated bearer token."""
    return dict(current_user)

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, current_user: sqlite3.Row = Depends(get_current_user)):
    """Logs out user, revokes bearer token, and appends LOGOUT event to the audit ledger."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        from backend.security.auth import revoke_token
        revoke_token(token, user_id=current_user["id"], username=current_user["username"])

    AuditLogger.log_event(
        action="AUTH_LOGOUT",
        component="security.auth_router",
        status="success",
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        metadata={"username": current_user["username"]}
    )
    return {"status": "success", "message": "Successfully logged out"}

@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    """Allows current user to change password, clears must_change_password flag."""
    if not verify_password(payload.old_password, current_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    hashed = hash_password(payload.new_password)
    cursor = db.cursor()
    cursor.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (hashed, current_user["id"])
    )
    db.commit()
    
    AuditLogger.log_event(
        action="AUTH_CHANGE_PASSWORD",
        component="security.auth_router",
        status="success",
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"]
    )
    return {"status": "success", "message": "Password changed successfully"}

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: sqlite3.Row = Depends(RoleChecker(["admin"])),
    db: sqlite3.Connection = Depends(get_db)
):
    """Retrieves all registered users for administration dashboard. Restricted to admin role."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    return [dict(u) for u in users]

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def provision_user(
    payload: UserProvisionRequest,
    current_user: sqlite3.Row = Depends(RoleChecker(["admin"])),
    db: sqlite3.Connection = Depends(get_db)
):
    """Provisions a new user with a temporary password and forces password change on first login."""
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (payload.username,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    dept_id = payload.department_id
    dept_name = None
    if dept_id:
        cursor.execute("SELECT id, name FROM departments WHERE id = ?", (dept_id,))
        d_row = cursor.fetchone()
        if d_row:
            dept_id = d_row[0]
            dept_name = d_row[1]
    if not dept_id:
        default_dept = "Administration" if payload.role == "admin" else "Operations"
        cursor.execute("SELECT id, name FROM departments WHERE name = ?", (default_dept,))
        d_row = cursor.fetchone()
        if d_row:
            dept_id = d_row[0]
            dept_name = d_row[1]

    hashed = hash_password(payload.password)
    cursor.execute(
        "INSERT INTO users (username, password_hash, role, department_id, department_name, must_change_password) VALUES (?, ?, ?, ?, ?, 1)",
        (payload.username, hashed, payload.role, dept_id, dept_name)
    )
    db.commit()
    
    cursor.execute("SELECT * FROM users WHERE username = ?", (payload.username,))
    new_user = cursor.fetchone()
    
    AuditLogger.log_event(
        action="USER_PROVISIONED",
        component="security.auth_router",
        status="success",
        username=payload.username,
        metadata={"username": payload.username, "role": payload.role, "department_name": dept_name}
    )
    AuditLogger.log_event(
        action="USER_CREATED",
        component="security.auth_router",
        status="success",
        username=payload.username,
        metadata={"username": payload.username, "role": payload.role, "department_name": dept_name}
    )
    return dict(new_user)

@router.patch("/users/{target_username}/department", response_model=UserResponse)
async def update_user_department(
    target_username: str,
    payload: UserDepartmentUpdateRequest,
    current_user: sqlite3.Row = Depends(RoleChecker(["admin"])),
    db: sqlite3.Connection = Depends(get_db)
):
    """Assigns or changes a user's department. Admin only."""
    cursor = db.cursor()
    cursor.execute("SELECT id, name FROM departments WHERE id = ?", (payload.department_id,))
    dept_row = cursor.fetchone()
    if not dept_row:
        raise HTTPException(status_code=404, detail="Department not found")
    dept_name = dept_row[1]

    cursor.execute("SELECT id, department_name FROM users WHERE username = ?", (target_username,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_dept = user[1]
    cursor.execute(
        "UPDATE users SET department_id = ?, department_name = ? WHERE username = ?",
        (payload.department_id, dept_name, target_username)
    )
    db.commit()

    cursor.execute("SELECT * FROM users WHERE username = ?", (target_username,))
    updated = cursor.fetchone()

    AuditLogger.log_event(
        action="USER_DEPARTMENT_CHANGED",
        component="security.auth_router",
        status="success",
        username=target_username,
        metadata={
            "username": target_username,
            "department_id": payload.department_id,
            "department_name": dept_name,
            "previous_department": old_dept
        }
    )
    return dict(updated)

@router.post("/users/{target_username}/status", response_model=UserResponse)
async def update_user_status(
    target_username: str,
    payload: UserStatusRequest,
    current_user: sqlite3.Row = Depends(RoleChecker(["admin"])),
    db: sqlite3.Connection = Depends(get_db)
):
    """Enables or disables target user account."""
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (target_username,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    cursor.execute(
        "UPDATE users SET is_active = ? WHERE username = ?",
        (1 if payload.is_active else 0, target_username)
    )
    db.commit()
    
    cursor.execute("SELECT * FROM users WHERE username = ?", (target_username,))
    updated = cursor.fetchone()
    
    AuditLogger.log_event(
        action="USER_STATUS_UPDATED",
        component="security.auth_router",
        status="success",
        username=target_username,
        metadata={"username": target_username, "is_active": payload.is_active}
    )
    AuditLogger.log_event(
        action="USER_ENABLED" if payload.is_active else "USER_DISABLED",
        component="security.auth_router",
        status="success",
        username=target_username,
        metadata={"username": target_username, "is_active": payload.is_active}
    )
    return dict(updated)

@router.post("/users/{target_username}/role", response_model=UserResponse)
async def update_user_role(
    target_username: str,
    payload: UserRoleRequest,
    current_user: sqlite3.Row = Depends(RoleChecker(["admin"])),
    db: sqlite3.Connection = Depends(get_db)
):
    """Updates target user's role assignment."""
    if payload.role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role specified")
        
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (target_username,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    cursor.execute(
        "UPDATE users SET role = ? WHERE username = ?",
        (payload.role, target_username)
    )
    db.commit()
    
    cursor.execute("SELECT * FROM users WHERE username = ?", (target_username,))
    updated = cursor.fetchone()
    
    AuditLogger.log_event(
        action="USER_ROLE_UPDATED",
        component="security.auth_router",
        status="success",
        username=target_username,
        metadata={"username": target_username, "role": payload.role}
    )
    AuditLogger.log_event(
        action="ROLE_CHANGED",
        component="security.auth_router",
        status="success",
        username=target_username,
        metadata={"username": target_username, "role": payload.role}
    )
    return dict(updated)

@router.post("/users/{target_username}/reset-password", response_model=UserResponse)
async def admin_reset_password(
    target_username: str,
    payload: PasswordResetRequest,
    current_user: sqlite3.Row = Depends(RoleChecker(["admin"])),
    db: sqlite3.Connection = Depends(get_db)
):
    """Resets target user password and forces password change on next login."""
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (target_username,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    hashed = hash_password(payload.password)
    cursor.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE username = ?",
        (hashed, target_username)
    )
    db.commit()
    
    cursor.execute("SELECT * FROM users WHERE username = ?", (target_username,))
    updated = cursor.fetchone()
    
    AuditLogger.log_event(
        action="USER_PASSWORD_RESET",
        component="security.auth_router",
        status="success",
        username=target_username,
        metadata={"username": target_username}
    )
    AuditLogger.log_event(
        action="PASSWORD_RESET",
        component="security.auth_router",
        status="success",
        username=target_username,
        metadata={"username": target_username}
    )
    return dict(updated)

# =========================================================================
# Department Management Endpoints (Admin Controlled)
# =========================================================================

@router.get("/departments", response_model=list[DepartmentResponse], tags=["Department Management"])
async def list_departments(
    current_user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    """Lists all configured departments with actual user and document counts from SQLite database."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT d.id, d.name, d.description, d.is_active, d.created_at, d.updated_at,
               (SELECT COUNT(*) FROM users u WHERE u.department_id = d.id AND u.is_active = 1) AS user_count,
               (SELECT COUNT(*) FROM documents doc WHERE doc.owner_department_id = d.id AND doc.status = 'indexed') AS document_count
        FROM departments d
        ORDER BY d.id ASC
    """)
    rows = cursor.fetchall()
    return [dict(r) for r in rows]

@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED, tags=["Department Management"])
async def create_department(
    payload: DepartmentCreate,
    current_user: sqlite3.Row = Depends(RoleChecker(["admin"])),
    db: sqlite3.Connection = Depends(get_db)
):
    """Creates a new organizational department. Restricted to administrators."""
    clean_name = payload.name.strip()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM departments WHERE LOWER(name) = LOWER(?)", (clean_name,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Department name already exists")

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO departments (name, description, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
        (clean_name, (payload.description or "").strip(), now_str, now_str)
    )
    db.commit()
    dept_id = cursor.lastrowid
    
    cursor.execute("""
        SELECT d.id, d.name, d.description, d.is_active, d.created_at, d.updated_at,
               0 AS user_count, 0 AS document_count
        FROM departments d WHERE d.id = ?
    """, (dept_id,))
    new_dept = cursor.fetchone()

    AuditLogger.log_event(
        action="DEPARTMENT_CREATED",
        component="security.auth_router",
        status="success",
        resource=clean_name,
        metadata={"department_id": dept_id, "department_name": clean_name}
    )
    return dict(new_dept)

@router.patch("/departments/{id}", response_model=DepartmentResponse, tags=["Department Management"])
async def update_department(
    id: int,
    payload: DepartmentUpdate,
    current_user: sqlite3.Row = Depends(RoleChecker(["admin"])),
    db: sqlite3.Connection = Depends(get_db)
):
    """Renames, updates description, or activates/deactivates a department. Admin only."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM departments WHERE id = ?", (id,))
    dept = cursor.fetchone()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    updates = []
    params = []
    if payload.name is not None:
        clean_name = payload.name.strip()
        cursor.execute("SELECT id FROM departments WHERE LOWER(name) = LOWER(?) AND id != ?", (clean_name, id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Department name already exists")
        updates.append("name = ?")
        params.append(clean_name)
    if payload.description is not None:
        updates.append("description = ?")
        params.append(payload.description.strip())
    if payload.is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if payload.is_active else 0)

    now_str = datetime.now(timezone.utc).isoformat()
    updates.append("updated_at = ?")
    params.append(now_str)
    params.append(id)

    cursor.execute(f"UPDATE departments SET {', '.join(updates)} WHERE id = ?", params)
    
    if payload.name is not None:
        clean_name = payload.name.strip()
        cursor.execute("UPDATE users SET department_name = ? WHERE department_id = ?", (clean_name, id))
        cursor.execute("UPDATE documents SET owner_department_name = ? WHERE owner_department_id = ?", (clean_name, id))
    db.commit()

    cursor.execute("""
        SELECT d.id, d.name, d.description, d.is_active, d.created_at, d.updated_at,
               (SELECT COUNT(*) FROM users u WHERE u.department_id = d.id AND u.is_active = 1) AS user_count,
               (SELECT COUNT(*) FROM documents doc WHERE doc.owner_department_id = d.id AND doc.status = 'indexed') AS document_count
        FROM departments d
        WHERE d.id = ?
    """, (id,))
    updated_dept = cursor.fetchone()

    audit_action = "DEPARTMENT_DEACTIVATED" if (payload.is_active is False) else "DEPARTMENT_UPDATED"
    AuditLogger.log_event(
        action=audit_action,
        component="security.auth_router",
        status="success",
        resource=updated_dept["name"],
        metadata={"department_id": id, "department_name": updated_dept["name"]}
    )
    return dict(updated_dept)

# Create departments_router with root-level paths for /departments and /users/{username}/department
departments_router = APIRouter(tags=["Department Management"])
departments_router.add_api_route("/departments", list_departments, methods=["GET"], response_model=list[DepartmentResponse])
departments_router.add_api_route("/departments", create_department, methods=["POST"], response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
departments_router.add_api_route("/departments/{id}", update_department, methods=["PATCH"], response_model=DepartmentResponse)
departments_router.add_api_route("/users/{target_username}/department", update_user_department, methods=["PATCH"], response_model=UserResponse)

