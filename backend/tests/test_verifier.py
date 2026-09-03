import os
import unittest
import logging
from unittest.mock import MagicMock, patch
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.agents.controller.agent import AgentController, AgentStep, AgentPlan
from backend.app.verification.verifier import (
    GroundingVerifier,
    VerificationEvidence,
    VerificationResult,
    make_grounding_verify_callback
)

class TestAegisVerifier(unittest.IsolatedAsyncioTestCase):
    """Unit tests and integration checks for the output verification grounding engine."""
    
    def setUp(self):
        self.safe_dir = os.path.abspath("outputs")
        self.verifier = GroundingVerifier(safe_directories=[self.safe_dir], min_pass_score=0.7)
        
        # Mock RAG results
        self.valid_rag_results = [
            {
                "text": "Pressure limit for check valve V-101 is capped at 150 PSI during refinery shutdown protocols.",
                "metadata": {
                    "filename": "shutdown_rules.pdf",
                    "page_number": 3,
                    "chunk_id": "rule_c3",
                    "source_path": os.path.join(self.safe_dir, "documents", "shutdown_rules.pdf")
                }
            }
        ]
        
        self.output_with_valid_citation = (
            "The pressure limit for valve V-101 is 150 PSI. "
            "[source: shutdown_rules.pdf, page: 3, chunk: rule_c3]"
        )

    def test_printed_citation_parsing(self):
        """5. Verify the verifier extracts structured citation coordinates correctly across formats."""
        citations = self.verifier.parse_citations(self.output_with_valid_citation)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["source"], "shutdown_rules.pdf")
        self.assertEqual(citations[0]["page"], 3)
        self.assertEqual(citations[0]["chunk_id"], "rule_c3")

        # Test pipe-separated format: [Source: file.pdf | Page 3]
        pipe_citations = self.verifier.parse_citations("According to specs [Source: shutdown_rules.pdf | Page 3].")
        self.assertEqual(len(pipe_citations), 1)
        self.assertEqual(pipe_citations[0]["source"], "shutdown_rules.pdf")
        self.assertEqual(pipe_citations[0]["page"], 3)

        # Test simple source format: [Source: shutdown_rules.pdf]
        simple_citations = self.verifier.parse_citations("According to specs [Source: shutdown_rules.pdf].")
        self.assertEqual(len(simple_citations), 1)
        self.assertEqual(simple_citations[0]["source"], "shutdown_rules.pdf")
        self.assertEqual(simple_citations[0]["page"], 1)

    def test_grounding_verification_success(self):
        """1, 5, 6, 8, 10. Verify successful grounding check when citations and overlap are valid."""
        res = self.verifier.verify(self.output_with_valid_citation, self.valid_rag_results)
        self.assertTrue(res.passed)
        self.assertGreaterEqual(res.score, 0.7)
        self.assertEqual(res.citation_count, 1)
        self.assertEqual(len(res.evidence), 1)

    def test_grounding_verification_pipe_format_success(self):
        """Verify pipe-formatted citation passes grounding verification."""
        pipe_out = "Pressure limit for check valve V-101 is capped at 150 PSI. [Source: shutdown_rules.pdf | Page 3]"
        res = self.verifier.verify(pipe_out, self.valid_rag_results)
        self.assertTrue(res.passed)
        self.assertGreaterEqual(res.score, 0.7)

    def test_honest_refusal_callback_pass(self):
        """Verify honest refusal when document has no info passes verification callback without retry failure."""
        verify_cb = make_grounding_verify_callback(self.verifier)
        step = AgentStep("s2", "generate answer", "text_generation", {"action": "generate_answer"})
        step.output = "The indexed organizational documents do not contain information to answer this question."
        plan = AgentPlan("What is the company cafeteria menu?")
        
        rag_step = AgentStep("s1", "rag search", "text_generation", {"action": "rag_search"})
        rag_step.output = self.valid_rag_results
        plan.steps = [rag_step, step]
        plan.current_step_index = 1
        
        passed = verify_cb(plan, step)
        self.assertTrue(passed)
        self.assertIn("Honest ungrounded notice", step.verification_result)

    def test_missing_evidence(self):
        """2. Verify grounding fails when no vector evidence context is provided."""
        res = self.verifier.verify(self.output_with_valid_citation, [])
        self.assertFalse(res.passed)
        self.assertEqual(res.score, 0.2)  # only presence score (0.2) + overlap (0.0) + validity (0.0) = 0.2
        self.assertIn("No grounding evidence", res.reasons[0])

    def test_invalid_citation_format(self):
        """3. Verify malformed citations are ignored and result in grounding failures."""
        output = "The pressure limit is 150 PSI. [source shutdown_rules.pdf, page 3]"
        res = self.verifier.verify(output, self.valid_rag_results)
        self.assertFalse(res.passed)
        self.assertEqual(res.citation_count, 0)
        self.assertTrue(any("does not contain any bracket source citations" in r for r in res.reasons))

    def test_citation_to_unavailable_source(self):
        """4. Verify citations to unretrieved document sources fail grounding audits."""
        output = "The pressure limit is 150 PSI. [source: other_rules.pdf, page: 1, chunk: other_c1]"
        res = self.verifier.verify(output, self.valid_rag_results)
        self.assertFalse(res.passed)
        self.assertEqual(res.citation_count, 1)
        self.assertEqual(len(res.missing_evidence), 1)
        self.assertIn("[other_rules.pdf:1:other_c1]", res.missing_evidence)

    def test_low_text_overlap(self):
        """7. Verify low token overlap results in verification failure."""
        strict_verifier = GroundingVerifier(safe_directories=[self.safe_dir], min_pass_score=0.8)
        output = "The computer motherboard has twelve copper pins. [source: shutdown_rules.pdf, page: 3, chunk: rule_c3]"
        res = strict_verifier.verify(output, self.valid_rag_results)
        self.assertFalse(res.passed)
        self.assertTrue(any("low word overlap" in r for r in res.reasons))

    def test_verification_score_threshold(self):
        """9. Verify min_pass_score thresholds toggle passed status."""
        # With default 0.7 threshold: passes
        res_default = self.verifier.verify(self.output_with_valid_citation, self.valid_rag_results)
        self.assertTrue(res_default.passed)
        
        # Set strict threshold to 0.95: fails
        strict_verifier = GroundingVerifier(safe_directories=[self.safe_dir], min_pass_score=0.95)
        res_strict = strict_verifier.verify(self.output_with_valid_citation, self.valid_rag_results)
        self.assertFalse(res_strict.passed)

    def test_malformed_evidence_handling(self):
        """11. Verify verifier handles missing keys in RAG metadata collections gracefully."""
        malformed = [{"text": "Pressure limit", "metadata": {}}] # empty metadata dictionary
        res = self.verifier.verify(self.output_with_valid_citation, malformed)
        self.assertFalse(res.passed)

    def test_unsafe_path_traversal_evidence(self):
        """12. Verify directory traversal attempts in metadata paths fail immediately with score 0."""
        unsafe_results = [
            {
                "text": "Secret content",
                "metadata": {
                    "filename": "secret.txt",
                    "page_number": 1,
                    "chunk_id": "sec_c1",
                    "source_path": os.path.abspath(os.path.join(self.safe_dir, "..", "..", "private_system_env.env"))
                }
            }
        ]
        res = self.verifier.verify(self.output_with_valid_citation, unsafe_results)
        self.assertFalse(res.passed)
        self.assertEqual(res.score, 0.0)
        self.assertIn("Security violation", res.reasons[0])

    def test_no_confidential_payload_logged(self):
        """13. Verify logged logs do not capture actual prompts or retrieved text."""
        logger_target = logging.getLogger("aegis.verifier")
        with self.assertLogs(logger_target, level='INFO') as log_capture:
            self.verifier.verify("SECRET_ANSWER [source: file.pdf, page: 1, chunk: c1]", self.valid_rag_results)
            
            combined_logs = "\n".join(log_capture.output)
            self.assertIn("Score=", combined_logs)
            self.assertIn("Passed=", combined_logs)
            self.assertNotIn("SECRET_ANSWER", combined_logs)
            self.assertNotIn("V-101 is capped at 150 PSI", combined_logs)

    async def test_agent_controller_verification_integration_pass(self):
        """14. Verify successful verifier integration inside the AgentController loop."""
        # 1. Setup mocks
        registry = ModelRegistryManager("backend/models/registry/registry.json")
        mock_loader = MagicMock(spec=ModelLoaderManager)
        mock_loader.base_url = "http://localhost:11434"
        mock_loader.switch_model.return_value = {"status": "success"}
        
        mock_rag = MagicMock()
        mock_rag.search.return_value = self.valid_rag_results
        
        # Instantiate controller with grounding callback
        verify_cb = make_grounding_verify_callback(self.verifier)
        controller = AgentController(
            registry_manager=registry,
            loader_manager=mock_loader,
            rag_service=mock_rag,
            verify_callback=verify_cb,
            max_steps=5,
            max_replans=2
        )
        
        # Override _call_llm inside run to return a valid grounded citation answer
        with patch.object(AgentController, '_call_llm', return_value=self.output_with_valid_citation):
            res = await controller.run("search company manual about fire safety")
            
        self.assertTrue(res["success"])
        self.assertEqual(res["plan"]["status"], "COMPLETED")
        self.assertIn("PASS (Score:", res["plan"]["steps"][1]["verification_result"])

    async def test_agent_controller_verification_failure_triggers_replan(self):
        """15, 16, 17, 18. Verify grounding failures trigger retry loops up to limit threshold."""
        registry = ModelRegistryManager("backend/models/registry/registry.json")
        mock_loader = MagicMock(spec=ModelLoaderManager)
        mock_loader.base_url = "http://localhost:11434"
        mock_loader.switch_model.return_value = {"status": "success"}
        
        mock_rag = MagicMock()
        mock_rag.search.return_value = self.valid_rag_results
        
        # Verifier runs on LLM responses. Mock LLM to output ungrounded texts (missing citation)
        ungrounded_output = "The pressure limit is 150 PSI."
        
        verify_cb = make_grounding_verify_callback(self.verifier)
        controller = AgentController(
            registry_manager=registry,
            loader_manager=mock_loader,
            rag_service=mock_rag,
            verify_callback=verify_cb,
            max_steps=10,  # Ensure steps limit does not block first
            max_replans=2
        )
        
        with patch.object(AgentController, '_call_llm', return_value=ungrounded_output):
            res = await controller.run("search company manual about fire safety")
            
        # Should fail after retry limit (max_replans = 2) is exceeded
        self.assertFalse(res["success"])
        self.assertEqual(res["plan"]["status"], "FAILED")
        
        # Plan steps layout: step_1 (RAG search), step_2 (generate, failed verification, REPLAN status),
        # step_2_retry_1 (failed verification, REPLAN status), step_2_retry_2 (failed verification, FAILED status)
        self.assertEqual(len(res["plan"]["steps"]), 4)
        self.assertEqual(res["plan"]["steps"][-1]["status"], "FAILED")
        self.assertIn("FAIL (Score:", res["plan"]["steps"][-1]["verification_result"])

    async def test_no_infinite_verification_loop(self):
        """18. Verify that execution terminates and does not loop infinitely under continuous verification failure."""
        registry = ModelRegistryManager("backend/models/registry/registry.json")
        mock_loader = MagicMock(spec=ModelLoaderManager)
        mock_loader.base_url = "http://localhost:11434"
        mock_loader.switch_model.return_value = {"status": "success"}
        
        mock_rag = MagicMock()
        mock_rag.search.return_value = self.valid_rag_results
        
        # Verify callback always returns False
        verify_cb = lambda plan, step: False
        
        controller = AgentController(
            registry_manager=registry,
            loader_manager=mock_loader,
            rag_service=mock_rag,
            verify_callback=verify_cb,
            max_steps=3,  # strict steps limit
            max_replans=100  # large budget to test steps limit cutoff
        )
        
        with patch.object(AgentController, '_call_llm', return_value="Ungrounded answer text."):
            res = await controller.run("search company manual about fire safety")
            
        self.assertFalse(res["success"])
        self.assertEqual(res["plan"]["status"], "FAILED")
        self.assertIn("steps limit exceeded", res["error"])

if __name__ == "__main__":
    unittest.main()
