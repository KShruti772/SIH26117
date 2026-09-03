import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.security.dependencies import get_current_user
from backend.app.config.settings import settings
from backend.security.database import init_db

# Mock user object matching sqlite Row interface/dict
class MockUser:
    def __init__(self, data):
        self.data = data
    def __getitem__(self, key):
        return self.data[key]
    def get(self, key, default=None):
        return self.data.get(key, default)
    def keys(self):
        return self.data.keys()

class TestChatRoute(unittest.TestCase):
    """Unit tests verifying the FastAPI `/chat` endpoint validations and auth controls."""

    @classmethod
    def setUpClass(cls):
        cls.original_db_path = settings.AUTH_DB_PATH
        cls.test_dir = tempfile.mkdtemp()
        settings.AUTH_DB_PATH = os.path.join(cls.test_dir, "audit.db")
        init_db()

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls.original_db_path
        for filename in os.listdir(cls.test_dir):
            os.remove(os.path.join(cls.test_dir, filename))
        os.rmdir(cls.test_dir)

    def setUp(self):
        self.client = TestClient(app)
        self.mock_user = MockUser({
            "id": 1,
            "username": "testuser",
            "role": "user",
            "is_active": True,
            "created_at": "2026-08-27"
        })

    def tearDown(self):
        # Clear dependency overrides after each test
        app.dependency_overrides.clear()

    def test_chat_unauthenticated_rejected(self):
        """Verify request without bearer token is rejected with 401 Unauthorized."""
        app.dependency_overrides.clear()
        response = self.client.post("/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 401)

    def test_chat_empty_prompt_rejected(self):
        """Verify empty message triggers 422 Validation Error."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user

        # Empty string
        response = self.client.post("/chat", json={"message": ""})
        self.assertEqual(response.status_code, 422)

    def test_chat_oversized_prompt_rejected(self):
        """Verify prompts exceeding 1000 characters trigger 422 Validation Error."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user

        long_message = "x" * 1001
        response = self.client.post("/chat", json={"message": long_message})
        self.assertEqual(response.status_code, 422)

    @patch("backend.app.main.agent_controller")
    def test_chat_successful_execution_routing(self, mock_controller):
        """Verify valid chat prompts route cleanly and return sanitized responses."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user

        # Mock AgentController.run response as an AsyncMock
        mock_controller.run = AsyncMock(return_value={
            "success": True,
            "duration_ms": 150,
            "plan": {
                "final_output": "The computed array sum is 45.",
                "steps": [
                    {
                        "step_id": "step_1",
                        "capability": "text_generation",
                        "input": {"action": "rag_search"},
                        "output": [
                            {
                                "text": "chunk text context",
                                "metadata": {"filename": "procedures.pdf", "page_number": 2, "raw_path": "/absolute/path"}
                            }
                        ],
                        "verification_result": "PASS"
                    }
                ]
            },
            "error": None
        })

        response = self.client.post("/chat", json={"message": "compute array sum"})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["answer"], "The computed array sum is 45.")
        self.assertEqual(data["verification"], "PASS")
        self.assertEqual(len(data["sources"]), 1)
        self.assertEqual(data["sources"][0]["filename"], "procedures.pdf")
        self.assertEqual(data["sources"][0]["page_number"], 2)
        # Excludes raw path
        self.assertNotIn("raw_path", data["sources"][0])

if __name__ == "__main__":
    unittest.main()
