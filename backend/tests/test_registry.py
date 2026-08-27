import unittest
import os
import tempfile
import json
from backend.models.registry.manager import (
    ModelRegistryManager,
    RegistryFileNotFoundError,
    InvalidRegistryJsonError,
    MalformedModelEntryError,
    DuplicateModelIdError,
    ModelNotFoundError,
    InvalidCapabilityQueryError
)

class TestModelRegistryManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Path to actual registry file
        cls.actual_registry_path = "backend/models/registry/registry.json"

    def test_actual_registry_loads(self):
        """Verify the actual registry.json loads and parses without validation errors."""
        manager = ModelRegistryManager(self.actual_registry_path)
        models = manager.get_all_models(include_disabled=True)
        self.assertGreater(len(models), 0)
        
        # Verify model IDs are unique
        model_ids = [m["model_id"] for m in models]
        self.assertEqual(len(model_ids), len(set(model_ids)), "Model IDs in registry.json must be unique.")

    def test_get_model_by_id(self):
        """Verify model profiles can be fetched using valid IDs, and fail on invalid IDs."""
        manager = ModelRegistryManager(self.actual_registry_path)
        
        # Get first configured model
        all_models = manager.get_all_models()
        first_id = all_models[0]["model_id"]
        
        model = manager.get_model(first_id)
        self.assertEqual(model["model_id"], first_id)

        # Query unknown ID
        with self.assertRaises(ModelNotFoundError):
            manager.get_model("unknown-model-signature")

    def test_capability_filtering(self):
        """Verify models can be correctly retrieved by capability."""
        manager = ModelRegistryManager(self.actual_registry_path)
        
        # Query coding capability
        coding_models = manager.get_models_by_capability("coding")
        for m in coding_models:
            self.assertIn("coding", m["capabilities"])

        # Query invalid capability
        with self.assertRaises(InvalidCapabilityQueryError):
            manager.get_models_by_capability("invalid-capability-name")

    def test_disabled_filtering(self):
        """Verify disabled models are excluded or included based on arguments."""
        # Create a temp file containing a disabled model
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "test_disabled_registry.json")
        
        registry_data = {
            "models": [
                {
                    "model_id": "active-model",
                    "display_name": "Active Model",
                    "runtime_model_name": "test-active-tag",
                    "provider": "Test",
                    "runtime": "ollama",
                    "capabilities": ["coding"],
                    "model_type": "coding",
                    "context_length": 2048,
                    "quantization": "None",
                    "estimated_vram_gb": 1.0,
                    "estimated_ram_gb": 2.0,
                    "priority": 1,
                    "enabled": True,
                    "requires_gpu": False,
                    "supports_cpu": True,
                    "supports_vision": False,
                    "supports_code": True,
                    "supports_text": False,
                    "status": "configured"
                },
                {
                    "model_id": "disabled-model",
                    "display_name": "Disabled Model",
                    "runtime_model_name": "test-disabled-tag",
                    "provider": "Test",
                    "runtime": "ollama",
                    "capabilities": ["coding"],
                    "model_type": "coding",
                    "context_length": 2048,
                    "quantization": "None",
                    "estimated_vram_gb": 1.0,
                    "estimated_ram_gb": 2.0,
                    "priority": 1,
                    "enabled": False,
                    "requires_gpu": False,
                    "supports_cpu": True,
                    "supports_vision": False,
                    "supports_code": True,
                    "supports_text": False,
                    "status": "configured"
                }
            ]
        }
        
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(registry_data, f)
            
        try:
            manager = ModelRegistryManager(temp_path)
            
            # Excludes disabled by default
            enabled_only = manager.get_all_models()
            self.assertEqual(len(enabled_only), 1)
            self.assertEqual(enabled_only[0]["model_id"], "active-model")
            
            # Includes disabled when requested
            all_models = manager.get_all_models(include_disabled=True)
            self.assertEqual(len(all_models), 2)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_missing_registry_file(self):
        """Verify RegistryFileNotFoundError is raised when file path is invalid."""
        with self.assertRaises(RegistryFileNotFoundError):
            ModelRegistryManager("nonexistent_registry_file_path.json")

    def test_invalid_json_formatting(self):
        """Verify InvalidRegistryJsonError is raised when file contains malformed JSON text."""
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "test_invalid_json.json")
        
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write("{ malformed json structure }")
            
        try:
            with self.assertRaises(InvalidRegistryJsonError):
                ModelRegistryManager(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_duplicate_model_ids(self):
        """Verify DuplicateModelIdError is raised when multiple models share the same model_id."""
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "test_duplicate_ids.json")
        
        model_profile = {
            "model_id": "duplicate-id",
            "display_name": "Test Model",
            "runtime_model_name": "test-duplicate-tag",
            "provider": "Test",
            "runtime": "ollama",
            "capabilities": ["coding"],
            "model_type": "coding",
            "context_length": 2048,
            "quantization": "None",
            "estimated_vram_gb": 1.0,
            "estimated_ram_gb": 2.0,
            "priority": 1,
            "enabled": True,
            "requires_gpu": False,
            "supports_cpu": True,
            "supports_vision": False,
            "supports_code": True,
            "supports_text": False,
            "status": "configured"
        }
        
        registry_data = {
            "models": [model_profile, model_profile]
        }
        
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(registry_data, f)
            
        try:
            with self.assertRaises(DuplicateModelIdError):
                ModelRegistryManager(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_malformed_model_profile(self):
        """Verify MalformedModelEntryError is raised when required profile keys are missing."""
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "test_malformed.json")
        
        registry_data = {
            "models": [
                {
                    "model_id": "malformed-model",
                    "display_name": "Malformed Model"
                    # missing all other required fields
                }
            ]
        }
        
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(registry_data, f)
            
        try:
            with self.assertRaises(MalformedModelEntryError):
                ModelRegistryManager(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
