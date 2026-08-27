import os
import sqlite3
from typing import Generator
from backend.app.config.settings import settings

def get_db_path() -> str:
    """Resolves absolute path to local auth database and ensures parent folders exist."""
    db_path = os.path.abspath(settings.AUTH_DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path

def init_db() -> None:
    """Initializes sqlite database schema and creates users table if missing."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'utc'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now', 'utc')),
                user_id INTEGER,
                username TEXT,
                role TEXT,
                action TEXT NOT NULL,
                component TEXT NOT NULL,
                resource TEXT,
                status TEXT NOT NULL,
                request_id TEXT,
                duration_ms INTEGER,
                metadata_json TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a local database session connection."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
