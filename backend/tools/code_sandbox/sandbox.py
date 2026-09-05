import os
import sys
import re
import uuid
import time
import shutil
import sqlite3
import subprocess
import logging
import hashlib
import mimetypes
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union

from backend.security.database import get_db_path
from backend.security.audit import AuditLogger

logger = logging.getLogger("aegis.sandbox")

class SandboxError(Exception):
    """Base exception for code sandbox execution errors."""
    pass

class BaseSandbox:
    """Interface class to allow future swap of execution sandbox backends (e.g., to Docker/microVMs)."""
    
    def execute(
        self,
        code: str,
        timeout_seconds: float = 10.0,
        files: Optional[Dict[str, Union[bytes, str]]] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes untrusted code and returns a structured status dictionary."""
        raise NotImplementedError

    def execute_code(
        self,
        code: str,
        language: str = "python",
        files: Optional[Dict[str, Union[bytes, str]]] = None,
        timeout_seconds: float = 10.0,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Tool interface contract for agentic code execution."""
        return self.execute(
            code=code,
            timeout_seconds=timeout_seconds,
            files=files,
            user_id=user_id,
            username=username,
            conversation_id=conversation_id
        )

class SubprocessSandbox(BaseSandbox):
    """
    Subprocess-based sandbox executing Python code in an isolated child process.
    Provides strict AST pre-execution inspection, restricted scrubbed environment,
    controlled input file mounting, output artifact collection, timeout guards, and audit trails.
    """
    
    def __init__(
        self,
        workspace_parent: str = "sandbox_runs",
        artifacts_storage: str = "data/sandbox",
        output_limit_bytes: int = 65536
    ):
        self.workspace_parent = os.path.abspath(workspace_parent)
        self.artifacts_storage = os.path.abspath(artifacts_storage)
        self.output_limit_bytes = output_limit_bytes
        os.makedirs(self.workspace_parent, exist_ok=True)
        os.makedirs(self.artifacts_storage, exist_ok=True)

    @staticmethod
    def _validate_safe_filename(filename: str) -> str:
        """Validates and cleans filename to strictly block path traversal attempts."""
        if not filename or not isinstance(filename, str):
            raise ValueError("Invalid filename: filename must be a non-empty string (path traversal blocked).")
        clean = filename.strip()
        if ".." in clean or "/" in clean or "\\" in clean or "\x00" in clean:
            raise ValueError(f"Security Rejection: Path traversal attempt detected in filename '{filename}' (path traversal blocked).")
        base = os.path.basename(clean)
        if not base or base != clean or base.startswith("."):
            raise ValueError(f"Security Rejection: Invalid file basename '{filename}' (path traversal blocked).")
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", base):
            raise ValueError(f"Security Rejection: Filename contains forbidden characters: '{base}' (path traversal blocked).")
        return base

    @staticmethod
    def _validate_ast_safety(code: str) -> Optional[str]:
        """Statically inspects Python code AST for forbidden module imports."""
        import ast
        forbidden_modules = {
            "ctypes", "winreg", "subprocess", "socket", "importlib", "shutil",
            "requests", "urllib", "http", "httpx", "aiohttp", "ftplib", "telnetlib"
        }
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name.split(".")[0]
                        if mod in forbidden_modules:
                            return f"Forbidden module import detected: '{alias.name}'"
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        mod = node.module.split(".")[0]
                        if mod in forbidden_modules:
                            return f"Forbidden module import detected: '{node.module}'"
        except SyntaxError as e:
            return f"SyntaxError in code string: {e}"
        return None

    def execute(
        self,
        code: str,
        timeout_seconds: float = 10.0,
        files: Optional[Dict[str, Union[bytes, str]]] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        conversation_id: Optional[str] = None,
        script_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes Python code in a separate process, managing execution limits, input files, artifacts, and cleanup."""
        import json
        run_id = f"run_{uuid.uuid4()}"
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest() if isinstance(code, str) else None
        
        # Validate and resolve target script filename
        try:
            if script_filename and isinstance(script_filename, str) and script_filename.strip():
                clean_sname = self._validate_safe_filename(script_filename.strip())
                target_script_name = clean_sname if clean_sname.endswith(".py") else f"{clean_sname}.py"
            else:
                target_script_name = "script.py"
        except ValueError as ve:
            return {
                "execution_id": None,
                "success": False,
                "status": "FAILED",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(ve),
                "timed_out": False,
                "duration_ms": 0,
                "execution_time_ms": 0,
                "code_hash": code_hash,
                "language": "python",
                "code": code if isinstance(code, str) else "",
                "filename": script_filename or "script.py",
                "artifacts": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(ve)
            }

        def rejected_result(error: str) -> Dict[str, Any]:
            AuditLogger.log_event(
                action="SANDBOX_EXECUTION_FAILED",
                component="sandbox.subprocess",
                status="failure",
                user_id=user_id,
                username=username,
                metadata={
                    "run_id": run_id,
                    "execution_id": run_id,
                    "error": error,
                    "result": "rejected",
                    "status": "failure",
                    "code_hash": code_hash,
                    "language": "python",
                    "conversation_id": conversation_id
                }
            )
            AuditLogger.log_event(
                action="SANDBOX_EXECUTION",
                component="sandbox.subprocess",
                status="failure",
                user_id=user_id,
                username=username,
                metadata={
                    "run_id": run_id,
                    "execution_id": run_id,
                    "error": error,
                    "result": "rejected",
                    "status": "failure",
                    "code_hash": code_hash,
                    "language": "python",
                    "conversation_id": conversation_id
                }
            )
            return {
                "execution_id": None,
                "success": False,
                "status": "FAILED",
                "exit_code": -1,
                "stdout": "",
                "stderr": error,
                "timed_out": False,
                "duration_ms": 0,
                "execution_time_ms": 0,
                "code_hash": code_hash,
                "language": "python",
                "code": code if isinstance(code, str) else "",
                "filename": target_script_name,
                "artifacts": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": error
            }

        # 1. Input validation
        if not isinstance(code, str) or not code.strip():
            return rejected_result("Rejected: Empty or invalid code string.")
            
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0 or timeout_seconds > 60:
            return rejected_result("Rejected: Timeout must be a positive float between 0.1 and 60.0 seconds.")

        # AST Pre-Execution Security Inspection
        ast_violation = self._validate_ast_safety(code)
        if ast_violation:
            return rejected_result(f"Security Rejection: {ast_violation}")

        # 2. Setup isolated temporary workspace
        run_dir = os.path.join(self.workspace_parent, run_id)
        os.makedirs(run_dir, exist_ok=True)

        # 3. Setup isolated persistent user storage workspace
        user_storage_dir = os.path.join(
            self.artifacts_storage,
            str(user_id) if user_id is not None and user_id != -1 else "global"
        )
        os.makedirs(user_storage_dir, exist_ok=True)
        
        # Persist the script into the user's isolated workspace
        perm_script_path = os.path.join(user_storage_dir, target_script_name)
        with open(perm_script_path, "wb") as pfh:
            pfh.write(code.encode("utf-8"))
        
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION_STARTED",
            component="sandbox.subprocess",
            status="success",
            user_id=user_id,
            username=username,
            resource=run_id,
            metadata={
                "run_id": run_id,
                "execution_id": run_id,
                "filename": target_script_name,
                "conversation_id": conversation_id,
                "language": "python",
                "status": "started"
            }
        )

        # 4. Mount input files safely
        mounted_input_names = set()
        if files and isinstance(files, dict):
            for fname, fcontent in files.items():
                try:
                    clean_in_fname = self._validate_safe_filename(fname)
                except ValueError as ve:
                    shutil.rmtree(run_dir, ignore_errors=True)
                    return rejected_result(str(ve))
                
                target_file_path = os.path.join(run_dir, clean_in_fname)
                try:
                    if isinstance(fcontent, bytes):
                        with open(target_file_path, "wb") as fh:
                            fh.write(fcontent)
                    elif isinstance(fcontent, str):
                        with open(target_file_path, "w", encoding="utf-8") as fh:
                            fh.write(fcontent)
                    mounted_input_names.add(clean_in_fname)
                except Exception as fe:
                    shutil.rmtree(run_dir, ignore_errors=True)
                    return rejected_result(f"Input file mounting failed for '{fname}': {fe}")

        socket_block_prefix = (
            "import socket\n"
            "class _BlockedSocket(socket.socket):\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        raise PermissionError('Sandbox Security Violation: Network access is disabled by AEGIS air-gap policy.')\n"
            "    def connect(self, *args, **kwargs):\n"
            "        raise PermissionError('Sandbox Security Violation: Network access is disabled by AEGIS air-gap policy.')\n"
            "socket.socket = _BlockedSocket\n"
            "socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError('Sandbox Security Violation: Network access is disabled by AEGIS air-gap policy.'))\n\n"
        )
        script_path = os.path.join(run_dir, target_script_name)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(socket_block_prefix + code)

        # 4. Environment restriction (strip all host secrets, DB URLs, credentials)
        safe_env = {}
        for key in ["SYSTEMROOT", "SYSTEMDRIVE", "PATH", "PATHEXT", "TEMP", "TMP", "TMPDIR", "HOME", "USER", "LANG", "LC_ALL", "PYTHONPATH"]:
            if key in os.environ:
                safe_env[key] = os.environ[key]
        
        logger.info(f"Launching subprocess sandbox execution ID {run_id} ({target_script_name})")
        start_time = time.perf_counter()
        
        timed_out = False
        exit_code = -1
        stdout = ""
        stderr = ""
        error_msg = None
        
        # 5. Spawning Python subprocess
        try:
            python_executable = sys.executable
            proc = subprocess.Popen(
                [python_executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=run_dir,
                env=safe_env,
                text=True
            )
            
            try:
                stdout, stderr = proc.communicate(timeout=timeout_seconds)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.terminate()
                try:
                    stdout, stderr = proc.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                exit_code = -1
                error_msg = f"Execution timed out. Exceeded cap of {timeout_seconds} seconds."

        except Exception as e:
            exit_code = -1
            error_msg = f"Sandbox launch initialization failed: {e}"
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # 6. Output limit checks
        if len(stdout) > self.output_limit_bytes:
            stdout = stdout[:self.output_limit_bytes] + "\n... [TRUNCATED: Output limit exceeded]"
            error_msg = error_msg or "Output limit exceeded."
            exit_code = -1
            
        if len(stderr) > self.output_limit_bytes:
            stderr = stderr[:self.output_limit_bytes] + "\n... [TRUNCATED: Output limit exceeded]"
            error_msg = error_msg or "Output limit exceeded."
            exit_code = -1

        # 7. Collect generated artifact files & persist script
        artifacts: List[Dict[str, Any]] = []
        try:
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()

            # Always persist and record the executed script file in sandbox_artifacts
            clean_script_bytes = code.encode("utf-8")
            art_id = f"art_{uuid.uuid4().hex[:12]}"
            
            # Check if artifact record already exists for this user and filename
            cursor.execute("""
                SELECT id FROM sandbox_artifacts WHERE user_id = ? AND filename = ?
            """, (user_id if user_id is not None else -1, target_script_name))
            existing_row = cursor.fetchone()
            if existing_row:
                art_id = existing_row[0]
                cursor.execute("""
                    UPDATE sandbox_artifacts
                    SET execution_id = ?, conversation_id = ?, file_path = ?, file_size = ?, content_hash = ?, created_at = ?
                    WHERE id = ?
                """, (
                    run_id, conversation_id or "", perm_script_path, len(clean_script_bytes), code_hash, now_iso, art_id
                ))
            else:
                cursor.execute("""
                    INSERT INTO sandbox_artifacts (
                        id, execution_id, user_id, username, conversation_id,
                        filename, file_path, file_size, mime_type, content_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    art_id, run_id, user_id if user_id is not None else -1, username or "", conversation_id or "",
                    target_script_name, perm_script_path, len(clean_script_bytes), "text/x-python", code_hash, now_iso
                ))
            
            if target_script_name != "script.py":
                artifacts.append({
                    "id": art_id,
                    "filename": target_script_name,
                    "file_path": perm_script_path,
                    "file_size": len(clean_script_bytes),
                    "mime_type": "text/x-python",
                    "content_hash": code_hash,
                    "sha256_hash": code_hash,
                    "download_url": f"/sandbox/artifacts/{art_id}/download",
                    "created_at": now_iso
                })

            # Check for any other files generated in run_dir during execution
            for item in os.listdir(run_dir):
                if item == target_script_name or item == "script.py" or item in mounted_input_names:
                    continue
                
                item_path = os.path.join(run_dir, item)
                if os.path.isfile(item_path):
                    with open(item_path, "rb") as afh:
                        art_bytes = afh.read()
                    
                    art_size = len(art_bytes)
                    art_hash = hashlib.sha256(art_bytes).hexdigest()
                    extra_art_id = f"art_{uuid.uuid4().hex[:12]}"
                    mime, _ = mimetypes.guess_type(item)
                    mime_type = mime or "application/octet-stream"

                    # Persist file into user's isolated sandbox storage
                    user_extra_path = os.path.join(user_storage_dir, item)
                    with open(user_extra_path, "wb") as pfh:
                        pfh.write(art_bytes)

                    # Record in SQLite sandbox_artifacts table
                    cursor.execute("""
                        INSERT INTO sandbox_artifacts (
                            id, execution_id, user_id, username, conversation_id,
                            filename, file_path, file_size, mime_type, content_hash, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        extra_art_id, run_id, user_id if user_id is not None else -1, username or "", conversation_id or "",
                        item, user_extra_path, art_size, mime_type, art_hash, now_iso
                    ))

                    artifacts.append({
                        "id": extra_art_id,
                        "filename": item,
                        "file_path": user_extra_path,
                        "file_size": art_size,
                        "mime_type": mime_type,
                        "content_hash": art_hash,
                        "sha256_hash": art_hash,
                        "download_url": f"/sandbox/artifacts/{extra_art_id}/download",
                        "created_at": now_iso
                    })
            
            # Persist execution record in sandbox_executions table
            success = (exit_code == 0) and not timed_out and (error_msg is None)
            cursor.execute("""
                INSERT INTO sandbox_executions (
                    id, user_id, username, conversation_id, language, code, code_hash,
                    filename, exit_code, stdout, stderr, duration_ms, status, timed_out,
                    artifacts_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, user_id if user_id is not None else -1, username or "", conversation_id or "",
                "python", code, code_hash or "", target_script_name, exit_code,
                stdout or "", stderr or (error_msg or ""), duration_ms,
                "SUCCESS" if success else "FAILED", 1 if timed_out else 0,
                json.dumps([a["filename"] for a in artifacts]), now_iso
            ))

            conn.commit()
            conn.close()
        except Exception as arte:
            logger.warning(f"Error persisting sandbox execution / artifacts for run {run_id}: {arte}")

        # 8. Graceful temporary workspace cleanup
        try:
            shutil.rmtree(run_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temporary sandbox directory '{run_dir}': {e}")

        success = (exit_code == 0) and not timed_out and (error_msg is None)
        logger.info(f"Sandbox run ID {run_id} completed in {duration_ms}ms with success={success}, artifacts={len(artifacts)}")
        
        # 9. Audit sandbox execution
        audit_action = "SANDBOX_EXECUTION_COMPLETED" if success else "SANDBOX_EXECUTION_FAILED"
        result_str = "success" if success else "failed"
        AuditLogger.log_event(
            action=audit_action,
            component="sandbox.subprocess",
            status="success" if success else "failure",
            resource=run_id,
            duration_ms=duration_ms,
            user_id=user_id,
            username=username,
            metadata={
                "run_id": run_id,
                "execution_id": run_id,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "result": result_str,
                "status": "success" if success else "failure",
                "artifact_count": len(artifacts),
                "artifacts_count": len(artifacts),
                "artifacts": [a["filename"] for a in artifacts],
                "language": "python",
                "code_hash": code_hash,
                "conversation_id": conversation_id
            }
        )
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="sandbox.subprocess",
            status="success" if success else "failure",
            resource=run_id,
            duration_ms=duration_ms,
            user_id=user_id,
            username=username,
            metadata={
                "run_id": run_id,
                "execution_id": run_id,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "result": result_str,
                "status": "success" if success else "failure",
                "artifact_count": len(artifacts),
                "artifacts_count": len(artifacts),
                "artifacts": [a["filename"] for a in artifacts],
                "language": "python",
                "code_hash": code_hash,
                "conversation_id": conversation_id
            }
        )

        return {
            "execution_id": run_id,
            "success": success,
            "status": "SUCCESS" if success else "FAILED",
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "execution_time_ms": duration_ms,
            "code_hash": code_hash,
            "language": "python",
            "code": code if isinstance(code, str) else "",
            "filename": target_script_name,
            "artifacts": artifacts,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error_msg or (stderr if not success and stderr else None)
        }

    def create_file(
        self,
        filename: str,
        content: Union[str, bytes],
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates and persists a verified code or data file artifact in the user's isolated workspace."""
        clean_name = self._validate_safe_filename(filename)

        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        file_size = len(raw_bytes)
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        lines_count = len(content.splitlines()) if isinstance(content, str) else 0
        art_id = f"art_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        mime, _ = mimetypes.guess_type(clean_name)
        mime_type = mime or ("text/x-python" if clean_name.endswith(".py") else "text/plain")

        user_storage_dir = os.path.join(
            self.artifacts_storage,
            str(user_id) if user_id is not None and user_id != -1 else "global"
        )
        os.makedirs(user_storage_dir, exist_ok=True)
        perm_path = os.path.join(user_storage_dir, clean_name)
        with open(perm_path, "wb") as pfh:
            pfh.write(raw_bytes)

        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM sandbox_artifacts WHERE user_id = ? AND filename = ?
            """, (user_id if user_id is not None else -1, clean_name))
            existing_row = cursor.fetchone()
            if existing_row:
                art_id = existing_row[0]
                cursor.execute("""
                    UPDATE sandbox_artifacts
                    SET file_path = ?, file_size = ?, mime_type = ?, content_hash = ?, created_at = ?
                    WHERE id = ?
                """, (
                    perm_path, file_size, mime_type, content_hash, now_iso, art_id
                ))
            else:
                cursor.execute("""
                    INSERT INTO sandbox_artifacts (
                        id, execution_id, user_id, username, conversation_id,
                        filename, file_path, file_size, mime_type, content_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    art_id, f"create_{uuid.uuid4().hex[:8]}", user_id if user_id is not None else -1, username or "", conversation_id or "",
                    clean_name, perm_path, file_size, mime_type, content_hash, now_iso
                ))
            conn.commit()
        finally:
            conn.close()

        AuditLogger.log_event(
            action="SANDBOX_FILE_CREATED",
            component="sandbox.subprocess",
            status="success",
            user_id=user_id,
            username=username,
            resource=clean_name,
            metadata={
                "filename": clean_name,
                "file_size": file_size,
                "lines_count": lines_count,
                "artifact_id": art_id,
                "conversation_id": conversation_id
            }
        )

        return {
            "id": art_id,
            "filename": clean_name,
            "file_size": file_size,
            "lines_count": lines_count,
            "mime_type": mime_type,
            "content_hash": content_hash,
            "sha256_hash": content_hash,
            "download_url": f"/sandbox/artifacts/{art_id}/download",
            "file_path": perm_path,
            "created_at": now_iso,
            "conversation_id": conversation_id
        }

    def list_files(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[int] = None,
        is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """Retrieves list of real persisted sandbox artifact files with strict RBAC user isolation."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            query = "SELECT id, execution_id, user_id, username, conversation_id, filename, file_path, file_size, mime_type, content_hash, created_at FROM sandbox_artifacts WHERE 1=1"
            params: List[Any] = []
            if not is_admin:
                if user_id is not None:
                    query += " AND user_id = ?"
                    params.append(user_id)
                else:
                    return []
            if conversation_id:
                query += " AND conversation_id = ?"
                params.append(conversation_id)
            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                item["download_url"] = f"/sandbox/artifacts/{item['id']}/download"
                item["sha256_hash"] = item.get("content_hash")
                fpath = item.get("file_path")
                if fpath and os.path.exists(fpath):
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                            item["lines_count"] = len(fh.readlines())
                    except Exception:
                        item["lines_count"] = 0
                else:
                    item["lines_count"] = 0
                result.append(item)
            return result
        finally:
            conn.close()

    def get_file(
        self,
        file_id: str,
        user_id: Optional[int] = None,
        is_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Retrieves file details and readable text content for a sandbox artifact with strict RBAC validation."""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sandbox_artifacts WHERE id = ?", (file_id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            if not is_admin and (user_id is None or item["user_id"] != user_id):
                return None
            
            content_str = None
            if item.get("file_path") and os.path.exists(item["file_path"]):
                try:
                    with open(item["file_path"], "r", encoding="utf-8", errors="replace") as fh:
                        content_str = fh.read()
                except Exception:
                    pass
            item["content"] = content_str
            item["download_url"] = f"/sandbox/artifacts/{item['id']}/download"
            item["sha256_hash"] = item.get("content_hash")
            item["lines_count"] = len(content_str.splitlines()) if content_str else 0
            return item
        finally:
            conn.close()

    def list_executions(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[int] = None,
        is_admin: bool = False,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieves list of real sandbox executions with strict RBAC user isolation."""
        import json
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            query = "SELECT id, user_id, username, conversation_id, language, code, code_hash, filename, exit_code, stdout, stderr, duration_ms, status, timed_out, artifacts_json, created_at FROM sandbox_executions WHERE 1=1"
            params: List[Any] = []
            if not is_admin:
                if user_id is not None:
                    query += " AND user_id = ?"
                    params.append(user_id)
                else:
                    return []
            if conversation_id:
                query += " AND conversation_id = ?"
                params.append(conversation_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                try:
                    item["artifacts"] = json.loads(item.get("artifacts_json") or "[]")
                except Exception:
                    item["artifacts"] = []
                result.append(item)
            return result
        finally:
            conn.close()

    def get_execution(
        self,
        execution_id: str,
        user_id: Optional[int] = None,
        is_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a single execution record with strict RBAC validation."""
        import json
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sandbox_executions WHERE id = ?", (execution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            if not is_admin and (user_id is None or item["user_id"] != user_id):
                return None
            try:
                item["artifacts"] = json.loads(item.get("artifacts_json") or "[]")
            except Exception:
                item["artifacts"] = []
            return item
        finally:
            conn.close()
