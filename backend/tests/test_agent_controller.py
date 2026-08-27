import unittest
from unittest.mock import MagicMock, patch
import logging
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.agents.controller.agent import AgentController, AgentStep, AgentPlan

class TestAgentController(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the AEGIS Multi-Step Agent Planner and Controller orchestration loop."""
    
    async def asyncSetUp(self):
        self.registry_path = "backend/models/registry/registry.json"
        self.registry = ModelRegistryManager(self.registry_path)
        
        # Mock loader manager to prevent HTTP calls to localhost Ollama daemon
        self.mock_loader = MagicMock(spec=ModelLoaderManager)
        self.mock_loader.base_url = "http://localhost:11434"
        self.mock_loader.switch_model.return_value = {"status": "success"}

        # Mock tools
        self.mock_sandbox = MagicMock()
        self.mock_rag = MagicMock()
        self.mock_ocr = MagicMock()
        
        # Instantiate controller targeting mock systems
        self.controller = AgentController(
            registry_manager=self.registry,
            loader_manager=self.mock_loader,
            ocr_service=self.mock_ocr,
            rag_service=self.mock_rag,
            sandbox_service=self.mock_sandbox,
            max_steps=5,
            max_replans=2
        )

    def test_capability_classification(self):
        """Verify keyword classification maps user prompts to appropriate capabilities."""
        self.assertEqual(self.controller._classify_capability("write python code to sum arrays"), "coding")
        self.assertEqual(self.controller._classify_capability("analyze scanned document layout"), "vision")
        self.assertEqual(self.controller._classify_capability("search company manual for standards"), "text_generation")
        self.assertEqual(self.controller._classify_capability("summarize index keys"), "reasoning")

    def test_plan_creation(self):
        """Verify planning logic compiles a sequential multi-step sequence."""
        plan = self.controller._create_plan("write python code to sum arrays")
        self.assertEqual(plan.request, "write python code to sum arrays")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].capability, "coding")
        self.assertEqual(plan.steps[0].input.get("action"), "generate_code")
        self.assertEqual(plan.steps[1].capability, "coding")
        self.assertEqual(plan.steps[1].input.get("action"), "execute_code")

    async def test_successful_execution_coding(self):
        """Verify code generation and sandbox execution runs sequentially to completion."""
        self.mock_sandbox.execute.return_value = {"success": True, "stdout": "42", "stderr": "", "error": None}
        
        res = await self.controller.run("write python code to sum arrays")
        
        self.assertTrue(res["success"])
        self.assertEqual(res["plan"]["status"], "COMPLETED")
        self.assertEqual(self.mock_sandbox.execute.call_count, 1)
        self.mock_loader.switch_model.assert_any_call("qwen2.5-coder-1.5b-instruct")

    async def test_verification_callback_fail_triggers_replan(self):
        """Verify step verification failures trigger dynamic replan retry steps."""
        self.mock_sandbox.execute.return_value = {"success": True, "stdout": "42", "stderr": "", "error": None}
        
        # Verify callback fails the first step execution run, then passes the next retry step run
        call_count = 0
        def verify_fn(step: AgentStep) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count > 1
            
        self.controller.verify_callback = verify_fn
        
        res = await self.controller.run("write python code to sum arrays")
        self.assertTrue(res["success"])
        plan_dict = res["plan"]
        
        # Plan should hold: step_1 (COMPLETED), step_2        # Step 1 failed verification and triggered a retry step, which passed verification
        self.assertEqual(len(plan_dict["steps"]), 3)
        self.assertEqual(plan_dict["steps"][0]["status"], "REPLAN")
        self.assertEqual(plan_dict["steps"][0]["verification_result"], "FAIL")
        self.assertEqual(plan_dict["steps"][1]["status"], "COMPLETED")
        self.assertEqual(plan_dict["steps"][1]["verification_result"], "PASS")
        self.assertEqual(plan_dict["steps"][2]["status"], "COMPLETED")

    async def test_replan_limit_exceeded(self):
        """Verify executing fails when retry/replan budget is exceeded."""
        self.mock_sandbox.execute.return_value = {"success": False, "stdout": "", "stderr": "SyntaxError", "error": "SyntaxError"}
        
        # Max replans is 2. Step 2 fails 3 times total (1 initial + 2 retries) and then halts.
        res = await self.controller.run("write python code to sum arrays")
        
        self.assertFalse(res["success"])
        self.assertEqual(res["plan"]["status"], "FAILED")
        self.assertEqual(len(res["plan"]["steps"]), 4)  # step_1, step_2, step_2_retry_1, step_2_retry_2
        self.assertEqual(res["plan"]["steps"][-1]["status"], "FAILED")

    async def test_max_steps_limit(self):
        """Verify maximum step limit prevents infinite loops and exits cleanly."""
        self.mock_sandbox.execute.return_value = {"success": False, "stdout": "", "stderr": "Error", "error": "Error"}
        
        # Limit steps to 2 execution cycles
        self.controller.max_steps = 2
        
        res = await self.controller.run("write python code to sum arrays")
        self.assertFalse(res["success"])
        self.assertEqual(res["plan"]["status"], "FAILED")
        self.assertIn("steps limit exceeded", res["error"])

    async def test_confidential_payload_not_logged(self):
        """Verify user confidential query parameters and execution outputs are excluded from logging."""
        self.mock_sandbox.execute.return_value = {"success": True, "stdout": "CONFIDENTIAL_DB_PASSWORD", "stderr": "", "error": None}
        
        logger_target = logging.getLogger("aegis.agent_controller")
        with self.assertLogs(logger_target, level='INFO') as log_capture:
            await self.controller.run("write python code containing CONFIDENTIAL_PLAINTEXT_PROMPT")
            
            combined_logs = "\n".join(log_capture.output)
            
            # Check metadata is correctly tracked
            self.assertIn("Capability=coding", combined_logs)
            self.assertIn("Status=COMPLETED", combined_logs)
            
            # Verify no secrets are leaked
            self.assertNotIn("CONFIDENTIAL_PLAINTEXT_PROMPT", combined_logs)
            self.assertNotIn("CONFIDENTIAL_DB_PASSWORD", combined_logs)

if __name__ == "__main__":
    unittest.main()
