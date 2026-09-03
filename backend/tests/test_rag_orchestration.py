import unittest
import asyncio
from unittest.mock import MagicMock
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.agents.controller.agent import AgentController, AgentPlan, AgentStep

class TestRagOrchestration(unittest.TestCase):
    def setUp(self):
        self.registry_manager = ModelRegistryManager("backend/models/registry/registry.json")
        self.loader_manager = ModelLoaderManager(self.registry_manager)
        
        # Async mock for switch_model to avoid network/daemon calls in test environment
        async def fake_switch_model(model_id):
            return True
        self.loader_manager.switch_model = fake_switch_model
        
        self.mock_rag_service = MagicMock()
        
        self.controller = AgentController(
            registry_manager=self.registry_manager,
            loader_manager=self.loader_manager,
            rag_service=self.mock_rag_service
        )

    def test_knowledge_question_invokes_rag(self):
        """Verify that a knowledge/document question triggers a RAG retrieval step without magic phrases."""
        knowledge_queries = [
            "What is our emergency shutdown procedure?",
            "According to the uploaded document, what are the safety requirements?",
            "Summarize the employee leave policy.",
            "What does the uploaded SIH document say about the architecture?",
            "Find information about access control in our documents."
        ]
        
        for query in knowledge_queries:
            plan = self.controller._create_plan(query)
            self.assertGreaterEqual(len(plan.steps), 2, f"Failed for query: {query}")
            self.assertEqual(plan.steps[0].input.get("action"), "rag_search")
            self.assertEqual(plan.steps[0].input.get("query"), query, "Actual user query must be forwarded to rag_search")
            self.assertEqual(plan.steps[1].input.get("action"), "generate_answer")

    def test_non_knowledge_coding_question_skips_rag(self):
        """Verify that coding and general non-knowledge questions do not invoke RAG retrieval."""
        non_knowledge_queries = [
            "Write a Python function to reverse a string.",
            "Calculate 25 * 4",
            "Explain what a Python list is."
        ]
        
        for query in non_knowledge_queries:
            plan = self.controller._create_plan(query)
            actions = [step.input.get("action") for step in plan.steps]
            self.assertNotIn("rag_search", actions, f"RAG should not be invoked for query: {query}")

    def test_actual_user_query_forwarded_to_retrieval(self):
        """Verify user's actual request string is passed to rag_search input."""
        request = "What is the policy regarding remote access?"
        plan = self.controller._create_plan(request)
        step_1 = plan.steps[0]
        self.assertEqual(step_1.input.get("query"), request)

    def test_empty_retrieval_handled_safely(self):
        """Verify empty retrieval returns clear state without fabricating facts."""
        async def run_test():
            plan = AgentPlan("What is the policy for hypothetical X?")
            step_1 = AgentStep("step_1", "RAG Lookup", "text_generation", {"action": "rag_search", "query": plan.request})
            step_1.output = [] # Empty retrieval
            
            step_2 = AgentStep("step_2", "Generate Answer", "text_generation", {"action": "generate_answer", "user_query": plan.request})
            
            plan.steps = [step_1, step_2]
            plan.current_step_index = 1
            
            success = await self.controller._execute_step(plan, step_2)
            self.assertTrue(success)
            self.assertTrue(
                any(msg in step_2.output for msg in [
                    "I could not find sufficient evidence",
                    "No relevant organizational knowledge"
                ])
            )

        asyncio.run(run_test())

    def test_retrieved_chunks_formatted_into_llm_prompt(self):
        """Verify retrieved chunks with document metadata are formatted into structured prompt."""
        async def run_test():
            plan = AgentPlan("What is the shutdown procedure?")
            step_1 = AgentStep("step_1", "RAG Lookup", "text_generation", {"action": "rag_search", "query": plan.request})
            step_1.output = [
                {
                    "chunk_id": "c1",
                    "text": "Press the red isolation switch immediately.",
                    "metadata": {"filename": "safety.pdf", "page_number": 3}
                }
            ]
            
            step_2 = AgentStep("step_2", "Generate Answer", "text_generation", {"action": "generate_answer", "user_query": plan.request})
            
            plan.steps = [step_1, step_2]
            plan.current_step_index = 1
            
            # Mock _call_llm to inspect prompt text
            received_prompts = []
            async def fake_call_llm(model_name, prompt):
                received_prompts.append(prompt)
                return "Grounded answer text."

            self.controller._call_llm = fake_call_llm
            success = await self.controller._execute_step(plan, step_2)
            
            self.assertTrue(success)
            self.assertEqual(len(received_prompts), 1)
            prompt = received_prompts[0]
            
            self.assertIn("SYSTEM INSTRUCTIONS:", prompt)
            self.assertIn("USER QUESTION:\nWhat is the shutdown procedure?", prompt)
            self.assertIn("RETRIEVED KNOWLEDGE:", prompt)
            self.assertIn("[Source: safety.pdf | Page 3]", prompt)
            self.assertIn("Press the red isolation switch immediately.", prompt)
            self.assertIn("Answer using the retrieved organizational context when available.", prompt)

        asyncio.run(run_test())

    def test_explicit_document_question_triggers_rag(self):
        """Verify that explicit document questions ('What does our internal document say about X?') trigger RAG."""
        queries = [
            "What does the uploaded PDF say about safety?",
            "What is described in our employee manual?"
        ]
        for q in queries:
            plan = self.controller._create_plan(q)
            self.assertEqual(plan.steps[0].input.get("action"), "rag_search")

    def test_rag_retrieval_failure_handled(self):
        """Verify that errors inside the RAG search step are handled gracefully."""
        self.mock_rag_service.search.side_effect = Exception("ChromaDB connection timeout")
        plan = self.controller._create_plan("What is the safety policy?")
        step_1 = plan.steps[0]
        asyncio.run(self.controller._execute_step(plan, step_1))
        self.assertEqual(step_1.status, "FAILED")
        self.assertIn("ChromaDB connection timeout", step_1.error)

    def test_no_hardcoded_magic_phrase_required(self):
        """Verify that RAG works for natural queries without requiring 'search company manual'."""
        plan = self.controller._create_plan("What are our workplace safety rules?")
        self.assertEqual(plan.steps[0].input.get("action"), "rag_search")
        self.assertEqual(plan.steps[0].input.get("query"), "What are our workplace safety rules?")

if __name__ == "__main__":
    unittest.main()
