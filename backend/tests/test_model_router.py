import os
import shutil
import tempfile
import sqlite3
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.config.settings import settings
from backend.security.database import init_db
from backend.security.auth import create_access_token
from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.models.router import (
    ModelRouter,
    TaskType,
    RoutingDecision,
    NoCompatibleModelError,
    InvalidModelIdError,
    classify_task_from_prompt,
    validate_model_id
)
from backend.app.main import app

class TestModelRouter(unittest.IsolatedAsyncioTestCase):
    """Automated verification suite for the AEGIS Model Capability Router."""

    @classmethod
    def setUpClass(cls):
        cls.orig_db_path = settings.AUTH_DB_PATH
        cls.test_dir = tempfile.mkdtemp(prefix="aegis_router_test_")
        cls.db_path = os.path.join(cls.test_dir, "test_router_auth.db")
        settings.AUTH_DB_PATH = cls.db_path
        init_db()

        # Provision test operator
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
            ("operator_router", "hash_pw", "user", 1)
        )
        cls.user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cls.token = create_access_token("operator_router", "user")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_DB_PATH = cls.orig_db_path
        init_db()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        # Mock ModelRegistryManager with diverse capability fixtures
        self.mock_registry = MagicMock(spec=ModelRegistryManager)
        self.mock_loader = MagicMock(spec=ModelLoaderManager)
        self.mock_loader.base_url = "http://127.0.0.1:11434"
        self.mock_loader.current_model_id = "gemma3:4b"
        self.mock_loader.get_current_model_id = AsyncMock(return_value="gemma3:4b")
        self.mock_loader.switch_model = AsyncMock(return_value={"status": "success", "model_id": "gemma3:4b"})

        # Configured models
        self.sample_models = [
            {
                "model_id": "gemma3:4b",
                "display_name": "Gemma 3 4B",
                "runtime_model_name": "gemma3:4b",
                "provider": "Google",
                "runtime": "LOCAL",
                "status": "ACTIVE",
                "is_installed": True,
                "is_active": True,
                "priority": 1,
                "size_bytes": 3338801804,
                "capabilities": ["text_generation", "reasoning", "coding", "vision"],
                "supports_vision": True,
                "supports_code": True,
                "supports_text": True
            },
            {
                "model_id": "qwen3:4b",
                "display_name": "Qwen 3 4B",
                "runtime_model_name": "qwen3:4b",
                "provider": "Alibaba",
                "runtime": "LOCAL",
                "status": "INSTALLED",
                "is_installed": True,
                "is_active": False,
                "priority": 2,
                "size_bytes": 2497293931,
                "capabilities": ["text_generation", "reasoning", "coding"],
                "supports_vision": False,
                "supports_code": True,
                "supports_text": True
            },
            {
                "model_id": "deepseek-coder:1.3b",
                "display_name": "DeepSeek Coder 1.3B",
                "runtime_model_name": "deepseek-coder:1.3b",
                "provider": "DeepSeek",
                "runtime": "LOCAL",
                "status": "INSTALLED",
                "is_installed": True,
                "is_active": False,
                "priority": 3,
                "size_bytes": 1400000000,
                "capabilities": ["coding", "tool_calling"],
                "supports_vision": False,
                "supports_code": True,
                "supports_text": False
            },
            {
                "model_id": "llava:7b",
                "display_name": "LLaVA 7B",
                "runtime_model_name": "llava:7b",
                "provider": "Local",
                "runtime": "LOCAL",
                "status": "INSTALLED",
                "is_installed": True,
                "is_active": False,
                "priority": 4,
                "size_bytes": 4500000000,
                "capabilities": ["vision", "text_generation"],
                "supports_vision": True,
                "supports_code": False,
                "supports_text": True
            }
        ]

        self.mock_loader.get_discovered_models = AsyncMock(return_value=self.sample_models)
        self.router = ModelRouter(self.mock_registry, self.mock_loader)

    async def test_01_text_task_routes_to_compatible_local_model(self):
        """1. Text / Document QA task routes to a text-capable model."""
        decision = await self.router.route(task_type=TaskType.DOCUMENT_QA)
        self.assertIn("text_generation", decision.required_capabilities)
        self.assertIn(decision.selected_model, ["gemma3:4b", "qwen3:4b", "llava:7b"])

    async def test_02_coding_task_routes_to_coding_model(self):
        """2. Coding / Calculation task selects coding-capable model."""
        decision = await self.router.route(task_type=TaskType.CODING)
        self.assertIn("coding", decision.required_capabilities)
        self.assertIn(decision.selected_model, ["gemma3:4b", "qwen3:4b", "deepseek-coder:1.3b"])

    async def test_03_vision_task_routes_to_vision_model(self):
        """3. Vision task routes strictly to vision-capable model."""
        decision = await self.router.route(task_type=TaskType.VISION_ANALYSIS)
        self.assertIn("vision", decision.required_capabilities)
        self.assertIn(decision.selected_model, ["gemma3:4b", "llava:7b"])
        self.assertNotEqual(decision.selected_model, "qwen3:4b")
        self.assertNotEqual(decision.selected_model, "deepseek-coder:1.3b")

    async def test_04_sticky_active_model_reuse(self):
        """4. Reuses currently active model if it satisfies task requirements (no unnecessary switch)."""
        self.mock_loader.current_model_id = "gemma3:4b"
        self.mock_loader.get_current_model_id = AsyncMock(return_value="gemma3:4b")

        decision = await self.router.route(task_type=TaskType.DOCUMENT_QA)
        self.assertEqual(decision.selected_model, "gemma3:4b")
        self.assertFalse(decision.switched)
        self.assertIn("Reusing currently active model", decision.reason)
        self.mock_loader.switch_model.assert_not_called()

    async def test_05_incompatible_active_model_triggers_switch(self):
        """5. Incompatible active model triggers switch to compatible installed model."""
        # Active model is qwen3:4b (no vision)
        self.mock_loader.current_model_id = "qwen3:4b"
        self.mock_loader.get_current_model_id = AsyncMock(return_value="qwen3:4b")

        decision = await self.router.route(task_type=TaskType.VISION_ANALYSIS)
        self.assertEqual(decision.selected_model, "gemma3:4b")
        self.assertTrue(decision.switched)
        self.mock_loader.switch_model.assert_called_once_with("gemma3:4b")

    async def test_06_no_compatible_model_returns_honest_error(self):
        """6. When no installed model satisfies required capabilities, raises NoCompatibleModelError."""
        # Set discovered models to only text model
        self.mock_loader.get_discovered_models = AsyncMock(return_value=[
            {
                "model_id": "text-only:2b",
                "runtime_model_name": "text-only:2b",
                "is_installed": True,
                "status": "INSTALLED",
                "capabilities": ["text_generation"]
            }
        ])

        with self.assertRaises(NoCompatibleModelError) as ctx:
            await self.router.route(task_type=TaskType.VISION_ANALYSIS)

        self.assertIn("No locally installed model satisfies", str(ctx.exception))

    async def test_07_uninstalled_model_is_never_selected(self):
        """7. Models with is_installed=False / UNAVAILABLE are excluded from candidate pool."""
        self.mock_loader.get_discovered_models = AsyncMock(return_value=[
            {
                "model_id": "ghost-coder:7b",
                "runtime_model_name": "ghost-coder:7b",
                "is_installed": False,
                "status": "UNAVAILABLE",
                "capabilities": ["coding"]
            },
            {
                "model_id": "installed-coder:1b",
                "runtime_model_name": "installed-coder:1b",
                "is_installed": True,
                "status": "INSTALLED",
                "capabilities": ["coding"]
            }
        ])

        decision = await self.router.route(task_type=TaskType.CODING)
        self.assertEqual(decision.selected_model, "installed-coder:1b")

    async def test_08_invalid_model_id_is_rejected_safely(self):
        """8. Malformed or path injection model IDs are rejected."""
        with self.assertRaises(InvalidModelIdError):
            validate_model_id("../../../etc/passwd")

        with self.assertRaises(InvalidModelIdError):
            validate_model_id("model; rm -rf /")

        with self.assertRaises(InvalidModelIdError):
            validate_model_id("https://external-cloud.com/model")

        # Valid IDs
        self.assertEqual(validate_model_id("gemma3:4b"), "gemma3:4b")
        self.assertEqual(validate_model_id("qwen3:4b"), "qwen3:4b")

    def test_09_task_classification_from_prompts(self):
        """9. Classifies user prompts deterministically into TaskType categories."""
        self.assertEqual(
            classify_task_from_prompt("What is the proposed solution in SIH2026ppt.pdf?"),
            TaskType.DOCUMENT_QA
        )
        self.assertEqual(
            classify_task_from_prompt("Summarize the entire document"),
            TaskType.DOCUMENT_SUMMARY
        )
        self.assertEqual(
            classify_task_from_prompt("Calculate the factorial of 10 using Python"),
            TaskType.CODING
        )
        self.assertEqual(
            classify_task_from_prompt("Calculate the compound interest for 5 years"),
            TaskType.CALCULATION
        )
        self.assertEqual(
            classify_task_from_prompt("Extract text from this scanned image of circuit diagram"),
            TaskType.VISION_ANALYSIS
        )
        self.assertEqual(
            classify_task_from_prompt("What is thermodynamics?"),
            TaskType.GENERAL_TEXT
        )

    def test_10_api_models_route_endpoint(self):
        """10. POST /models/route returns structured routing decision via REST API."""
        res = self.client.post(
            "/models/route",
            json={"task_type": "DOCUMENT_QA", "prompt": "What is in the document?"},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["task_type"], "DOCUMENT_QA")
        self.assertIn("selected_model", data)
        self.assertIn("required_capabilities", data)
        self.assertIn("text_generation", data["required_capabilities"])

if __name__ == "__main__":
    unittest.main()
