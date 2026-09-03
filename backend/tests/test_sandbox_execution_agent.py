import os
import shutil
import unittest
import tempfile
import asyncio
from unittest.mock import MagicMock, AsyncMock

from backend.tools.code_sandbox.sandbox import SubprocessSandbox
from backend.agents.controller.agent import AgentController, AgentPlan, AgentStep
from backend.security.database import init_db, get_db_path
import sqlite3

class TestSandboxExecutionAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["AEGIS_DB_PATH"] = ":memory:"
        init_db()

    def setUp(self):
        self.temp_runs = tempfile.mkdtemp(prefix="test_sandbox_runs_")
        self.temp_artifacts = tempfile.mkdtemp(prefix="test_sandbox_artifacts_")
        self.sandbox = SubprocessSandbox(
            workspace_parent=self.temp_runs,
            artifacts_storage=self.temp_artifacts
        )

    def tearDown(self):
        shutil.rmtree(self.temp_runs, ignore_errors=True)
        shutil.rmtree(self.temp_artifacts, ignore_errors=True)

    def test_01_factorial_calculation_real_execution(self):
        code = (
            "import math\n"
            "res = math.factorial(20)\n"
            "print(res)\n"
        )
        res = self.sandbox.execute(code, timeout_seconds=5.0)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["stdout"].strip(), "2432902008176640000")
        self.assertEqual(res["stderr"], "")
        self.assertFalse(res["timed_out"])
        self.assertIsInstance(res["duration_ms"], int)

    def test_02_intentional_failure_and_real_stderr(self):
        code = (
            "def calculate():\n"
            "    raise ValueError('CRITICAL_CALCULATION_FAULT')\n"
            "calculate()\n"
        )
        res = self.sandbox.execute(code, timeout_seconds=5.0)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "FAILED")
        self.assertNotEqual(res["exit_code"], 0)
        self.assertIn("CRITICAL_CALCULATION_FAULT", res["stderr"])

    def test_03_file_input_and_artifact_generation(self):
        input_csv = "part,quantity\nvalve_a,10\nvalve_b,25\n"
        code = (
            "import csv\n"
            "total = 0\n"
            "with open('inventory.csv', 'r') as f:\n"
            "    reader = csv.DictReader(f)\n"
            "    for row in reader:\n"
            "        total += int(row['quantity'])\n"
            "with open('summary.csv', 'w') as out:\n"
            "    out.write(f'total,{total}\\n')\n"
            "print(f'TOTAL:{total}')\n"
        )
        res = self.sandbox.execute(
            code=code,
            files={"inventory.csv": input_csv},
            user_id=1,
            username="admin"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["stdout"].strip(), "TOTAL:35")
        self.assertEqual(len(res["artifacts"]), 1)
        art = res["artifacts"][0]
        self.assertEqual(art["filename"], "summary.csv")
        self.assertIn("download_url", art)
        
        # Verify recorded in SQLite database
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename, file_size, user_id FROM sandbox_artifacts WHERE id = ?", (art["id"],))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "summary.csv")
        self.assertEqual(row[2], 1)

    def test_04_path_traversal_blocked(self):
        res = self.sandbox.execute(
            code="print(1)",
            files={"../escape.txt": "evil content"}
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("path traversal blocked", res["stderr"])

    def test_05_network_access_blocked(self):
        # 1. AST check blocks import socket
        code_ast = "import socket\ns = socket.socket()\n"
        res_ast = self.sandbox.execute(code_ast)
        self.assertFalse(res_ast["success"])
        self.assertIn("Forbidden module import detected", res_ast["stderr"])

        # 2. Subprocess check blocks subprocess
        code_sub = "import subprocess\nsubprocess.run(['ls'])\n"
        res_sub = self.sandbox.execute(code_sub)
        self.assertFalse(res_sub["success"])
        self.assertIn("Forbidden module import detected", res_sub["stderr"])

    def test_06_agent_controller_coding_end_to_end(self):
        mock_loader = MagicMock()
        mock_loader.current_model_id = "qwen2.5-coder:7b"
        mock_loader.is_model_loaded.return_value = True
        
        # Mock LLM returning valid factorial python code
        mock_loader.generate = AsyncMock(return_value="```python\nimport math\nprint(math.factorial(20))\n```")

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=MagicMock(
            task_type="CODING",
            selected_model="qwen2.5-coder:7b",
            runtime_model_name="qwen2.5-coder:7b",
            required_capabilities=["coding"],
            matched_capabilities=["coding"],
            reason="Routed to qwen2.5-coder:7b for coding",
            switched=False,
            to_dict=lambda: {"task_type": "CODING", "selected_model": "qwen2.5-coder:7b", "switched": False}
        ))

        mock_registry = MagicMock()
        mock_registry.get_profile.return_value = {
            "model_id": "qwen2.5-coder:7b",
            "runtime_model_name": "qwen2.5-coder:7b",
            "capabilities": ["coding"]
        }

        controller = AgentController(
            registry_manager=mock_registry,
            loader_manager=mock_loader,
            sandbox_service=self.sandbox,
            model_router=mock_router,
            max_steps=5,
            max_replans=2
        )

        user_prompt = "Write a Python program to calculate factorial of 20, execute it in the sandbox, and show the actual output."
        res = asyncio.run(controller.run(user_prompt))

        self.assertTrue(res["success"])
        self.assertIsNotNone(res["sandbox_execution"])
        self.assertEqual(res["sandbox_execution"]["status"], "SUCCESS")
        self.assertEqual(res["sandbox_execution"]["exit_code"], 0)
        self.assertEqual(res["sandbox_execution"]["stdout"].strip(), "2432902008176640000")
        self.assertIn("2432902008176640000", res["answer"])
        self.assertNotIn("print(0)", res["answer"])

    def test_07_agentic_error_feedback_replan_loop(self):
        mock_loader = MagicMock()
        mock_loader.current_model_id = "qwen2.5-coder:7b"
        mock_loader.is_model_loaded.return_value = True

        # First call produces failing code (ZeroDivisionError), second call (replan) produces fixed code
        mock_loader.generate = AsyncMock(side_effect=[
            "```python\n# Broken script\nprint(10 / 0)\n```",
            "```python\n# Fixed script\nprint(10 / 2)\n```"
        ])

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=MagicMock(
            task_type="CODING",
            selected_model="qwen2.5-coder:7b",
            runtime_model_name="qwen2.5-coder:7b",
            required_capabilities=["coding"],
            matched_capabilities=["coding"],
            reason="Routed to qwen2.5-coder:7b for coding",
            switched=False,
            to_dict=lambda: {"task_type": "CODING", "selected_model": "qwen2.5-coder:7b", "switched": False}
        ))

        mock_registry = MagicMock()
        mock_registry.get_profile.return_value = {
            "model_id": "qwen2.5-coder:7b",
            "runtime_model_name": "qwen2.5-coder:7b",
            "capabilities": ["coding"]
        }

        controller = AgentController(
            registry_manager=mock_registry,
            loader_manager=mock_loader,
            sandbox_service=self.sandbox,
            model_router=mock_router,
            max_steps=10,
            max_replans=3
        )

        user_prompt = "Calculate division of 10 by 2 in sandbox."
        res = asyncio.run(controller.run(user_prompt))

        self.assertTrue(res["success"])
        self.assertIsNotNone(res["sandbox_execution"])
        self.assertEqual(res["sandbox_execution"]["status"], "SUCCESS")
        self.assertEqual(res["sandbox_execution"]["exit_code"], 0)
        self.assertEqual(res["sandbox_execution"]["stdout"].strip(), "5.0")
        # Verify that generate was called twice (initial + error replan)
        self.assertEqual(mock_loader.generate.call_count, 2)
        # Verify the prompt passed in the second call contains the error feedback
        second_call_kwargs = mock_loader.generate.call_args_list[1].kwargs
        second_call_prompt = second_call_kwargs.get("prompt", "")
        self.assertIn("ZeroDivisionError", second_call_prompt)

    def test_08_multi_tenant_artifact_isolation(self):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        from backend.security.auth import create_access_token, hash_password

        # Seed test users into SQLite
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (id, username, password_hash, role, is_active) VALUES (?, ?, ?, ?, 1)",
            (1, "admin", hash_password("AdminPassword123!"), "admin")
        )
        cursor.execute(
            "INSERT OR REPLACE INTO users (id, username, password_hash, role, is_active) VALUES (?, ?, ?, ?, 1)",
            (10, "alice", hash_password("AlicePassword123!"), "user")
        )
        cursor.execute(
            "INSERT OR REPLACE INTO users (id, username, password_hash, role, is_active) VALUES (?, ?, ?, ?, 1)",
            (20, "bob", hash_password("BobPassword123!"), "user")
        )
        conn.commit()
        conn.close()

        import backend.app.main as main_module
        main_module.sandbox_service = self.sandbox

        client = TestClient(app)

        # Create artifact owned by user 10 ("alice")
        res = self.sandbox.execute(
            code="with open('report.txt', 'w') as f:\n    f.write('confidential data')\nprint('done')",
            user_id=10,
            username="alice"
        )
        self.assertTrue(res["success"])
        self.assertEqual(len(res["artifacts"]), 1)
        art_id = res["artifacts"][0]["id"]

        token_bob = create_access_token(subject="bob", role="user")
        token_alice = create_access_token(subject="alice", role="user")
        token_admin = create_access_token(subject="admin", role="admin")

        # Bob (user 20) attempting to download Alice's artifact -> 403 Forbidden
        bob_resp = client.get(
            f"/sandbox/artifacts/{art_id}/download",
            headers={"Authorization": f"Bearer {token_bob}"}
        )
        self.assertEqual(bob_resp.status_code, 403)

        # Alice (user 10, owner) downloading -> 200 OK
        alice_resp = client.get(
            f"/sandbox/artifacts/{art_id}/download",
            headers={"Authorization": f"Bearer {token_alice}"}
        )
        self.assertEqual(alice_resp.status_code, 200)
        self.assertEqual(alice_resp.text, "confidential data")

        # Admin downloading -> 200 OK
        admin_resp = client.get(
            f"/sandbox/artifacts/{art_id}/download",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(admin_resp.status_code, 200)
        self.assertEqual(admin_resp.text, "confidential data")

if __name__ == "__main__":
    unittest.main()
