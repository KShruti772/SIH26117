import re
import logging
import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field

from backend.models.registry.manager import ModelRegistryManager, ModelRegistryError
from backend.models.loaders.manager import ModelLoaderManager, ModelLoaderError, RuntimeUnavailableError
from backend.security.audit import AuditLogger, get_request_id

logger = logging.getLogger("aegis.model_router")

class ModelRouterError(Exception):
    """Base exception for model routing failures."""
    pass

class NoCompatibleModelError(ModelRouterError):
    """Raised when no locally installed model satisfies the required capabilities."""
    pass

class InvalidModelIdError(ModelRouterError):
    """Raised when an untrusted or malformed model ID is supplied."""
    pass

class TaskType(str, Enum):
    DOCUMENT_QA = "DOCUMENT_QA"
    DOCUMENT_SUMMARY = "DOCUMENT_SUMMARY"
    GENERAL_TEXT = "GENERAL_TEXT"
    CODING = "CODING"
    VISION_ANALYSIS = "VISION_ANALYSIS"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    CALCULATION = "CALCULATION"

# Capability Normalization Map
CAPABILITY_ALIASES = {
    "text": "text_generation",
    "text_generation": "text_generation",
    "generation": "text_generation",
    "reasoning": "reasoning",
    "reason": "reasoning",
    "coding": "coding",
    "code": "coding",
    "vision": "vision",
    "image": "vision",
    "multimodal": "vision",
    "tool_calling": "tool_calling",
    "tool_execution": "tool_calling",
    "tools": "tool_calling",
    "long_context": "long_context",
}

# Task Type Mandatory Capabilities
TASK_MANDATORY_CAPABILITIES: Dict[TaskType, List[str]] = {
    TaskType.DOCUMENT_QA: ["text_generation"],
    TaskType.DOCUMENT_SUMMARY: ["text_generation"],
    TaskType.GENERAL_TEXT: ["text_generation"],
    TaskType.CODING: ["coding"],
    TaskType.VISION_ANALYSIS: ["vision"],
    TaskType.TOOL_EXECUTION: ["tool_calling"],
    TaskType.CALCULATION: ["coding"],
}

# Task Type Preferred Capabilities for secondary ranking
TASK_PREFERRED_CAPABILITIES: Dict[TaskType, List[str]] = {
    TaskType.DOCUMENT_QA: ["reasoning", "tool_calling"],
    TaskType.DOCUMENT_SUMMARY: ["reasoning", "long_context"],
    TaskType.GENERAL_TEXT: ["reasoning"],
    TaskType.CODING: ["tool_calling", "reasoning"],
    TaskType.VISION_ANALYSIS: ["text_generation", "reasoning"],
    TaskType.TOOL_EXECUTION: ["reasoning"],
    TaskType.CALCULATION: ["tool_calling", "reasoning"],
}

class RoutingDecision(BaseModel):
    task_type: str
    selected_model: str
    runtime_model_name: str
    required_capabilities: List[str]
    matched_capabilities: List[str]
    reason: str
    switched: bool = False
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

def validate_model_id(model_id: str) -> str:
    """Validates that a model ID contains only safe alphanumeric and standard delimiter chars."""
    if not model_id or not isinstance(model_id, str):
        raise InvalidModelIdError("Model ID must be a non-empty string.")
    clean = model_id.strip()
    if not re.match(r"^[a-zA-Z0-9_\-\.:]+$", clean) or ".." in clean or "/" in clean or "\\" in clean:
        raise InvalidModelIdError(f"Security validation failed: Invalid model identifier '{clean}'.")
    return clean

def classify_task_from_prompt(prompt: str, has_doc_context: bool = False, has_image: bool = False) -> TaskType:
    """Classifies incoming user query into a stable TaskType enum."""
    p_lower = prompt.lower().strip()
    vision_patterns = [
        "scanned image", "image analysis", "analyze this image", "analyze image", "read image",
        "look at this image", "diagram ocr", "ocr image", "scanned document",
        "scanned diagram", "image diagram", "what does this image", "what is in this image",
        "describe this image", "describe the image", "visible in this image", "identify the major components",
        "visible abnormalities", "schematic diagram", "diagram on page", "visible in the inspection",
        "what defects are visible", "examine the photo", "photograph", "drawing", "vision model", "computer vision"
    ]
    if has_image or any(w in p_lower for w in vision_patterns) or bool(re.search(r"\bvision\b", p_lower)):
        return TaskType.VISION_ANALYSIS

    coding_patterns = [
        "write python", "write a python", "write code", "create python", "generate python",
        "python function", "write a function", "create a function", "implement ", "def ",
        "class ", "execute python", "run code in sandbox", "run python", "sandbox",
        "write a program", "write program", "calculate factorial", "compute factorial",
        "factorial of"
    ]
    if any(p in p_lower for p in coding_patterns) and not p_lower.startswith("what is"):
        return TaskType.CODING

    calc_patterns = [
        "calculate the average", "calculate average", "compute the average", "compute the sum",
        "calculate percentage", "calculate compound interest", "compound interest", "calculate",
        "compute"
    ]
    if any(p in p_lower for p in calc_patterns) and not p_lower.startswith("what is"):
        return TaskType.CALCULATION

    summary_patterns = [
        "summarize the entire document", "summarize the document", "summarize this document",
        "summarize entire document", "summarize document", "summarize the pdf", "summarize pdf",
        "overview of the document", "document overview", "full summary", "complete summary"
    ]
    if any(p in p_lower for p in summary_patterns) or ("summarize" in p_lower and has_doc_context):
        return TaskType.DOCUMENT_SUMMARY

    if has_doc_context or any(k in p_lower for k in ["document", "pdf", "in the document", "according to", "sih2026ppt", "sop", "manual"]):
        return TaskType.DOCUMENT_QA

    return TaskType.GENERAL_TEXT

