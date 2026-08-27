import unittest
from unittest.mock import patch
import asyncio
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import (
    ModelLoaderManager,
    ModelLoaderError,
    RuntimeUnavailableError,
    ModelLoadTimeoutError,
    ModelUnloadTimeoutError
)

class TestModelLoaderManager(unittest.IsolatedAsyncioTestCase):
    """Unit tests for memory-aware dynamic model loaders under simulated state mock triggers."""
    
    async def asyncSetUp(self):
        self.registry_path = "backend/models/registry/registry.json"
        self.registry_manager = ModelRegistryManager(self.registry_path)
        self.loader = ModelLoaderManager(self.registry_manager)
        
        # Simulated Ollama runtime state
        self.runtime_available = True
        self.mock_vram = []
        self.load_succeeds = True
        self.unload_succeeds = True

    def side_effect_send_request(self, path: str, method: str = "GET", payload: dict = None, timeout: float = 5.0):
        """Simulates response mappings of local Ollama HTTP server."""
        if not self.runtime_available:
            raise RuntimeUnavailableError("Ollama local service is unreachable: Connection refused")
            
        if path == "/":
            return {"text": "Ollama is running"}
            
        elif path == "/api/ps":
            return {"models": [{"name": m} for m in self.mock_vram]}
            
        elif path == "/api/generate":
            if payload:
                model = payload.get("model")
                keep_alive = payload.get("keep_alive")
                if keep_alive == 0:
                    # Unload model if allowed
                    if self.unload_succeeds and model in self.mock_vram:
                        self.mock_vram.remove(model)
                else:
                    # Load model if allowed
                    if self.load_succeeds and model not in self.mock_vram:
                        self.mock_vram.append(model)
            return {}
            
        return {}

    @patch.object(ModelLoaderManager, '_send_request')
    async def test_is_runtime_available_true(self, mock_send):
        """Verify loader registers availability when local host responds successfully."""
        mock_send.side_effect = self.side_effect_send_request
        res = await self.loader.is_runtime_available()
        self.assertTrue(res)

    @patch.object(ModelLoaderManager, '_send_request')
    async def test_is_runtime_available_false(self, mock_send):
        """Verify loader registers offline status when daemon throws errors."""
        self.runtime_available = False
        mock_send.side_effect = self.side_effect_send_request
        res = await self.loader.is_runtime_available()
        self.assertFalse(res)

    @patch.object(ModelLoaderManager, '_send_request')
    async def test_get_running_models(self, mock_send):
        """Verify active VRAM model listing formats are parsed cleanly."""
        self.mock_vram = ["qwen2.5:3b-instruct-q4_K_M", "qwen2.5-coder:1.5b-instruct-q4_K_M"]
        mock_send.side_effect = self.side_effect_send_request
        
        running = await self.loader.get_running_models()
        self.assertEqual(len(running), 2)
        self.assertIn("qwen2.5:3b-instruct-q4_K_M", running)

    @patch.object(ModelLoaderManager, '_send_request')
    async def test_switch_model_already_active(self, mock_send):
        """Verify switch returns immediately if target model is already loaded in VRAM."""
        self.mock_vram = ["qwen2.5:3b-instruct-q4_K_M"]
        mock_send.side_effect = self.side_effect_send_request
        
        res = await self.loader.switch_model("qwen2.5-3b-instruct")
        self.assertEqual(res["details"], "already_loaded")
        self.assertEqual(res["active_model"], "qwen2.5:3b-instruct-q4_K_M")

    @patch.object(ModelLoaderManager, '_send_request')
    async def test_switch_model_requires_swap(self, mock_send):
        """Verify sequential swap: unloads active, loads target, verifies loaded."""
        self.mock_vram = ["qwen2-vl:2b-instruct-q4_K_M"]
        mock_send.side_effect = self.side_effect_send_request
        
        res = await self.loader.switch_model("qwen2.5-coder-1.5b-instruct")
            
        self.assertEqual(res["details"], "swapped")
        self.assertEqual(res["active_model"], "qwen2.5-coder:1.5b-instruct-q4_K_M")
        self.assertIn("qwen2.5-coder:1.5b-instruct-q4_K_M", self.mock_vram)
        self.assertNotIn("qwen2-vl:2b-instruct-q4_K_M", self.mock_vram)

    @patch.object(ModelLoaderManager, '_send_request')
    async def test_switch_model_unload_timeout(self, mock_send):
        """Verify ModelUnloadTimeoutError triggers if active model fails to unload."""
        self.mock_vram = ["qwen2-vl:2b-instruct-q4_K_M"]
        self.unload_succeeds = False  # Simulate unload failing
        mock_send.side_effect = self.side_effect_send_request
        
        # Use short polling / timeout parameters to speed up the test
        with self.assertRaises(ModelUnloadTimeoutError):
            await self.loader.switch_model(
                "qwen2.5-coder-1.5b-instruct",
                load_timeout=1.0,
                unload_timeout=0.05
            )

    @patch.object(ModelLoaderManager, '_send_request')
    async def test_switch_model_load_timeout(self, mock_send):
        """Verify ModelLoadTimeoutError triggers if target model fails to start."""
        self.load_succeeds = False  # Simulate load failing
        mock_send.side_effect = self.side_effect_send_request
        
        with self.assertRaises(ModelLoadTimeoutError):
            await self.loader.switch_model(
                "qwen2.5-coder-1.5b-instruct",
                load_timeout=0.05,
                unload_timeout=1.0
            )

    @patch.object(ModelLoaderManager, '_send_request')
    async def test_concurrency_lock(self, mock_send):
        """Verify that loader lock prevents simultaneous parallel swaps, executing sequentially."""
        mock_send.side_effect = self.side_effect_send_request
        
        # Run two switches concurrently in tasks
        task1 = asyncio.create_task(self.loader.switch_model("qwen2.5-coder-1.5b-instruct"))
        task2 = asyncio.create_task(self.loader.switch_model("qwen2-vl-2b-instruct"))
        
        results = await asyncio.gather(task1, task2)
            
        self.assertEqual(results[0]["active_model"], "qwen2.5-coder:1.5b-instruct-q4_K_M")
        self.assertEqual(results[1]["active_model"], "qwen2-vl:2b-instruct-q4_K_M")
        self.assertIn("qwen2-vl:2b-instruct-q4_K_M", self.mock_vram)
        # Ensure only one model remains loaded
        self.assertEqual(len(self.mock_vram), 1)

if __name__ == "__main__":
    unittest.main()
