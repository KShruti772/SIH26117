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
    """Initializes sqlite database schema, creates users, audit_logs, conversations, messages, and revoked_tokens tables."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'utc')),
                updated_at TEXT DEFAULT (datetime('now', 'utc'))
            )
        """)

        # Seed standard initial departments and official industrial domains
        industrial_departments = [
            ("Administration", "Executive and administrative operations"),
            ("Operations", "Plant and facility operations"),
            ("Engineering", "Design, automation, and engineering"),
            ("Maintenance", "Equipment repair and preventive maintenance"),
            ("Safety", "Industrial safety and regulatory compliance"),
            ("Finance", "Financial auditing and procurement accounting"),
            ("Procurement", "Vendor management and materials acquisition"),
            ("IT", "Information systems and local infrastructure"),
            ("Operations & Maintenance", "Plant operations, operating procedures, and equipment maintenance"),
            ("HSE", "Health, safety, environmental compliance, and hazard management"),
            ("Procurement & Commercial", "Vendor contracts, procurement, and commercial comparisons")
        ]
        for dept_name, dept_desc in industrial_departments:
            cursor.execute(
                "INSERT OR IGNORE INTO departments (name, description, is_active) VALUES (?, ?, 1)",
                (dept_name, dept_desc)
            )
        conn.commit()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                department_id INTEGER,
                department_name TEXT,
                is_active INTEGER DEFAULT 1,
                must_change_password INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'utc')),
                FOREIGN KEY(department_id) REFERENCES departments(id)
            )
        """)
        for col, col_type in [
            ("must_change_password", "INTEGER DEFAULT 0"),
            ("department_id", "INTEGER"),
            ("department_name", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        # Backfill department for any existing user missing department
        cursor.execute("""
            UPDATE users SET 
                department_id = (SELECT id FROM departments WHERE name = 'Administration'),
                department_name = 'Administration'
            WHERE (department_id IS NULL OR department_name IS NULL OR department_name = '') AND role = 'admin'
        """)
        cursor.execute("""
            UPDATE users SET 
                department_id = (SELECT id FROM departments WHERE name = 'Operations'),
                department_name = 'Operations'
            WHERE (department_id IS NULL OR department_name IS NULL OR department_name = '') AND role != 'admin'
        """)
        conn.commit()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL,
                user_id INTEGER,
                department_id INTEGER,
                permission TEXT NOT NULL DEFAULT 'READ',
                granted_by INTEGER,
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
                metadata_json TEXT,
                previous_hash TEXT,
                entry_hash TEXT
            )
        """)
        try:
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN previous_hash TEXT")
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN entry_hash TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL,
                user_id INTEGER,
                username TEXT,
                revoked_at TEXT DEFAULT (datetime('now', 'utc')),
                expires_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                username TEXT,
                title TEXT NOT NULL,
                feature TEXT DEFAULT 'chat',
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now', 'utc')),
                updated_at TEXT DEFAULT (datetime('now', 'utc')),
                last_message_at TEXT DEFAULT (datetime('now', 'utc'))
            )
        """)
        for col, col_type in [
            ("user_id", "INTEGER"),
            ("username", "TEXT"),
            ("feature", "TEXT DEFAULT 'chat'"),
            ("status", "TEXT DEFAULT 'active'"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
            ("last_message_at", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE conversations ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id INTEGER,
                username TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT DEFAULT (datetime('now', 'utc')),
                rag_used INTEGER DEFAULT 0,
                sources_json TEXT,
                model_id TEXT,
                duration_ms INTEGER,
                request_id TEXT,
                verification TEXT,
                error_detail TEXT,
                feature TEXT DEFAULT 'chat',
                metadata_json TEXT,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        for col, col_type in [
            ("user_id", "INTEGER"),
            ("username", "TEXT"),
            ("rag_used", "INTEGER DEFAULT 0"),
            ("sources_json", "TEXT"),
            ("model_id", "TEXT"),
            ("duration_ms", "INTEGER"),
            ("request_id", "TEXT"),
            ("verification", "TEXT"),
            ("error_detail", "TEXT"),
            ("feature", "TEXT DEFAULT 'chat'"),
            ("metadata_json", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE messages ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                source_path TEXT NOT NULL,
                content_hash TEXT UNIQUE NOT NULL,
                file_size INTEGER DEFAULT 0,
                mime_type TEXT DEFAULT 'application/octet-stream',
                document_type TEXT DEFAULT 'document',
                category TEXT DEFAULT 'document',
                extraction_method TEXT DEFAULT 'native',
                metadata_json TEXT DEFAULT '{}',
                chunk_count INTEGER DEFAULT 0,
                owner_id INTEGER DEFAULT -1,
                owner_username TEXT DEFAULT '',
                status TEXT DEFAULT 'indexed',
                created_at TEXT DEFAULT (datetime('now', 'utc')),
                updated_at TEXT DEFAULT (datetime('now', 'utc'))
            )
        """)
        for col, col_type in [
            ("file_size", "INTEGER DEFAULT 0"),
            ("mime_type", "TEXT DEFAULT 'application/octet-stream'"),
            ("document_type", "TEXT DEFAULT 'document'"),
            ("category", "TEXT DEFAULT 'document'"),
            ("extraction_method", "TEXT DEFAULT 'native'"),
            ("metadata_json", "TEXT DEFAULT '{}'"),
            ("chunk_count", "INTEGER DEFAULT 0"),
            ("owner_id", "INTEGER DEFAULT -1"),
            ("owner_username", "TEXT DEFAULT ''"),
            ("owner_department_id", "INTEGER"),
            ("owner_department_name", "TEXT DEFAULT ''"),
            ("visibility", "TEXT DEFAULT 'PRIVATE'"),
            ("status", "TEXT DEFAULT 'indexed'"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE documents ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        # Backfill document department and visibility for existing documents
        cursor.execute("""
            UPDATE documents SET visibility = 'PRIVATE' WHERE visibility IS NULL OR visibility = ''
        """)
        cursor.execute("""
            UPDATE documents SET 
                owner_department_id = (SELECT department_id FROM users WHERE users.id = documents.owner_id),
                owner_department_name = (SELECT department_name FROM users WHERE users.id = documents.owner_id)
            WHERE (owner_department_id IS NULL OR owner_department_name IS NULL OR owner_department_name = '') AND owner_id > 0
        """)
        conn.commit()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generated_documents (
                id TEXT PRIMARY KEY,
                owner_id INTEGER DEFAULT -1,
                owner_username TEXT DEFAULT '',
                owner_department_id INTEGER,
                owner_department_name TEXT DEFAULT '',
                visibility TEXT DEFAULT 'PRIVATE',
                filename TEXT NOT NULL,
                title TEXT NOT NULL,
                format TEXT DEFAULT 'pdf',
                file_size INTEGER DEFAULT 0,
                mime_type TEXT DEFAULT 'application/pdf',
                source_document_ids TEXT DEFAULT '',
                conversation_id TEXT DEFAULT '',
                status TEXT DEFAULT 'completed',
                file_path TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'utc')),
                updated_at TEXT DEFAULT (datetime('now', 'utc'))
            )
        """)
        for col, col_type in [
            ("owner_id", "INTEGER DEFAULT -1"),
            ("owner_username", "TEXT DEFAULT ''"),
            ("owner_department_id", "INTEGER"),
            ("owner_department_name", "TEXT DEFAULT ''"),
            ("visibility", "TEXT DEFAULT 'PRIVATE'"),
            ("filename", "TEXT"),
            ("title", "TEXT"),
            ("format", "TEXT DEFAULT 'pdf'"),
            ("file_size", "INTEGER DEFAULT 0"),
            ("mime_type", "TEXT DEFAULT 'application/pdf'"),
            ("source_document_ids", "TEXT DEFAULT ''"),
            ("conversation_id", "TEXT DEFAULT ''"),
            ("status", "TEXT DEFAULT 'completed'"),
            ("file_path", "TEXT"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE generated_documents ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        # Backfill owner_id and owner_department for generated_documents linked to conversations
        try:
            cursor.execute("""
                UPDATE generated_documents SET 
                    owner_id = (SELECT user_id FROM conversations WHERE conversations.id = generated_documents.conversation_id),
                    owner_username = (SELECT username FROM conversations WHERE conversations.id = generated_documents.conversation_id),
                    owner_department_id = (SELECT users.department_id FROM users JOIN conversations ON users.id = conversations.user_id WHERE conversations.id = generated_documents.conversation_id),
                    owner_department_name = (SELECT users.department_name FROM users JOIN conversations ON users.id = conversations.user_id WHERE conversations.id = generated_documents.conversation_id)
                WHERE conversation_id IS NOT NULL AND conversation_id != '' 
                  AND EXISTS (SELECT 1 FROM conversations WHERE conversations.id = generated_documents.conversation_id AND conversations.user_id IS NOT NULL)
            """)
            conn.commit()
        except Exception:
            pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sandbox_artifacts (
                id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                user_id INTEGER DEFAULT -1,
                username TEXT DEFAULT '',
                conversation_id TEXT DEFAULT '',
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                mime_type TEXT DEFAULT 'application/octet-stream',
                content_hash TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'utc'))
            )
        """)
        for col, col_type in [
            ("execution_id", "TEXT NOT NULL"),
            ("user_id", "INTEGER DEFAULT -1"),
            ("username", "TEXT DEFAULT ''"),
            ("conversation_id", "TEXT DEFAULT ''"),
            ("filename", "TEXT NOT NULL"),
            ("file_path", "TEXT NOT NULL"),
            ("file_size", "INTEGER DEFAULT 0"),
            ("mime_type", "TEXT DEFAULT 'application/octet-stream'"),
            ("content_hash", "TEXT DEFAULT ''"),
            ("created_at", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE sandbox_artifacts ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sandbox_executions (
                id TEXT PRIMARY KEY,
                user_id INTEGER DEFAULT -1,
                username TEXT DEFAULT '',
                conversation_id TEXT DEFAULT '',
                language TEXT DEFAULT 'python',
                code TEXT NOT NULL,
                code_hash TEXT DEFAULT '',
                filename TEXT DEFAULT 'script.py',
                exit_code INTEGER DEFAULT -1,
                stdout TEXT DEFAULT '',
                stderr TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                timed_out INTEGER DEFAULT 0,
                artifacts_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now', 'utc'))
            )
        """)
        for col, col_type in [
            ("user_id", "INTEGER DEFAULT -1"),
            ("username", "TEXT DEFAULT ''"),
            ("conversation_id", "TEXT DEFAULT ''"),
            ("language", "TEXT DEFAULT 'python'"),
            ("code", "TEXT NOT NULL"),
            ("code_hash", "TEXT DEFAULT ''"),
            ("filename", "TEXT DEFAULT 'script.py'"),
            ("exit_code", "INTEGER DEFAULT -1"),
            ("stdout", "TEXT DEFAULT ''"),
            ("stderr", "TEXT DEFAULT ''"),
            ("duration_ms", "INTEGER DEFAULT 0"),
            ("status", "TEXT NOT NULL"),
            ("timed_out", "INTEGER DEFAULT 0"),
            ("artifacts_json", "TEXT DEFAULT '[]'"),
            ("created_at", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE sandbox_executions ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_requests (
                id TEXT PRIMARY KEY,
                plan_id TEXT,
                conversation_id TEXT,
                step_id TEXT,
                requester_id INTEGER,
                requester_username TEXT NOT NULL DEFAULT '',
                reviewer_id INTEGER,
                reviewer_username TEXT,
                reviewer_role TEXT,
                department_id INTEGER,
                department_name TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING',
                action_type TEXT NOT NULL DEFAULT 'DOCUMENT_APPROVAL',
                proposed_payload_json TEXT NOT NULL DEFAULT '{}',
                modified_payload_json TEXT,
                rejection_reason TEXT,
                created_at TEXT DEFAULT (datetime('now', 'utc')),
                reviewed_at TEXT,
                expires_at TEXT,
                FOREIGN KEY(department_id) REFERENCES departments(id),
                FOREIGN KEY(requester_id) REFERENCES users(id),
                FOREIGN KEY(reviewer_id) REFERENCES users(id)
            )
        """)
        for col, col_type in [
            ("plan_id", "TEXT"),
            ("conversation_id", "TEXT"),
            ("step_id", "TEXT"),
            ("requester_id", "INTEGER"),
            ("requester_username", "TEXT NOT NULL DEFAULT ''"),
            ("reviewer_id", "INTEGER"),
            ("reviewer_username", "TEXT"),
            ("reviewer_role", "TEXT"),
            ("department_id", "INTEGER"),
            ("department_name", "TEXT DEFAULT ''"),
            ("status", "TEXT NOT NULL DEFAULT 'PENDING'"),
            ("action_type", "TEXT NOT NULL DEFAULT 'DOCUMENT_APPROVAL'"),
            ("proposed_payload_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("modified_payload_json", "TEXT"),
            ("rejection_reason", "TEXT"),
            ("created_at", "TEXT"),
            ("reviewed_at", "TEXT"),
            ("expires_at", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE approval_requests ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        # Dedicated indexes for approval queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_requests(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_requester ON approval_requests(requester_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_reviewer ON approval_requests(reviewer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_department ON approval_requests(department_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_conversation ON approval_requests(conversation_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_plan ON approval_requests(plan_id)")

        conn.commit()
    finally:
        conn.close()

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a local database session connection with WAL mode and busy timeout."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
