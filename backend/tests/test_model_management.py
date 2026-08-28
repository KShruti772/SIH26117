import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from backend.app.main import app, loader_manager, registry_manager
from backend.security.dependencies import get_current_user

# Mock sqlite Row interface/dict
class MockUser:
    def __init__(self, data):
        self.data = data
    def __getitem__(self, key):
        return self.data[key]
    def get(self, key, default=None):
        return self.data.get(key, default)
    def keys(self):
        return self.data.keys()

class TestModelManagement(unittest.IsolatedAsyncioTestCase):
    """Verifies local AI inference and model management endpoints, fallbacks, and security boundaries."""

    def setUp(self):
        self.client = TestClient(app)
        self.user_a = MockUser({"id": 10, "username": "usera", "role": "user"})
        self.user_b = MockUser({"id": 11, "username": "userb", "role": "user"})
        self.admin = MockUser({"id": 100, "username": "admin", "role": "admin"})

    def tearDown(self):
        app.dependency_overrides.clear()
        loader_manager.current_model_id = None

    def test_authentication_required_for_model_routes(self):
        """Verify model management endpoints return 401 if unauthenticated."""
        # GET /models
        r1 = self.client.get("/models")
        self.assertEqual(r1.status_code, 401)

        # GET /models/current
        r2 = self.client.get("/models/current")
        self.assertEqual(r2.status_code, 401)

        # POST /models/select
        r3 = self.client.post("/models/select", json={"model_id": "qwen2.5-3b-instruct"})
        self.assertEqual(r3.status_code, 401)

    def test_model_listing(self):
        """Verify standard users can list configured model profiles successfully."""
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        response = self.client.get("/models")
        self.assertEqual(response.status_code, 200)
        models = response.json()
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)
        self.assertEqual(models[0]["model_id"], "qwen2.5-3b-instruct")

    def test_get_current_model_default(self):
        """Verify system returns default model profile when no model is active."""
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        response = self.client.get("/models/current")
        self.assertEqual(response.status_code, 200)
        profile = response.json()
        self.assertEqual(profile["model_id"], "qwen2.5-3b-instruct")

    @patch("backend.models.loaders.manager.ModelLoaderManager.switch_model")
    def test_select_model_success(self, mock_switch):
        """Verify switching model successfully triggers loader swap."""
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        mock_switch.return_value = {
            "status": "success",
            "model_id": "qwen2.5-coder-1.5b-instruct",
            "active_model": "qwen2.5-coder:1.5b-instruct-q4_K_M",
            "details": "swapped"
        }

        response = self.client.post("/models/select", json={"model_id": "qwen2.5-coder-1.5b-instruct"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["details"], "swapped")
        self.assertEqual(loader_manager.current_model_id, "qwen2.5-coder-1.5b-instruct")

    def test_select_invalid_model(self):
        """Verify selecting a model not in the registry is rejected."""
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        response = self.client.post("/models/select", json={"model_id": "nonexistent-model"})
        self.assertEqual(response.status_code, 500)  # Fails inside switch_model validation check

    @patch("backend.models.loaders.manager.ModelLoaderManager.switch_model")
    @patch("backend.models.loaders.manager.ModelLoaderManager.is_runtime_available")
    def test_select_model_offline_development_mock_fallback(self, mock_available, mock_switch):
        """Verify model selection falls back to simulated load when Ollama is offline in development."""
        from backend.models.loaders.manager import RuntimeUnavailableError
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        
        mock_switch.side_effect = RuntimeUnavailableError("Ollama local service is unreachable.")
        mock_available.return_value = False

        # In development: returns simulated_load
        with patch("backend.app.config.settings.settings.APP_ENV", "development"):
            response = self.client.post("/models/select", json={"model_id": "qwen2.5-coder-1.5b-instruct"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["details"], "simulated_load")
            self.assertEqual(data["model_id"], "qwen2.5-coder-1.5b-instruct")

        # In production: returns 503 Service Unavailable
        with patch("backend.app.config.settings.settings.APP_ENV", "production"):
            response = self.client.post("/models/select", json={"model_id": "qwen2.5-coder-1.5b-instruct"})
            self.assertEqual(response.status_code, 503)

    @patch("backend.app.main.agent_controller")
    @patch("backend.models.loaders.manager.ModelLoaderManager.is_runtime_available")
    def test_chat_inference_mode_mock_identification(self, mock_available, mock_controller):
        """Verify mock fallback state is clearly visible in the chat response model_info."""
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        
        # Simulated offline:
        mock_available.return_value = False
        mock_controller.run = AsyncMock(return_value={
            "success": True,
            "duration_ms": 10,
            "plan": {
                "final_output": "Mocked response text.",
                "steps": [],
                "inference_mode": "mock"
            }
        })

        response = self.client.post("/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("model_info", data)
        self.assertEqual(data["model_info"]["inference_mode"], "mock")

    @patch("backend.app.main.agent_controller")
    @patch("backend.models.loaders.manager.ModelLoaderManager.is_runtime_available")
    def test_chat_inference_mode_real_identification(self, mock_available, mock_controller):
        """Verify real inference state is active in model_info when online."""
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        
        # Simulated online:
        mock_available.return_value = True
        mock_controller.run = AsyncMock(return_value={
            "success": True,
            "duration_ms": 10,
            "plan": {
                "final_output": "Real AI output.",
                "steps": [],
                "inference_mode": "real"
            }
        })

        response = self.client.post("/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("model_info", data)
        self.assertEqual(data["model_info"]["inference_mode"], "real")

    @patch("backend.agents.controller.agent.AgentController._call_llm")
    @patch("backend.app.main.rag_service")
    @patch("backend.app.main.loader_manager.switch_model")
    async def test_rag_owner_id_filter_remains_active_during_chat(self, mock_switch, mock_rag, mock_call_llm):
        """Verify chat agent retrieval loops query ONLY User A's documents for User A."""
        from backend.agents.controller.agent import AgentController
        
        # Instantiating a clean agent controller mapping the mock RAG service
        controller = AgentController(
            registry_manager=registry_manager,
            loader_manager=loader_manager,
            rag_service=mock_rag
        )

        mock_call_llm.return_value = "Real answer grounded on source documents."
        mock_rag.search.return_value = [{"text": "confidential data", "metadata": {"filename": "A.pdf", "page_number": 1}}]
        mock_switch.return_value = {"status": "success"}

        # 1. Run User A query: RAG search must pass filter owner_id=10
        await controller.run("search company manual about leaks", current_user=self.user_a)
        mock_rag.search.assert_any_call(
            "safety procedures",
            filter_metadata={"owner_id": 10}
        )

        # 2. Run User B query: RAG search must pass filter owner_id=11
        await controller.run("search company manual about leaks", current_user=self.user_b)
        mock_rag.search.assert_any_call(
            "safety procedures",
            filter_metadata={"owner_id": 11}
        )

if __name__ == "__main__":
    unittest.main()
