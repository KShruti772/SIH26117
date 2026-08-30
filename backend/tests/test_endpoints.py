import unittest
from fastapi.testclient import TestClient
from backend.app.main import app

class TestAegisBackbone(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["application"], "AEGIS Sovereign AI Workbench")
        self.assertEqual(data["status"], "running")

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")

if __name__ == "__main__":
    unittest.main()
