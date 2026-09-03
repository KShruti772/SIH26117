import os
import sys
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
        artifacts_storage: str = "data/artifacts/sandbox",
        output_limit_bytes: int = 65536
    ):
        self.workspace_parent = os.path.abspath(workspace_parent)
        self.artifacts_storage = os.path.abspath(artifacts_storage)
        self.output_limit_bytes = output_limit_bytes
        os.makedirs(self.workspace_parent, exist_ok=True)
        os.makedirs(self.artifacts_storage, exist_ok=True)

    @staticmethod
    def _validate_ast_safety(code: str) -> Optional[str]:
        """Statically inspects Python code AST for forbidden module imports."""
        import ast
        forbidden_modules = {"ctypes", "winreg", "subprocess", "socket", "importlib", "shutil"}
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
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes Python code in a separate process, managing execution limits, input files, artifacts, and cleanup."""
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest() if isinstance(code, str) else None

        def rejected_result(error: str) -> Dict[str, Any]:
            AuditLogger.log_event(
                action="SANDBOX_EXECUTION",
                component="sandbox.subprocess",
                status="failure",
                user_id=user_id,
                username=username,
                metadata={
                    "error": error,
                    "code_hash": code_hash,
                    "language": "python"
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
        run_id = f"run_{uuid.uuid4()}"
        run_dir = os.path.join(self.workspace_parent, run_id)
        os.makedirs(run_dir, exist_ok=True)
        
        # 3. Mount input files safely
        mounted_input_names = set()
        if files and isinstance(files, dict):
            for fname, fcontent in files.items():
                if not fname or ".." in fname or "/" in fname or "\\" in fname:
                    shutil.rmtree(run_dir, ignore_errors=True)
                    return rejected_result(f"Security Rejection: Invalid input filename '{fname}' (path traversal blocked).")
                
                target_file_path = os.path.join(run_dir, fname)
                try:
                    if isinstance(fcontent, bytes):
                        with open(target_file_path, "wb") as fh:
                            fh.write(fcontent)
                    elif isinstance(fcontent, str):
                        with open(target_file_path, "w", encoding="utf-8") as fh:
                            fh.write(fcontent)
                    mounted_input_names.add(fname)
                except Exception as fe:
                    shutil.rmtree(run_dir, ignore_errors=True)
                    return rejected_result(f"Input file mounting failed for '{fname}': {fe}")

        socket_block_prefix = (
            "import socket\n"
            "def _blocked_socket(*args, **kwargs):\n"
            "    raise PermissionError('Sandbox Security Violation: Network socket creation is blocked.')\n"
            "socket.socket = _blocked_socket\n\n"
        )
        script_path = os.path.join(run_dir, "script.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(socket_block_prefix + code)

        # 4. Environment restriction (strip all host secrets, DB URLs, credentials)
        safe_env = {}
        for key in ["SYSTEMROOT", "SYSTEMDRIVE", "PATH", "PATHEXT", "TEMP", "TMP", "TMPDIR", "HOME", "USER", "LANG", "LC_ALL", "PYTHONPATH"]:
            if key in os.environ:
                safe_env[key] = os.environ[key]
        
        logger.info(f"Launching subprocess sandbox execution ID {run_id}")
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

        # 7. Collect generated artifact files
        artifacts: List[Dict[str, Any]] = []
        try:
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()

            for item in os.listdir(run_dir):
                if item == "script.py" or item in mounted_input_names:
                    continue
                
                item_path = os.path.join(run_dir, item)
                if os.path.isfile(item_path):
                    with open(item_path, "rb") as afh:
                        art_bytes = afh.read()
                    
                    art_size = len(art_bytes)
                    art_hash = hashlib.sha256(art_bytes).hexdigest()
                    art_id = f"art_{uuid.uuid4().hex[:12]}"
                    mime, _ = mimetypes.guess_type(item)
                    mime_type = mime or "application/octet-stream"

                    # Persist file into sandbox artifacts storage
                    perm_path = os.path.join(self.artifacts_storage, f"{art_id}_{item}")
                    with open(perm_path, "wb") as pfh:
                        pfh.write(art_bytes)

                    # Record in SQLite sandbox_artifacts table
                    cursor.execute("""
                        INSERT INTO sandbox_artifacts (
                            id, execution_id, user_id, username, conversation_id,
                            filename, file_path, file_size, mime_type, content_hash, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        art_id, run_id, user_id or -1, username or "", conversation_id or "",
                        item, perm_path, art_size, mime_type, art_hash, now_iso
                    ))

                    artifacts.append({
                        "id": art_id,
                        "filename": item,
                        "file_size": art_size,
                        "mime_type": mime_type,
                        "content_hash": art_hash,
                        "download_url": f"/sandbox/artifacts/{art_id}/download",
                        "created_at": now_iso
                    })
            
            conn.commit()
            conn.close()
        except Exception as arte:
            logger.warning(f"Error collecting sandbox artifacts for run {run_id}: {arte}")

        # 8. Graceful workspace directory cleanup
        try:
            shutil.rmtree(run_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up sandbox directory '{run_dir}': {e}")

        success = (exit_code == 0) and not timed_out and (error_msg is None)
        logger.info(f"Sandbox run ID {run_id} completed in {duration_ms}ms with success={success}, artifacts={len(artifacts)}")
        
        # 9. Audit sandbox execution
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="sandbox.subprocess",
            status="success" if success else "failure",
            resource=run_id,
            duration_ms=duration_ms,
            user_id=user_id,
            username=username,
            metadata={
                "execution_id": run_id,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "artifact_count": len(artifacts),
                "artifacts": [a["filename"] for a in artifacts],
                "language": "python",
                "code_hash": code_hash
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
            "artifacts": artifacts,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error_msg or (stderr if not success and stderr else None)
        }
