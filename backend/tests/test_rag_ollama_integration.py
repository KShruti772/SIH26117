import os
import unittest
import asyncio
from unittest.mock import MagicMock
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.rag.embeddings import get_local_embedding_model
from backend.rag.pipeline import AegisRagService
from backend.agents.controller.agent import AgentController

class TestRagOllamaIntegration(unittest.TestCase):
    def setUp(self):
        self.registry_manager = ModelRegistryManager("backend/models/registry/registry.json")
        self.loader_manager = ModelLoaderManager(self.registry_manager)
        
        async def fake_switch_model(model_id):
            return {"status": "success", "model_id": model_id}
        self.loader_manager.switch_model = fake_switch_model
        
        self.mock_rag_service = MagicMock()
        self.mock_sandbox_service = MagicMock()
        self.mock_sandbox_service.execute.return_value = {
            "success": True,
            "status": "success",
            "stdout": "10\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 0.05
        }
        self.controller = AgentController(
            registry_manager=self.registry_manager,
            loader_manager=self.loader_manager,
            rag_service=self.mock_rag_service,
            sandbox_service=self.mock_sandbox_service
        )

    def test_full_rag_context_to_ollama_pipeline(self):
        """Verify full flow: RAG query -> retrieval -> context assembly -> Ollama invocation -> response with sources."""
        async def run_test():
            query = "What is our workplace safety procedure?"
            
            # Mock RAG retrieval output
            self.mock_rag_service.search.return_value = [
                {
                    "chunk_id": "chunk_1",
                    "text": "All operators must wear safety helmets in zone A.",
                    "distance": 0.1852,
                    "metadata": {
                        "filename": "safety_manual.pdf",
                        "page_number": 4,
                        "embedding_model": "all-MiniLM-L6-v2"
                    }
                }
            ]

            # Mock Ollama generator call
            called_prompts = []
            async def fake_generate(prompt, system_prompt=None, model_id=None, timeout=30.0):
                called_prompts.append(prompt)
                return "Grounded Answer: Safety helmets are required in zone A."

            self.loader_manager.generate = fake_generate

            res = await self.controller.run(query)

            self.assertTrue(res["success"])
            self.assertTrue(res["rag_used"])
            self.assertEqual(len(res["sources"]), 1)
            self.assertEqual(res["sources"][0]["filename"], "safety_manual.pdf")
            self.assertEqual(res["sources"][0]["page"], 4)
            self.assertEqual(res["sources"][0]["distance"], 0.1852)
            self.assertIn("Safety helmets are required in zone A.", res["answer"])
            self.assertEqual(len(called_prompts), 1)
            self.assertIn("RETRIEVED KNOWLEDGE:", called_prompts[0])
            self.assertIn("[Source: safety_manual.pdf | Page 4]", called_prompts[0])

        asyncio.run(run_test())

    def test_non_rag_query_bypasses_retrieval(self):
        """Verify non-RAG question (e.g. coding) directly invokes Ollama without RAG sources."""
        async def run_test():
            query = "write python code to sum two numbers"
            
            async def fake_generate(prompt, system_prompt=None, model_id=None, timeout=30.0):
                return "def sum(a, b): return a + b"

            self.loader_manager.generate = fake_generate

            res = await self.controller.run(query)

            self.assertTrue(res["success"])
            self.assertFalse(res["rag_used"])
            self.assertEqual(len(res["sources"]), 0)

        asyncio.run(run_test())

    def test_ollama_failure_handled_gracefully(self):
        """Verify Ollama runtime failure is caught without unhandled exceptions."""
        async def run_test():
            query = "What is the emergency shutdown procedure?"
            self.mock_rag_service.search.return_value = [
                {
                    "chunk_id": "c1",
                    "text": "Turn off main switch.",
                    "distance": 0.1,
                    "metadata": {"filename": "doc.pdf", "page_number": 1}
                }
            ]

            async def failing_generate(prompt, system_prompt=None, model_id=None, timeout=30.0):
                raise Exception("Ollama HTTP 500 Connection Refused")

            self.loader_manager.generate = failing_generate

            res = await self.controller.run(query)

            self.assertFalse(res["success"])
            self.assertIn("Local model generation failed", res["answer"])

        asyncio.run(run_test())

    def test_rag_retrieval_failure_handled_safely(self):
        """Verify ChromaDB search exception fails step cleanly."""
        async def run_test():
            query = "What is the policy?"
            self.mock_rag_service.search.side_effect = Exception("ChromaDB vector error")

            res = await self.controller.run(query)

            self.assertFalse(res["success"])
            self.assertIn("Execution halted", res["error"])

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
