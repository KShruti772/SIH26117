import os
import unittest
import asyncio
from unittest.mock import MagicMock, patch
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.agents.controller.agent import AgentController, AgentStep, AgentPlan
from backend.app.verification.verifier import (
    GroundingVerifier,
    make_grounding_verify_callback
)
from backend.tools.code_sandbox.sandbox import SubprocessSandbox

class TestPhase2Intelligence(unittest.IsolatedAsyncioTestCase):
    """
    Comprehensive verification test suite for AEGIS Phase 2:
    - Real RAG pipeline & metadata
    - Grounding verifier & multi-format citations
    - Query routing (General, Knowledge, Coding, Calculation, Mixed)
    - Retry context preservation
    - Real code execution in SubprocessSandbox with structured metadata
    """

    def setUp(self):
        self.registry = ModelRegistryManager("backend/models/registry/registry.json")
        self.mock_loader = MagicMock(spec=ModelLoaderManager)
        self.mock_loader.base_url = "http://localhost:11434"
        self.mock_loader.current_model_id = "gemma3:4b"
        self.mock_loader.switch_model.return_value = {"status": "success"}

        self.mock_rag = MagicMock()
        self.sandbox = SubprocessSandbox(workspace_parent="sandbox_phase2_test")
        self.verifier = GroundingVerifier(safe_directories=[os.getcwd()], min_pass_score=0.7)

    def tearDown(self):
        import shutil
        if os.path.exists("sandbox_phase2_test"):
            try:
                shutil.rmtree("sandbox_phase2_test")
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 1. Routing Verification: General, RAG, Coding, Calculation, Mixed
    # -------------------------------------------------------------------------
    def test_routing_general_query(self):
        """Verify general conceptual questions route to direct text generation."""
        controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader
        )
        general_queries = [
            "What is TCP?",
            "Explain quantum computing in simple terms.",
            "How does a hash map work?",
            "What is the capital of France?"
        ]
        for q in general_queries:
            plan = controller._create_plan(q)
            self.assertEqual(len(plan.steps), 1, f"Expected 1 step for general query: '{q}'")
            self.assertEqual(plan.steps[0].input.get("action"), "generate_text")

    def test_routing_knowledge_query(self):
        """Verify organizational document inquiries route to RAG search and grounded answer."""
        controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader
        )
        knowledge_queries = [
            "What is the emergency shutdown procedure for the boiler?",
            "What does our safety manual say about eye protection?",
            "What are the specs for the alpha cooling tower in our documents?",
            "According to the uploaded protocol, what is the max pressure?"
        ]
        for q in knowledge_queries:
            plan = controller._create_plan(q)
            self.assertEqual(len(plan.steps), 2, f"Expected 2 steps for RAG query: '{q}'")
            self.assertEqual(plan.steps[0].input.get("action"), "rag_search")
            self.assertEqual(plan.steps[1].input.get("action"), "generate_answer")

    def test_routing_coding_query(self):
        """Verify programming tasks route to code generation and sandbox execution."""
        controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader,
            sandbox_service=self.sandbox
        )
        coding_queries = [
            "Write Python code to calculate factorial.",
            "Create a Python function for binary search.",
            "Write a python script to reverse a string.",
            "Write Python code to compute Fibonacci numbers."
        ]
        for q in coding_queries:
            plan = controller._create_plan(q)
            self.assertEqual(len(plan.steps), 2, f"Expected 2 steps for coding query: '{q}'")
            self.assertEqual(plan.steps[0].capability, "coding")
            self.assertEqual(plan.steps[0].input.get("action"), "generate_code")
            self.assertEqual(plan.steps[1].capability, "coding")
            self.assertEqual(plan.steps[1].input.get("action"), "execute_code")

    def test_routing_calculation_query(self):
        """Verify calculation and data analysis requests route to coding sandbox execution."""
        controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader,
            sandbox_service=self.sandbox
        )
        calc_queries = [
            "Calculate average revenue using pandas.",
            "Calculate compound interest using Python.",
            "Compute the sum of prime numbers up to 100 in Python."
        ]
        for q in calc_queries:
            plan = controller._create_plan(q)
            self.assertEqual(plan.steps[0].input.get("action"), "generate_code")
            self.assertEqual(plan.steps[1].input.get("action"), "execute_code")

    def test_routing_mixed_query(self):
        """Verify mixed tasks (read document + generate/execute code) create 3-step pipeline."""
        controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader,
            rag_service=self.mock_rag,
            sandbox_service=self.sandbox
        )
        mixed_queries = [
            "Read this document and write Python code to extract the relevant values.",
            "From the uploaded manual, extract the temperature limits and write code to verify them."
        ]
        for q in mixed_queries:
            plan = controller._create_plan(q)
            self.assertEqual(len(plan.steps), 3, f"Expected 3 steps for mixed query: '{q}'")
            self.assertEqual(plan.steps[0].input.get("action"), "rag_search")
            self.assertEqual(plan.steps[1].input.get("action"), "generate_code")
            self.assertEqual(plan.steps[2].input.get("action"), "execute_code")

    # -------------------------------------------------------------------------
    # 2. RAG Retry Context Backward Search Preservation
    # -------------------------------------------------------------------------
    async def test_rag_retry_context_preserved_after_verification_replan(self):
        """Verify that when a step fails verification and replans, it searches backwards to find original RAG chunks."""
        rag_chunks = [
            {
                "chunk_id": "c_alpha",
                "text": "Alpha cooling tower maximum safe operating temperature is 65 degrees Celsius.",
                "distance": 0.05,
                "metadata": {"filename": "cooling_specs.txt", "page_number": 1}
            }
        ]
        self.mock_rag.search.return_value = rag_chunks

        # Sequence of model outputs: first attempt missing citation (fails), retry provides valid citation (passes)
        outputs = [
            "Alpha cooling operates at 65 degrees.",  # Missing citation
            "Alpha cooling maximum safe operating temperature is 65 degrees Celsius. [Source: cooling_specs.txt | Page 1]"  # Grounded
        ]
        call_count = 0
        async def mock_generate(prompt, model_id=None, timeout=120.0):
            nonlocal call_count
            ans = outputs[min(call_count, len(outputs) - 1)]
            call_count += 1
            return ans

        self.mock_loader.generate = mock_generate

        verify_cb = make_grounding_verify_callback(self.verifier)
        controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader,
            rag_service=self.mock_rag,
            verify_callback=verify_cb,
            max_steps=5,
            max_replans=3
        )

        res = await controller.run("What is the operating temperature of the alpha cooling system in our document?")
        self.assertTrue(res["success"])
        self.assertIn("[Source: cooling_specs.txt | Page 1]", res["answer"])
        self.assertTrue(res["rag_used"])
        self.assertEqual(len(res["sources"]), 1)
        self.assertEqual(res["sources"][0]["filename"], "cooling_specs.txt")

    # -------------------------------------------------------------------------
    # 3. Sandbox Real Execution & Metadata
    # -------------------------------------------------------------------------
    def test_sandbox_exact_output_and_metadata(self):
        """Verify exact calculation in sandbox returns exit_code=0, stdout, timing, and metadata."""
        code = (
            "print('=== Basic Aegis Sandbox Test ===')\n"
            "x = 10\n"
            "y = 20\n"
            "print(f'Sum Calculation: {x + y}')\n"
        )
        res = self.sandbox.execute(code)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("=== Basic Aegis Sandbox Test ===", res["stdout"])
        self.assertIn("Sum Calculation: 30", res["stdout"])
        self.assertEqual(res["stderr"], "")
        self.assertGreaterEqual(res["duration_ms"], 0)
        self.assertIn("execution_id", res)
        self.assertIn("code_hash", res)
        self.assertIn("timestamp", res)

    # -------------------------------------------------------------------------
    # 4. Anti-Hallucination & Honest Refusal
    # -------------------------------------------------------------------------
    async def test_rag_honest_refusal_when_unretrieved(self):
        """Verify when vector database finds no evidence, agent responds with honest refusal without error."""
        self.mock_rag.search.return_value = []
        verify_cb = make_grounding_verify_callback(self.verifier)
        controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader,
            rag_service=self.mock_rag,
            verify_callback=verify_cb
        )
        res = await controller.run("What is the secret reactor recipe in our documents?")
        self.assertTrue(res["success"])
        self.assertTrue(
            any(msg in res["answer"] for msg in [
                "I could not find sufficient evidence",
                "No relevant organizational knowledge"
            ])
        )

    # -------------------------------------------------------------------------
    # 5. Non-RAG General Reasoning Verification
    # -------------------------------------------------------------------------
    async def test_general_reasoning_verification_pass(self):
        """Verify general reasoning queries pass verification without requiring citations."""
        self.mock_loader.generate.return_value = "TCP (Transmission Control Protocol) is a connection-oriented protocol that ensures reliable delivery."
        verify_cb = make_grounding_verify_callback(self.verifier)
        controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader,
            verify_callback=verify_cb
        )
        res = await controller.run("What is TCP?")
        self.assertTrue(res["success"])
        self.assertIn("TCP", res["answer"])
        self.assertFalse(res["rag_used"])

if __name__ == "__main__":
    unittest.main()
