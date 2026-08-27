import os
import json
from typing import List, Dict, Any

class ModelRegistryError(Exception):
    """Base exception for all model registry errors."""
    pass

class RegistryFileNotFoundError(ModelRegistryError):
    """Raised when the registry JSON file is missing from disk."""
    pass

class InvalidRegistryJsonError(ModelRegistryError):
    """Raised when the registry file fails JSON syntax decoding."""
    pass

class MalformedModelEntryError(ModelRegistryError):
    """Raised when a model profile lacks required keys or uses malformed data types."""
    pass

class DuplicateModelIdError(ModelRegistryError):
    """Raised when the registry contains non-unique model_id values."""
    pass

class ModelNotFoundError(ModelRegistryError):
    """Raised when a requested model_id is not found in the registry."""
    pass

class InvalidCapabilityQueryError(ModelRegistryError):
    """Raised when querying the registry using a capability not in the taxonomy."""
    pass

# Mandatory keys required in each model profile schema
REQUIRED_FIELDS = [
    "model_id", "display_name", "runtime_model_name", "provider", "runtime", "capabilities",
    "model_type", "context_length", "quantization", "estimated_vram_gb",
    "estimated_ram_gb", "priority", "enabled", "requires_gpu",
    "supports_cpu", "supports_vision", "supports_code", "supports_text",
    "status"
]

# Authorized task capability vocabulary
VALID_CAPABILITIES = {
    "text_generation", "reasoning", "coding", "vision", "multimodal"
}

class ModelRegistryManager:
    """Manages parsing, validation, retrieval and filtering of local open-weight model profiles."""
    
    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._models: Dict[str, Dict[str, Any]] = {}
        self.load_registry()

    def load_registry(self) -> None:
        """Loads and validates the registry schema configurations from local disk."""
        if not os.path.exists(self.registry_path):
            raise RegistryFileNotFoundError("Registry configuration file was not found on local disk.")

        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            raise InvalidRegistryJsonError("Failed to parse registry file. Invalid JSON syntax.")

        if not isinstance(data, dict) or "models" not in data or not isinstance(data["models"], list):
            raise MalformedModelEntryError("Registry database root must be a JSON object containing a 'models' list.")

        self._models = {}
        for entry in data["models"]:
            if not isinstance(entry, dict):
                raise MalformedModelEntryError("Each configured model profile must be a valid JSON object entry.")

            # Validate presence of required keys
            for field in REQUIRED_FIELDS:
                if field not in entry:
                    raise MalformedModelEntryError(f"Model profile entry is missing required configuration field: '{field}'")

            model_id = entry["model_id"]
            if not isinstance(model_id, str) or not model_id.strip():
                raise MalformedModelEntryError("Model 'model_id' must be a non-empty string.")

            if model_id in self._models:
                raise DuplicateModelIdError(f"Non-unique model_id conflict detected in registry database: '{model_id}'")

            # Validate capability taxonomy entries
            caps = entry["capabilities"]
            if not isinstance(caps, list):
                raise MalformedModelEntryError(f"Capabilities list for model ID '{model_id}' must be a JSON array.")
            
            for cap in caps:
                if not isinstance(cap, str) or cap not in VALID_CAPABILITIES:
                    raise MalformedModelEntryError(
                        f"Model ID '{model_id}' declares invalid capability query key: '{cap}'. "
                        f"Allowed taxonomy: {list(VALID_CAPABILITIES)}"
                    )

            self._models[model_id] = entry

    def get_all_models(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """Retrieves list of all registered model profiles."""
        return [
            model for model in self._models.values()
            if include_disabled or model["enabled"]
        ]

    def get_model(self, model_id: str) -> Dict[str, Any]:
        """Retrieves a specific model profile using its unique model_id configuration key."""
        if model_id not in self._models:
            raise ModelNotFoundError(f"Model profile with configuration ID '{model_id}' was not found.")
        return self._models[model_id]

    def get_models_by_capability(self, capability: str, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """Filters registered model profiles by task capability type."""
        if capability not in VALID_CAPABILITIES:
            raise InvalidCapabilityQueryError(
                f"Requested filter contains invalid capability query key: '{capability}'. "
                f"Allowed taxonomy: {list(VALID_CAPABILITIES)}"
            )

        return [
            model for model in self._models.values()
            if (include_disabled or model["enabled"]) and capability in model["capabilities"]
        ]
