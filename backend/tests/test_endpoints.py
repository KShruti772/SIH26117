import unittest
import urllib.request
import json
import subprocess
import time
import sys

class TestAegisBackbone(unittest.TestCase):
    server_proc = None

    @classmethod
    def setUpClass(cls):
        # Start uvicorn server in a subprocess on test port 8089
        cls.server_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8089"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Give the server a moment to start up
        time.sleep(2)

    @classmethod
    def tearDownClass(cls):
        # Shut down the server process cleanly
        if cls.server_proc:
            cls.server_proc.terminate()
            try:
                cls.server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.server_proc.kill()

    def test_root_endpoint(self):
        url = "http://127.0.0.1:8089/"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                self.assertEqual(response.status, 200)
                data = json.loads(response.read().decode('utf-8'))
                self.assertEqual(data["application"], "AEGIS Sovereign AI Workbench")
                self.assertEqual(data["status"], "running")
        except Exception as e:
            self.fail(f"Failed to query root endpoint: {e}")

    def test_health_endpoint(self):
        url = "http://127.0.0.1:8089/health"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                self.assertEqual(response.status, 200)
                data = json.loads(response.read().decode('utf-8'))
                self.assertEqual(data["status"], "ok")
        except Exception as e:
            self.fail(f"Failed to query health endpoint: {e}")

if __name__ == "__main__":
    unittest.main()
