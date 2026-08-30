import unittest
import asyncio
from unittest.mock import MagicMock, patch
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import (
    ModelLoaderManager,
    ModelLoaderError,
    RuntimeUnavailableError
)

class TestOllamaIntegration(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistryManager("backend/models/registry/registry.json")
        self.loader_manager = ModelLoaderManager(self.registry, base_url="http://127.0.0.1:11434")

    def test_runtime_available_coroutine_execution(self):
        """Verify that is_runtime_available is an awaitable coroutine returning boolean."""
        async def run_test():
            with patch.object(self.loader_manager, "_send_request", return_value={"text": "Ollama is running"}):
                available = await self.loader_manager.is_runtime_available()
                self.assertTrue(available)

            with patch.object(self.loader_manager, "_send_request", side_effect=RuntimeUnavailableError("Offline")):
                available = await self.loader_manager.is_runtime_available()
                self.assertFalse(available)

        asyncio.run(run_test())

    def test_generate_requires_non_empty_prompt(self):
        """Verify that generate rejects empty prompt strings."""
        async def run_test():
            with self.assertRaises(ModelLoaderError):
                await self.loader_manager.generate(prompt="")

        asyncio.run(run_test())

    def test_generate_dispatches_correct_payload(self):
        """Verify that generate builds valid JSON payload and awaits HTTP response."""
        async def run_test():
            with patch.object(self.loader_manager, "is_runtime_available", return_value=True):
                with patch.object(
                    self.loader_manager,
                    "_send_request",
                    return_value={"response": "AEGIS LOCAL TEST PASSED"}
                ) as mock_send:
                    res = await self.loader_manager.generate(
                        prompt="Respond with exactly: AEGIS LOCAL TEST PASSED",
                        system_prompt="You are AEGIS.",
                        model_id="qwen2.5-3b-instruct"
                    )
                    self.assertEqual(res, "AEGIS LOCAL TEST PASSED")
                    mock_send.assert_called_once_with(
                        "/api/generate",
                        "POST",
                        {
                            "model": "qwen2.5-3b-instruct",
                            "prompt": "Respond with exactly: AEGIS LOCAL TEST PASSED",
                            "stream": False,
                            "system": "You are AEGIS."
                        },
                        timeout=60.0
                    )

        asyncio.run(run_test())

    def test_generate_raises_runtime_unavailable_when_offline(self):
        """Verify that generate raises RuntimeUnavailableError when daemon is offline."""
        async def run_test():
            with patch.object(self.loader_manager, "is_runtime_available", return_value=False):
                with self.assertRaises(RuntimeUnavailableError) as ctx:
                    await self.loader_manager.generate(prompt="Test prompt")
                self.assertIn("Local inference runtime (Ollama) is offline", str(ctx.exception))

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
