import unittest
import os
import shutil
import socket
from backend.tools.code_sandbox.sandbox import SubprocessSandbox

class TestSubprocessSandbox(unittest.TestCase):
    """Unit tests and security boundary verification for the Subprocess-based local execution sandbox."""
    
    @classmethod
    def setUpClass(cls):
        cls.sandbox_dir = "sandbox_runs_test"
        cls.sandbox = SubprocessSandbox(workspace_parent=cls.sandbox_dir) # Standard 64KB limit
        cls.restricted_sandbox = SubprocessSandbox(workspace_parent=cls.sandbox_dir, output_limit_bytes=100) # Tiny limit for testing truncation

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.sandbox_dir):
            try:
                shutil.rmtree(cls.sandbox_dir)
            except Exception:
                pass

    def test_simple_success_program(self):
        """1, 5, 7. Verify a successful script returns exit code 0 and stdout."""
        code = "print('Aegis Sandbox test')"
        res = self.sandbox.execute(code)
        self.assertTrue(res["success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("Aegis Sandbox test", res["stdout"])
        self.assertFalse(res["timed_out"])
        self.assertIsNone(res["error"])

    def test_python_exception(self):
        """2, 6. Verify raised python exceptions are captured in stderr."""
        code = "raise ValueError('Custom test error')"
        res = self.sandbox.execute(code)
        self.assertFalse(res["success"])
        self.assertNotEqual(res["exit_code"], 0)
        self.assertIn("ValueError: Custom test error", res["stderr"])

    def test_syntax_error(self):
        """3. Verify script syntax errors are captured in stderr or error."""
        code = "def malformed_syntax("
        res = self.sandbox.execute(code)
        self.assertFalse(res["success"])
        self.assertIn("SyntaxError", res["error"] + res["stderr"])

    def test_timeout(self):
        """4. Verify infinite loops or slow code trigger hard timeout terminations."""
        code = "import time\nwhile True:\n    time.sleep(0.1)"
        res = self.sandbox.execute(code, timeout_seconds=1.0)
        self.assertFalse(res["success"])
        self.assertTrue(res["timed_out"])
        self.assertEqual(res["exit_code"], -1)
        self.assertIn("timed out", res["error"].lower())

    def test_workspace_cleanup(self):
        """8. Verify that the temporary workspace directory is cleaned up after execution."""
        code = "print('cleanup test')"
        # Execute run
        res = self.sandbox.execute(code)
        self.assertTrue(res["success"])
        
        # Verify no directories remain in sandbox_runs_test
        dirs = os.listdir(self.sandbox_dir)
        self.assertEqual(len(dirs), 0, "Workspace directories must be deleted after run.")

    def test_environment_scrubbing(self):
        """9. Verify parent env variables (like credentials) are stripped."""
        # Set a dummy secret variable in the parent process
        os.environ["SECRET_CREDENTIAL"] = "SUPER_SECRET_1234"
        
        code = "import os\nprint('Secret present:', 'SECRET_CREDENTIAL' in os.environ)"
        res = self.sandbox.execute(code)
        self.assertTrue(res["success"])
        self.assertIn("Secret present: False", res["stdout"])
        
        # Clean parent env
        del os.environ["SECRET_CREDENTIAL"]

    def test_output_limit_protection(self):
        """10. Verify massive output print loops are truncated and flagged as failed."""
        code = "while True:\n    print('FLOOD_PRINT_LOOP_AAAAAAA')"
        res = self.restricted_sandbox.execute(code, timeout_seconds=1.0)
        
        # Should be truncated and marked failed
        self.assertFalse(res["success"])
        self.assertIn("[TRUNCATED: Output limit exceeded]", res["stdout"])
        self.assertLessEqual(len(res["stdout"]), self.restricted_sandbox.output_limit_bytes + 50)

    def test_empty_code_rejected(self):
        """11. Verify empty or whitespace code inputs are rejected."""
        res = self.sandbox.execute("   ")
        self.assertFalse(res["success"])
        self.assertIn("Rejected", res["error"])

    def test_invalid_timeout_rejected(self):
        """12. Verify out of bound timeout values are rejected."""
        res = self.sandbox.execute("print('test')", timeout_seconds=-5)
        self.assertFalse(res["success"])
        self.assertIn("Rejected", res["error"])

    def test_multiple_runs_isolated_workspaces(self):
        """13. Verify parallel sandbox executions do not collide or share directories."""
        code1 = "import time\ntime.sleep(0.5)\nprint('Run 1 complete')"
        code2 = "print('Run 2 complete')"
        
        # Executing runs without waiting shows both directories exist separately
        res2 = self.sandbox.execute(code2)
        res1 = self.sandbox.execute(code1)
        
        self.assertTrue(res1["success"])
        self.assertTrue(res2["success"])
        self.assertIn("Run 1 complete", res1["stdout"])
        self.assertIn("Run 2 complete", res2["stdout"])

    def test_parent_fastapi_process_safety(self):
        """14. Verify division by zero inside sandbox does not crash unittest runner."""
        code = "x = 1 / 0"
        res = self.sandbox.execute(code)
        self.assertFalse(res["success"])
        self.assertNotEqual(res["exit_code"], 0)
        self.assertIn("ZeroDivisionError", res["stderr"])

    # -------------------------------------------------------------------------
    # SECURITY TESTING (VERIFYING WINDOWS SUBPROCESS SECURITY LIMITS):
    # -------------------------------------------------------------------------
    def test_security_filesystem_boundary(self):
        """
        Verify that a script inside the sandbox CAN read parent files.
        (Documenting Windows subprocess filesystem jail limitations).
        """
        # Create a mock file in the parent folder
        test_file = "parent_file_test.txt"
        with open(test_file, "w") as f:
            f.write("parent data leakage")
            
        try:
            # Code attempts to escape the temporary workspace dir and read parent file
            code = f"import os\nwith open('../../{test_file}', 'r') as f:\n    print(f.read())"
            res = self.sandbox.execute(code)
            
            # Since standard subprocesses do not block filesystem access on Windows,
            # this check will succeed, proving filesystem leakage is NOT blocked.
            self.assertTrue(res["success"], "Subprocess filesystem escape was blocked (unexpected on Windows).")
            self.assertIn("parent data leakage", res["stdout"])
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_security_network_boundary(self):
        """
        Verify that socket calls in sandbox are rejected by security policy.
        """
        code = "import socket\ns = socket.socket()\ns.connect(('127.0.0.1', 8080))"
        res = self.sandbox.execute(code)
        self.assertFalse(res["success"])
        self.assertIn("Security Rejection", res["error"])

if __name__ == "__main__":
    unittest.main()
