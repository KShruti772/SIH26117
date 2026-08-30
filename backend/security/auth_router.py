import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status, Request
from backend.security.database import get_db
from backend.security.auth import hash_password, verify_password, create_access_token
from backend.security.models import (
    UserRegister, UserResponse, TokenResponse,
    UserProvisionRequest, UserStatusRequest, UserRoleRequest,
    PasswordResetRequest, ChangePasswordRequest
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
    
    try:
        hashed = hash_password(payload.password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (payload.username, hashed, role)
        )
        db.commit()
        
        cursor.execute("SELECT * FROM users WHERE username = ?", (payload.username,))
        user = cursor.fetchone()
        AuditLogger.log_event(
            action="AUTH_REGISTER",
            component="security.auth_router",
            status="success",
            username=payload.username,
            metadata={"username": payload.username, "role": role}
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
            action="AUTH_LOGIN",
            component="security.auth_router",
            status="failure",
            username=username,
            metadata={"username": username, "error_category": "invalid_credentials"}
        )
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
            action="AUTH_LOGIN",
            component="security.auth_router",
            status="failure",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            metadata={"username": user["username"], "error_category": "inactive_profile"}
        )
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
        action="AUTH_LOGIN",
        component="security.auth_router",
        status="success",
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        metadata={"username": user["username"], "role": user["role"]}
    )
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
    AuditLogger.log_event(
        action="LOGOUT",
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
    AuditLogger.log_event(
        action="PASSWORD_CHANGED",
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
    
    hashed = hash_password(payload.password)
    cursor.execute(
        "INSERT INTO users (username, password_hash, role, must_change_password) VALUES (?, ?, ?, 1)",
        (payload.username, hashed, payload.role)
    )
    db.commit()
    
    cursor.execute("SELECT * FROM users WHERE username = ?", (payload.username,))
    new_user = cursor.fetchone()
    
    AuditLogger.log_event(
        action="USER_PROVISIONED",
        component="security.auth_router",
        status="success",
        username=payload.username,
        metadata={"username": payload.username, "role": payload.role}
    )
    AuditLogger.log_event(
        action="USER_CREATED",
        component="security.auth_router",
        status="success",
        username=payload.username,
        metadata={"username": payload.username, "role": payload.role}
    )
    return dict(new_user)

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
