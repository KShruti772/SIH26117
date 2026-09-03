import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from backend.models.loaders.manager import ModelLoaderManager
from backend.models.registry.manager import ModelRegistryManager

class TestModelManagement(unittest.TestCase):
    def setUp(self):
        self.mock_registry = MagicMock(spec=ModelRegistryManager)
        self.mock_registry.get_all_models.return_value = [
            {
                "model_id": "gemma3:4b",
                "display_name": "Gemma 3 4B",
                "runtime_model_name": "gemma3:4b",
                "provider": "Google",
                "capabilities": ["text_generation", "coding"],
                "quantization": "Q4_K_M"
            },
            {
                "model_id": "qwen3:4b",
                "display_name": "Qwen 3 4B",
                "runtime_model_name": "qwen3:4b",
                "provider": "Alibaba",
                "capabilities": ["text_generation", "coding"],
                "quantization": "Q4_K_M"
            }
        ]
        self.mock_registry.get_model.side_effect = lambda mid: {
            "model_id": mid,
            "display_name": mid.capitalize(),
            "runtime_model_name": mid,
            "provider": "Ollama"
        }
        self.loader_manager = ModelLoaderManager(registry_manager=self.mock_registry)

    def test_get_discovered_models(self):
        async def run_test():
            def mock_send_request(path, method="GET", payload=None, timeout=60.0):
                if path == "/api/tags":
                    return {
                        "models": [
                            {
                                "name": "gemma3:4b",
                                "size": 3338801804,
                                "modified_at": "2026-08-26T21:51:38.2311921+05:30",
                                "details": {
                                    "format": "gguf",
                                    "family": "gemma3",
                                    "parameter_size": "4.3B",
                                    "quantization_level": "Q4_K_M"
                                }
                            },
                            {
                                "name": "qwen3:4b",
                                "size": 2497293931,
                                "modified_at": "2026-08-26T21:36:59.870211+05:30",
                                "details": {
                                    "format": "gguf",
                                    "family": "qwen3",
                                    "parameter_size": "4.0B",
                                    "quantization_level": "Q4_K_M"
                                }
                            }
                        ]
                    }
                return {}

            self.loader_manager._send_request = mock_send_request
            self.loader_manager.get_current_model_id = AsyncMock(return_value="gemma3:4b")

            discovered = await self.loader_manager.get_discovered_models()
            self.assertEqual(len(discovered), 2)
            
            gemma = next(m for m in discovered if m["model_id"] == "gemma3:4b")
            self.assertEqual(gemma["status"], "ACTIVE")
            self.assertTrue(gemma["is_active"])
            self.assertTrue(gemma["is_installed"])
            self.assertEqual(gemma["parameter_size"], "4.3B")

            qwen = next(m for m in discovered if m["model_id"] == "qwen3:4b")
            self.assertEqual(qwen["status"], "INSTALLED")
            self.assertFalse(qwen["is_active"])
            self.assertTrue(qwen["is_installed"])

        asyncio.run(run_test())

    def test_model_switching(self):
        async def run_test():
            def mock_send_request(path, method="GET", payload=None, timeout=60.0):
                if path == "/":
                    return {"status": "Ollama is running"}
                if path == "/api/ps":
                    return {"models": [{"name": "gemma3:4b"}]}
                if path == "/api/generate":
                    return {"response": ""}
                return {}

            self.loader_manager._send_request = mock_send_request
            self.loader_manager.is_runtime_available = AsyncMock(return_value=True)
            self.loader_manager.get_running_models = AsyncMock(return_value=["gemma3:4b"])
            self.loader_manager.unload_model = AsyncMock()
            self.loader_manager.load_model = AsyncMock()

            res = await self.loader_manager.switch_model("qwen3:4b")
            self.assertEqual(res["status"], "success")
            self.assertEqual(self.loader_manager.current_model_id, "qwen3:4b")

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
