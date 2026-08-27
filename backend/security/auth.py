import bcrypt
import jwt
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from backend.app.config.settings import settings

logger = logging.getLogger("aegis.auth")

def hash_password(password: str) -> str:
    """Hashes plain text password securely using bcrypt."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    """Verifies a plain text password against a stored bcrypt hash."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def create_access_token(subject: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token containing subject, role, issue-at, and expiration claims."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": expire
    }
    
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes a JWT access token using settings configuration. Raises PyJWT exceptions if invalid."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
