import os
import sys
import uuid
import time
import shutil
import subprocess
import logging
from typing import Dict, Any

logger = logging.getLogger("aegis.sandbox")

class SandboxError(Exception):
    """Base exception for code sandbox execution errors."""
    pass

class BaseSandbox:
    """Interface class to allow future swap of execution sandbox backends (e.g., to Docker/microVMs)."""
    
    def execute(self, code: str, timeout_seconds: float = 10.0) -> Dict[str, Any]:
        """Executes untrusted code and returns a structured status dictionary."""
        raise NotImplementedError

class SubprocessSandbox(BaseSandbox):
    """
    Subprocess-based sandbox executing Python code in an isolated child process.
    
    ---------------------------------------------------------------------------
    SECURITY BOUNDARY NOTICE (WINDOWS PLATFORM LIMITATIONS):
    ---------------------------------------------------------------------------
    1. This sandbox runs code in a separate subprocess with a scrubbed environment.
    2. ON WINDOWS: It does NOT enforce network namespaces or filesystem jails.
       The child process inherits the OS user account permissions, meaning it
       can read/write accessible local files outside the workspace and open
       outbound TCP sockets (network access is NOT blocked natively).
    3. FOR PRODUCTION/AIR-GAP: Fully secure isolation requires deploying Aegis
       on Linux with Docker container isolations (using --network none) or 
       MicroVM virtualization. This implementation is an MVP-grade local executor.
    ---------------------------------------------------------------------------
    """
    
    def __init__(self, workspace_parent: str = "sandbox_runs", output_limit_bytes: int = 65536):
        self.workspace_parent = os.path.abspath(workspace_parent)
        self.output_limit_bytes = output_limit_bytes
        os.makedirs(self.workspace_parent, exist_ok=True)

    def execute(self, code: str, timeout_seconds: float = 10.0) -> Dict[str, Any]:
        """Executes Python code in a separate process, managing execution limits and cleanup."""
        from backend.security.audit import AuditLogger
        
        # 1. Input validation
        if not isinstance(code, str) or not code.strip():
            AuditLogger.log_event(
                action="SANDBOX_EXECUTION",
                component="tools.code_sandbox.sandbox",
                status="failure",
                metadata={"error_category": "invalid_code"}
            )
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
                "duration_ms": 0,
                "error": "Rejected: Empty or invalid code string."
            }
            
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0 or timeout_seconds > 60:
            AuditLogger.log_event(
                action="SANDBOX_EXECUTION",
                component="tools.code_sandbox.sandbox",
                status="failure",
                metadata={"error_category": "invalid_timeout"}
            )
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
                "duration_ms": 0,
                "error": "Rejected: Timeout must be a positive float between 0.1 and 60.0 seconds."
            }

        # 2. Setup isolated temporary workspace
        run_id = f"run_{uuid.uuid4()}"
        run_dir = os.path.join(self.workspace_parent, run_id)
        os.makedirs(run_dir, exist_ok=True)
        
        script_path = os.path.join(run_dir, "script.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # 3. Environment restriction
        # Scrub all parent variables (secrets, DB URLs, API keys)
        # Inherit only essential Windows environment paths required to spawn Python
        safe_env = {}
        for key in ["SYSTEMROOT", "SYSTEMDRIVE", "PATH", "PATHEXT", "TEMP", "TMP"]:
            if key in os.environ:
                safe_env[key] = os.environ[key]
        
        logger.info(f"Launching subprocess sandbox execution ID {run_id}")
        start_time = time.perf_counter()
        
        timed_out = False
        exit_code = -1
        stdout = ""
        stderr = ""
        error_msg = None
        
        # 4. Spawning Python subprocess
        try:
            # Use current virtual env Python or fallback to standard system python
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
                # Capture standard outputs with timeout limit
                stdout, stderr = proc.communicate(timeout=timeout_seconds)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.terminate()
                try:
                    # Allow graceful shutdown time
                    stdout, stderr = proc.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    # Force kill child process
                    proc.kill()
                    stdout, stderr = proc.communicate()
                exit_code = -1
                error_msg = f"Execution timed out. Exceeded cap of {timeout_seconds} seconds."

        except Exception as e:
            exit_code = -1
            error_msg = f"Sandbox launch initialization failed: {e}"
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # 5. Output limit checks (protect from print flood loops)
        if len(stdout) > self.output_limit_bytes:
            stdout = stdout[:self.output_limit_bytes] + "\n... [TRUNCATED: Output limit exceeded]"
            error_msg = error_msg or "Output limit exceeded."
            exit_code = -1
            
        if len(stderr) > self.output_limit_bytes:
            stderr = stderr[:self.output_limit_bytes] + "\n... [TRUNCATED: Output limit exceeded]"
            error_msg = error_msg or "Output limit exceeded."
            exit_code = -1

        # 6. Graceful workspace directory cleanup
        try:
            shutil.rmtree(run_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up sandbox directory '{run_dir}': {e}")

        success = (exit_code == 0) and not timed_out and (error_msg is None)
        
        logger.info(f"Sandbox run ID {run_id} completed in {duration_ms}ms with success={success}")
        
        AuditLogger.log_event(
            action="SANDBOX_EXECUTION",
            component="tools.code_sandbox.sandbox",
            status="success" if success else "failure",
            resource=run_id,
            duration_ms=duration_ms,
            metadata={
                "duration_ms": duration_ms,
                "sandbox_exit_code": exit_code,
                "sandbox_timeout": timed_out,
                "error_category": "timeout" if timed_out else ("launch_failure" if error_msg else None)
            }
        )
        
        return {
            "success": success,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "error": error_msg
        }
