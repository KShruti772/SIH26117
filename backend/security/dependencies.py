import sqlite3
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import List
from backend.security.database import get_db
from backend.security.auth import decode_access_token

# OAuth2 Bearer scheme targeting our auth login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user(
    db: sqlite3.Connection = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> sqlite3.Row:
    """Authenticates Bearer token, validates JWT claims, and fetches current user details."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    from backend.security.auth import decode_access_token, is_token_revoked
    
    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature has expired or is invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature has expired or is invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature has expired or is invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    
    if user is None:
        raise credentials_exception
        
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user profile",
        )
        
    from backend.security.audit import set_current_audit_user
    set_current_audit_user(user)
        
    return user

class RoleChecker:
    """Simple RBAC checker ensuring the authenticated user matches permitted access roles."""
    
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
        user_role = current_user["role"] if isinstance(current_user, sqlite3.Row) or isinstance(current_user, dict) else getattr(current_user, "role", "user")
        if user_role not in self.allowed_roles:
            from backend.security.audit import AuditLogger
            user_id = current_user["id"] if isinstance(current_user, sqlite3.Row) or isinstance(current_user, dict) else getattr(current_user, "id", None)
            username = current_user["username"] if isinstance(current_user, sqlite3.Row) or isinstance(current_user, dict) else getattr(current_user, "username", "unknown")
            
            AuditLogger.log_event(
                action="AUTHORIZATION_DENIED",
                component="security.dependencies",
                status="failure",
                user_id=user_id,
                username=username,
                role=user_role,
                metadata={
                    "resource_type": "api_endpoint",
                    "action": "access",
                    "result": "denied",
                    "reason": "ROLE_FORBIDDEN",
                    "allowed_roles": self.allowed_roles,
                    "attempted_role": user_role
                }
            )
            AuditLogger.log_event(
                action="AUTHORIZATION_FAILURE",
                component="security.dependencies",
                status="failure",
                user_id=user_id,
                username=username,
                role=user_role,
                metadata={
                    "resource_type": "api_endpoint",
                    "action": "access",
                    "result": "denied",
                    "reason": "ROLE_FORBIDDEN"
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for this user role",
            )
        return current_user

# Reusable authorization policy aliases
RequireAuthenticated = Depends(get_current_user)
RequireAdmin = Depends(RoleChecker(["admin"]))
