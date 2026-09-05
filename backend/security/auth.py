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
    """Verifies a plain text password against a stored bcrypt hash safely without leaking credentials."""
    if not password or not hashed:
        return False
    try:
        password_bytes = password.encode("utf-8") if isinstance(password, str) else password
        hashed_bytes = hashed.encode("utf-8") if isinstance(hashed, str) else hashed
        
        if not isinstance(hashed_bytes, (bytes, bytearray)):
            logger.warning("Password verification failed: malformed stored password hash")
            return False
            
        # Standard bcrypt hashes must be 59-60 chars and start with valid $2 prefix
        if len(hashed_bytes) < 59 or len(hashed_bytes) > 60:
            logger.warning("Password verification failed: malformed stored password hash")
            return False
            
        if not hashed_bytes.startswith((b"$2a$", b"$2b$", b"$2y$", b"$2x$")):
            logger.warning("Password verification failed: malformed stored password hash")
            return False

        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except BaseException:
        logger.warning("Password verification failed: malformed stored password hash")
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

def compute_token_hash(token: str) -> str:
    """Computes SHA-256 hash of a JWT token for revocation index mapping."""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def revoke_token(token: str, user_id: Optional[int] = None, username: Optional[str] = None) -> None:
    """Inserts a token hash into SQLite revoked_tokens table to invalidate it prior to natural expiration."""
    import sqlite3
    from backend.security.database import get_db_path
    token_hash = compute_token_hash(token)
    
    expires_at_str = None
    try:
        payload = decode_access_token(token)
        exp_ts = payload.get("exp")
        if exp_ts:
            expires_at_str = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()
    except Exception:
        pass
        
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO revoked_tokens (token_hash, user_id, username, expires_at)
            VALUES (?, ?, ?, ?)
        """, (token_hash, user_id, username, expires_at_str))
        conn.commit()
    finally:
        conn.close()

def is_token_revoked(token: str) -> bool:
    """Checks whether a token hash exists in the revoked_tokens blacklist."""
    import sqlite3
    from backend.security.database import get_db_path
    token_hash = compute_token_hash(token)
    
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM revoked_tokens WHERE token_hash = ?", (token_hash,))
        return cursor.fetchone() is not None
    finally:
        conn.close()
