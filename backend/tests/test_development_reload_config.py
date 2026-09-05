import os
import time
import socket
import signal
import shutil
import unittest
import requests
import subprocess
from pathlib import Path
from uvicorn.config import Config
from uvicorn.supervisors.watchfilesreload import FileFilter

from backend.tools.code_sandbox.sandbox import SubprocessSandbox


class TestDevelopmentReloadConfig(unittest.TestCase):
    """
    Test suite verifying that development reload (--reload) properly isolates
    sandbox executions, runtime artifacts, and database operations from triggering
    unwanted server restarts while preserving source code reload capabilities.
    """

    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parent.parent.parent
        cls.sandbox_runs_dir = cls.project_root / "sandbox_runs"
        cls.sandbox_data_dir = cls.project_root / "data" / "sandbox"
        cls.sandbox_runs_test_dir = cls.project_root / "sandbox_runs_test"
        
        os.makedirs(cls.sandbox_runs_dir, exist_ok=True)
        os.makedirs(cls.sandbox_data_dir, exist_ok=True)

    @staticmethod
    def _get_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def test_01_file_filter_excludes_sandbox_and_data_paths(self):
        """Verify uvicorn reload configuration ignores sandbox and data paths while watching backend."""
        config = Config(
            "backend.app.main:app",
            reload=True,
            reload_dirs=["backend"],
            reload_excludes=[
                "data*",
                "sandbox_runs*",
                "sandbox_runs_test*",
                "data/*",
                "data/**/*",
                "sandbox_runs/*",
                "sandbox_runs/**/*",
                "sandbox_runs_test/*",
                "sandbox_runs_test/**/*",
            ]
        )
        file_filter = FileFilter(config)

        # 1. Source files in backend should be watched
        backend_file = self.project_root / "backend" / "app" / "main.py"
        sandbox_tool = self.project_root / "backend" / "tools" / "code_sandbox" / "sandbox.py"
        self.assertTrue(file_filter(backend_file), "backend/app/main.py must trigger reload")
        self.assertTrue(file_filter(sandbox_tool), "backend/tools/code_sandbox/sandbox.py must trigger reload")

        # 2. Files in sandbox_runs should NOT trigger reload
        sandbox_run_file = self.sandbox_runs_dir / "run_abc123" / "script.py"
        self.assertFalse(file_filter(sandbox_run_file), "sandbox_runs files must NOT trigger reload")

        # 3. Files in sandbox_runs_test should NOT trigger reload
        sandbox_test_file = self.sandbox_runs_test_dir / "test_run_xyz" / "script.py"
        self.assertFalse(file_filter(sandbox_test_file), "sandbox_runs_test files must NOT trigger reload")

        # 4. Files in data/sandbox should NOT trigger reload
        sandbox_artifact_file = self.sandbox_data_dir / "user_1_factorial.py"
        self.assertFalse(file_filter(sandbox_artifact_file), "data/sandbox files must NOT trigger reload")

        # 5. Database and data files should NOT trigger reload
        db_file = self.project_root / "data" / "private" / "aegis_auth.db"
        self.assertFalse(file_filter(db_file), "data/private database must NOT trigger reload")

    def test_02_live_reload_ignores_sandbox_execution_and_catches_backend_changes(self):
        """
        Integration test: Launch live uvicorn server with development reload configuration,
        run real sandbox execution and file creation, verify no reload occurs,
        then touch a backend source file and verify reload DOES trigger.
        """
        port = self._get_free_port()
        cmd = [
            str(self.project_root / "backend" / ".venv" / "bin" / "python"),
            "-u",
            "-m", "uvicorn", "backend.app.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--reload",
            "--reload-dir", "backend",
            "--reload-exclude", "data*",
            "--reload-exclude", "sandbox_runs*",
            "--reload-exclude", "sandbox_runs_test*",
            "--reload-exclude", "*/data/*",
            "--reload-exclude", "*/data/**/*",
            "--reload-exclude", "*/sandbox_runs/*",
            "--reload-exclude", "*/sandbox_runs/**/*",
            "--reload-exclude", "*/sandbox_runs_test/*",
            "--reload-exclude", "*/sandbox_runs_test/**/*"
        ]

        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1"
        }

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(self.project_root),
            env=env,
            preexec_fn=os.setsid
        )

        test_marker_file = self.project_root / "backend" / "app" / "_temp_reload_marker.py"
        test_script_file = self.sandbox_data_dir / "live_reload_test_script.py"
        test_run_dir = self.sandbox_runs_dir / "live_test_run"

        try:
            # 1. Wait for server startup
            ready = False
            for _ in range(40):
                time.sleep(0.3)
                try:
                    res = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
                    if res.status_code == 200:
                        ready = True
                        break
                except Exception:
                    pass

            self.assertTrue(ready, "Uvicorn test server failed to start within timeout.")

            # 2. Execute real sandbox tool (generates real runtime files)
            sandbox = SubprocessSandbox(
                workspace_parent=str(self.sandbox_runs_dir),
                artifacts_storage=str(self.sandbox_data_dir)
            )
            result = sandbox.execute(
                code="print('Testing sandbox reload isolation: ' + str(2**16))",
                user_id=1,
                username="test_admin"
            )
            self.assertIn(str(result["status"]).lower(), ["success", "completed"])
            self.assertIn("65536", result["stdout"])

            # 3. Create a python file in data/sandbox
            file_meta = sandbox.create_file(
                filename="live_reload_test_script.py",
                content="def calculate():\n    return 42\n",
                user_id=1,
                username="test_admin"
            )
            self.assertTrue(os.path.exists(file_meta["file_path"]))

            # 4. Create a python file in sandbox_runs
            os.makedirs(test_run_dir, exist_ok=True)
            with open(test_run_dir / "script.py", "w") as f:
                f.write("print('sandbox run temp')\n")

            time.sleep(1.0)

            # 5. Now modify a backend source file
            with open(test_marker_file, "w") as f:
                f.write("# Temporary reload trigger marker\n")

            # Collect output lines
            captured_logs = ""
            start = time.time()
            while time.time() - start < 5.0:
                line = proc.stdout.readline()
                if line:
                    captured_logs += line
                    if "Reloading..." in captured_logs or "WatchFiles detected changes" in captured_logs:
                        break

            # Verify that sandbox directories were NOT what triggered reload
            self.assertNotIn(
                "sandbox_runs",
                captured_logs,
                f"FAIL: WatchFiles detected sandbox_runs directory! Logs: {captured_logs}"
            )
            self.assertNotIn(
                "data/sandbox",
                captured_logs,
                f"FAIL: WatchFiles detected data/sandbox directory! Logs: {captured_logs}"
            )

            # Verify that the backend source modification DID trigger reload
            reloaded = (
                "Reloading..." in captured_logs or
                "WatchFiles detected changes" in captured_logs or
                "_temp_reload_marker.py" in captured_logs
            )
            self.assertTrue(
                reloaded,
                f"FAIL: Server did not reload upon backend source modification! Logs: {captured_logs}"
            )

        finally:
            # Cleanup test files
            if test_marker_file.exists():
                test_marker_file.unlink()
            if test_script_file.exists():
                test_script_file.unlink()
            if test_run_dir.exists():
                shutil.rmtree(test_run_dir, ignore_errors=True)

            try:
                if proc.stdout:
                    proc.stdout.close()
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=2)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
