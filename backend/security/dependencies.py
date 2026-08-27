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
    
    try:
        payload = decode_access_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception
        
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
        if current_user["role"] not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for this user role",
            )
        return current_user