class ModelRouter:
    """
    Deterministic Model Capability Router for AEGIS Sovereign AI Workbench.
    Routes tasks to compatible locally installed open-weight models based on task requirements.
    """

    def __init__(self, registry_manager: ModelRegistryManager, loader_manager: ModelLoaderManager):
        self.registry_manager = registry_manager
        self.loader_manager = loader_manager

    @staticmethod
    def normalize_capability(cap: str) -> str:
        c = cap.lower().strip()
        return CAPABILITY_ALIASES.get(c, c)

    @classmethod
    def normalize_capabilities(cls, caps: List[str]) -> List[str]:
        return [cls.normalize_capability(c) for c in caps]

    async def route(
        self,
        task_type: Optional[TaskType] = None,
        required_capabilities: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        has_doc_context: bool = False,
        has_image: bool = False,
        preferred_model_id: Optional[str] = None,
        auto_switch: bool = True,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        role: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> RoutingDecision:
        """
        Determines the optimal locally installed model for the given task requirements.
        Performs model switching via loader_manager if required and auto_switch is True.
        """
        # 1. Resolve task type
        if task_type is None:
            if prompt:
                task_type = classify_task_from_prompt(prompt, has_doc_context=has_doc_context, has_image=has_image)
            elif required_capabilities:
                norm_reqs = self.normalize_capabilities(required_capabilities)
                if "vision" in norm_reqs:
                    task_type = TaskType.VISION_ANALYSIS
                elif "coding" in norm_reqs:
                    task_type = TaskType.CODING
                elif "tool_calling" in norm_reqs:
                    task_type = TaskType.TOOL_EXECUTION
                else:
                    task_type = TaskType.GENERAL_TEXT
            else:
                task_type = TaskType.GENERAL_TEXT

        # 2. Resolve mandatory required capabilities
        if required_capabilities:
            req_caps = self.normalize_capabilities(required_capabilities)
        else:
            req_caps = TASK_MANDATORY_CAPABILITIES.get(task_type, ["text_generation"])

        pref_caps = TASK_PREFERRED_CAPABILITIES.get(task_type, [])

        # 3. Discover local models (merges Ollama installed tags + registry metadata)
        discovered = []
        try:
            if hasattr(self.loader_manager, "get_discovered_models"):
                res = self.loader_manager.get_discovered_models()
                if asyncio.iscoroutine(res):
                    res = await res
                if isinstance(res, list):
                    discovered = res
        except Exception as e:
            logger.warning(f"Error fetching discovered models: {e}")

        # Fallback to configured registry models if loader discovery is empty or mocked
        if not discovered or not isinstance(discovered, list) or not all(isinstance(x, dict) for x in discovered):
            try:
                registry_models = self.registry_manager.get_all_models(include_disabled=False)
                active_curr = getattr(self.loader_manager, "current_model_id", None)
                discovered = [
                    {
                        "model_id": m.get("model_id"),
                        "display_name": m.get("display_name", m.get("model_id")),
                        "runtime_model_name": m.get("runtime_model_name", m.get("model_id")),
                        "provider": m.get("provider", "Local"),
                        "runtime": "LOCAL",
                        "status": "ACTIVE" if m.get("model_id") == active_curr else "INSTALLED",
                        "is_installed": True,
                        "is_active": (m.get("model_id") == active_curr),
                        "priority": m.get("priority", 1),
                        "capabilities": m.get("capabilities", ["text_generation", "reasoning", "coding"]),
                        "supports_vision": m.get("supports_vision", False),
                        "supports_code": m.get("supports_code", False),
                        "supports_text": m.get("supports_text", True)
                    }
                    for m in registry_models
                ]
            except Exception as e:
                logger.warning(f"Fallback registry lookup failed: {e}")
                discovered = []

        # 4. Filter for installed models only
        installed_models = [
            m for m in discovered
            if isinstance(m, dict) and (m.get("is_installed") or m.get("status") in ("ACTIVE", "INSTALLED"))
        ]

        if not installed_models:
            raise RuntimeUnavailableError("No locally installed open-weight models were discovered in the local inference runtime.")

        # 5. Filter for models satisfying all mandatory capabilities
        compatible_models = []
        for m in installed_models:
            raw_caps = m.get("capabilities", [])
            model_caps = set(self.normalize_capabilities(raw_caps))
            if m.get("supports_vision"):
                model_caps.add("vision")
            if m.get("supports_code"):
                model_caps.add("coding")
            if m.get("supports_text"):
                model_caps.add("text_generation")

            if all(req in model_caps for req in req_caps):
                compatible_models.append((m, model_caps))

        if not compatible_models:
            req_str = ", ".join(req_caps)
            raise NoCompatibleModelError(
                f"No locally installed model satisfies the required '{req_str}' capability for task '{task_type.value}'."
            )

        # 6. Check currently active/loaded model
        active_id = None
        if hasattr(self.loader_manager, "get_current_model_id"):
            try:
                curr_res = self.loader_manager.get_current_model_id()
                if asyncio.iscoroutine(curr_res):
                    active_id = await curr_res
                elif isinstance(curr_res, str):
                    active_id = curr_res
            except Exception:
                active_id = None
        if not active_id and hasattr(self.loader_manager, "current_model_id") and isinstance(self.loader_manager.current_model_id, str):
            active_id = self.loader_manager.current_model_id

        # Validate preferred_model_id if passed
        if preferred_model_id:
            preferred_model_id = validate_model_id(preferred_model_id)

        # 7. Check if preferred model or active model satisfies requirements (Sticky Session Preference)
        selected_model_meta = None
        selected_caps = []
        reason = ""
        switched = False

        if preferred_model_id:
            for m, caps in compatible_models:
                if m.get("model_id") == preferred_model_id or m.get("runtime_model_name") == preferred_model_id:
                    selected_model_meta = m
                    selected_caps = list(caps)
                    reason = f"Explicitly requested compatible model '{preferred_model_id}'."
                    break

        if not selected_model_meta and active_id:
            for m, caps in compatible_models:
                if m.get("model_id") == active_id or m.get("runtime_model_name") == active_id:
                    selected_model_meta = m
                    selected_caps = list(caps)
                    reason = f"Reusing currently active model '{active_id}' which satisfies all capabilities for {task_type.value}."
                    break

        # 8. Otherwise rank candidates deterministically
        if not selected_model_meta:
            def rank_key(item):
                m, caps = item
                pref_matches = sum(1 for p in pref_caps if p in caps)
                priority = m.get("priority", 10)
                size = m.get("size_bytes") or 0
                return (-pref_matches, priority, -size)

            compatible_models.sort(key=rank_key)
            selected_model_meta, selected_caps_set = compatible_models[0]
            selected_caps = list(selected_caps_set)
            reason = f"Selected optimal local model '{selected_model_meta.get('model_id')}' matching required capabilities for {task_type.value}."

        selected_id = validate_model_id(selected_model_meta.get("model_id"))
        runtime_name = selected_model_meta.get("runtime_model_name", selected_id)

        # 9. Perform model switch if not already active
        if active_id != selected_id and active_id != runtime_name:
            switched = True
            if auto_switch and hasattr(self.loader_manager, "switch_model"):
                logger.info(f"ModelRouter: Switching active model from '{active_id}' to '{selected_id}' for task {task_type.value}")
                try:
                    sw_res = self.loader_manager.switch_model(selected_id)
                    if asyncio.iscoroutine(sw_res):
                        await sw_res
                except Exception as e:
                    logger.warning(f"Model switch call encountered exception: {e}")
                    raise

        # 10. Audit routing decision
        req_id = request_id or get_request_id()
        AuditLogger.log_event(
            action="MODEL_ROUTED",
            component="models.router",
            status="success",
            user_id=user_id,
            username=username,
            role=role,
            resource=selected_id,
            request_id=req_id,
            metadata={
                "task_type": task_type.value,
                "selected_model": selected_id,
                "switched": switched,
                "reason": reason,
                "required_capabilities": req_caps,
                "matched_capabilities": selected_caps
            }
        )

        return RoutingDecision(
            task_type=task_type.value,
            selected_model=selected_id,
            runtime_model_name=runtime_name,
            required_capabilities=req_caps,
            matched_capabilities=selected_caps,
            reason=reason,
            switched=switched,
            fallback_used=False
        )
