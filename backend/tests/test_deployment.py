import os
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.config.settings import Settings, settings
from backend.models.loaders.manager import ModelLoaderManager
from backend.models.registry.manager import ModelRegistryManager

class TestDeploymentConfig(unittest.TestCase):
    """Verifies configuration parsing and deployment environment behaviors."""

    def test_default_network_settings(self):
        """Verify that default settings match localhost limits."""
        s = Settings()
        self.assertEqual(s.HOST, "127.0.0.1")
        self.assertEqual(s.PORT, 8000)
        self.assertEqual(s.OLLAMA_BASE_URL, "http://localhost:11434")

    @patch.dict(os.environ, {
        "HOST": "0.0.0.0",
        "PORT": "9000",
        "OLLAMA_BASE_URL": "http://192.168.1.10:11434"
    })
    def test_env_override_settings(self):
        """Verify that settings correctly parse custom LAN overrides from environment."""
        s = Settings()
        self.assertEqual(s.HOST, "0.0.0.0")
        self.assertEqual(s.PORT, 9000)
        self.assertEqual(s.OLLAMA_BASE_URL, "http://192.168.1.10:11434")

    def test_model_loader_manager_base_url(self):
        """Verify that ModelLoaderManager dynamically falls back to settings.OLLAMA_BASE_URL."""
        mock_registry = MagicMock(spec=ModelRegistryManager)
        
        # 1. Custom URL overrides default base_url
        loader = ModelLoaderManager(mock_registry, base_url="http://custom-ollama:11434")
        self.assertEqual(loader.base_url, "http://custom-ollama:11434")
        
        # 2. None URL dynamically loads current settings configuration
        with patch.object(settings, "OLLAMA_BASE_URL", "http://settings-ollama:11434"):
            loader_default = ModelLoaderManager(mock_registry, base_url=None)
            self.assertEqual(loader_default.base_url, "http://settings-ollama:11434")

    def test_health_check_endpoint(self):
        """Verify that the health-check route resolves successfully."""
        from backend.app.main import app
        client = TestClient(app)
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

if __name__ == "__main__":
    unittest.main()
