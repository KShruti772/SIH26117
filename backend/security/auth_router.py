import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status, Request
from backend.security.database import get_db
from backend.security.auth import hash_password, verify_password, create_access_token
from backend.security.models import UserRegister, UserResponse, TokenResponse
from backend.security.dependencies import get_current_user
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
        
    # MVP Role mapping helper: username containing 'admin' gets admin privileges
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
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": dict(user)
    }

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: sqlite3.Row = Depends(get_current_user)):
    """Returns safe user profile details for the currently authenticated bearer token."""
    return dict(current_user)
