import os
import json
import urllib.request
import urllib.error
import asyncio
import logging
from typing import List, Dict, Any, Optional
from backend.models.registry.manager import ModelRegistryManager, ModelRegistryError

# Setup basic logger
logger = logging.getLogger("aegis.model_loader")
logger.setLevel(logging.INFO)

class ModelLoaderError(Exception):
    """Base exception for model loading issues."""
    pass

class RuntimeUnavailableError(ModelLoaderError):
    """Raised when the local Ollama runtime is not running/unreachable."""
    pass

class ModelLoadTimeoutError(ModelLoaderError):
    """Raised when loading weights exceeds the timeout interval."""
    pass

class ModelUnloadTimeoutError(ModelLoaderError):
    """Raised when unloading weights exceeds the timeout interval."""
    pass

class ConcurrencyTimeoutError(ModelLoaderError):
    """Raised when a lock acquisition times out under high concurrency."""
    pass

class ModelNotFoundError(ModelLoaderError):
    """Raised when the requested model is not pulled in the local Ollama runtime."""
    pass

class ModelLoaderManager:
    """Manages the memory lifecycle of local LLMs using dynamic loading/unloading mutex loops."""
    
    def __init__(self, registry_manager: ModelRegistryManager, base_url: Optional[str] = None):
        self.registry_manager = registry_manager
        from backend.app.config.settings import settings
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.lock = asyncio.Lock()
        self.current_model_id: Optional[str] = None
        
    async def get_current_model_id(self) -> Optional[str]:
        """Cross-references loaded VRAM model names against the configuration registry."""
        try:
            running = await self.get_running_models()
            if running:
                models = self.registry_manager.get_all_models(include_disabled=True)
                for m in models:
                    target = m["runtime_model_name"]
                    if any(target == r or r.startswith(target + ":") or target.startswith(r + ":") for r in running):
                        return m["model_id"]
            return None
        except Exception:
            return None

    async def get_discovered_models(self) -> List[Dict[str, Any]]:
        """
        Discovers locally installed models from Ollama runtime via GET /api/tags,
        merges with configured registry metadata, and determines active/installed status.
        """
        active_id = await self.get_current_model_id() or self.current_model_id or "gemma3:4b"
        installed_ollama_models = []
        try:
            res = await asyncio.to_thread(self._send_request, "/api/tags", "GET", timeout=5.0)
            installed_ollama_models = res.get("models", [])
        except Exception as e:
            logger.warning(f"Failed to discover local Ollama tags: {e}")

        installed_tags = {m.get("name"): m for m in installed_ollama_models if m.get("name")}
        
        configured_models = self.registry_manager.get_all_models(include_disabled=True)
        results = []
        seen_tags = set()

        for cfg in configured_models:
            tag = cfg.get("runtime_model_name", cfg.get("model_id"))
            seen_tags.add(tag)
            seen_tags.add(cfg.get("model_id"))
            
            is_installed = tag in installed_tags or any(tag == t or t.startswith(tag + ":") for t in installed_tags)
            is_active = (cfg.get("model_id") == active_id or tag == active_id)
            
            ollama_meta = installed_tags.get(tag, {})
            details = ollama_meta.get("details", {})
            
            status = "ACTIVE" if is_active else ("INSTALLED" if is_installed else "UNAVAILABLE")
            
            results.append({
                "model_id": cfg.get("model_id"),
                "display_name": cfg.get("display_name", cfg.get("model_id")),
                "runtime_model_name": tag,
                "provider": cfg.get("provider", details.get("family", "Ollama").capitalize()),
                "runtime": "LOCAL",
                "status": status,
                "is_installed": is_installed,
                "is_active": is_active,
                "size_bytes": ollama_meta.get("size"),
                "modified_at": ollama_meta.get("modified_at"),
                "parameter_size": details.get("parameter_size", cfg.get("quantization", "4B")),
                "quantization": details.get("quantization_level", cfg.get("quantization", "Q4_K_M")),
                "format": details.get("format", "gguf"),
                "family": details.get("family", "gemma3"),
                "capabilities": cfg.get("capabilities", ["text_generation", "reasoning", "coding"]),
                "notes": cfg.get("notes", "Local open-weight model.")
            })

        for tag, meta in installed_tags.items():
            if tag not in seen_tags and not any(tag.startswith(st + ":") for st in seen_tags):
                is_active = (tag == active_id)
                details = meta.get("details", {})
                results.append({
                    "model_id": tag,
                    "display_name": tag.capitalize(),
                    "runtime_model_name": tag,
                    "provider": details.get("family", "Ollama").capitalize(),
                    "runtime": "LOCAL",
                    "status": "ACTIVE" if is_active else "INSTALLED",
                    "is_installed": True,
                    "is_active": is_active,
                    "size_bytes": meta.get("size"),
                    "modified_at": meta.get("modified_at"),
                    "parameter_size": details.get("parameter_size", "4B"),
                    "quantization": details.get("quantization_level", "Q4_K_M"),
                    "format": details.get("format", "gguf"),
                    "family": details.get("family", "Ollama"),
                    "capabilities": ["text_generation", "reasoning", "coding"],
                    "notes": "Discovered from local Ollama runtime tags."
                })

        return results
        
    def _send_request(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: float = 60.0) -> Dict[str, Any]:
        """Performs blocking synchronous HTTP requests to local Ollama runtime with exponential backoff retries."""
        import time
        url = f"{self.base_url}{path}"
        data = None
        headers = {}
        
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            
        max_retries = 3
        backoff_delay = 0.2
        last_exception = None

        for attempt in range(max_retries):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    status = response.status
                    body = response.read().decode("utf-8")
                    
                    if status not in (200, 201, 204):
                        raise ModelLoaderError(f"HTTP call returned error status: {status}")
                    
                    if body.strip():
                        try:
                            return json.loads(body)
                        except json.JSONDecodeError:
                            return {"text": body}
                    return {}
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise ModelNotFoundError(f"Requested model was not found in local Ollama storage: HTTP 404")
                last_exception = ModelLoaderError(f"Ollama call returned HTTP status {e.code}")
            except urllib.error.URLError as e:
                last_exception = RuntimeUnavailableError(f"Ollama local service is unreachable: {e.reason}")
            except Exception as e:
                last_exception = ModelLoaderError(f"Ollama call encountered error: {e}")

            # Sleep before retrying
            if attempt < max_retries - 1:
                time.sleep(backoff_delay)
                backoff_delay *= 2.0

        if isinstance(last_exception, (RuntimeUnavailableError, ModelNotFoundError, ModelLoaderError)):
            raise last_exception
        raise RuntimeUnavailableError(f"Ollama local service is unreachable after {max_retries} attempts: {last_exception}")

    async def is_runtime_available(self) -> bool:
        """Asynchronously checks if the local Ollama daemon is running."""
        try:
            # We call the root URL which returns a simple text string "Ollama is running"
            result = await asyncio.to_thread(self._send_request, "/", "GET", timeout=5.0)
            return "Ollama" in result.get("text", "") or "running" in result.get("text", "")
        except RuntimeUnavailableError:
            return False
        except Exception:
            return False

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        timeout: float = 60.0
    ) -> str:
        """
        Asynchronously verifies local Ollama availability, resolves model names,
        and generates response text via local Ollama HTTP endpoints.
        """
        if not prompt or not prompt.strip():
            raise ModelLoaderError("Prompt text cannot be empty.")

        # 1. Verify Ollama daemon reachability
        if not await self.is_runtime_available():
            raise RuntimeUnavailableError(
                f"Local inference runtime (Ollama) is offline or unreachable at '{self.base_url}'."
            )

        # 2. Resolve target runtime model name
        target_model = model_id or self.current_model_id or "gemma3:4b"
        runtime_model = target_model
        try:
            profile = self.registry_manager.get_model(target_model)
            runtime_model = profile.get("runtime_model_name", target_model)
        except Exception:
            runtime_model = target_model

        # 3. Build API payload
        payload: Dict[str, Any] = {
            "model": runtime_model,
            "prompt": prompt,
            "stream": False
        }
        if system_prompt:
            payload["system"] = system_prompt

        # 4. Dispatch async request to local daemon
        try:
            result = await asyncio.to_thread(self._send_request, "/api/generate", "POST", payload, timeout=timeout)
            response_text = result.get("response", "")
            return response_text
        except RuntimeUnavailableError:
            raise
        except Exception as e:
            raise ModelLoaderError(f"Ollama local generation failed: {e}")

    async def get_running_models(self) -> List[str]:
        """Asynchronously retrieves the tags of currently loaded models in VRAM."""
        try:
            result = await asyncio.to_thread(self._send_request, "/api/ps", "GET", timeout=3.0)
            models = result.get("models", [])
            # Return list of exact model tags in memory
            return [m["name"] for m in models]
        except RuntimeUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch loaded models: {e}")
            return []

    async def unload_model(self, runtime_model_name: str, poll_interval: float = 0.5, timeout: float = 15.0) -> None:
        """Instructs Ollama to release a model's VRAM allocation and blocks until unloaded."""
        logger.info(f"Requesting unload of active model: {runtime_model_name}")
        
        # Ollama API unloads models when a generation request is sent with keep_alive=0
        payload = {
            "model": runtime_model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": 0
        }
        
        try:
            # Send immediate unload request
            await asyncio.to_thread(self._send_request, "/api/generate", "POST", payload, timeout=5.0)
        except Exception as e:
            logger.warning(f"Unload command sent but threw response warning: {e}")
            
        # Verify unload via polling status check
        start_time = asyncio.get_event_loop().time()
        while True:
            running = await self.get_running_models()
            
            # Match names flexibly to capture tag mismatches
            is_loaded = any(
                runtime_model_name == r or r.startswith(runtime_model_name + ":") or runtime_model_name.startswith(r + ":")
                for r in running
            )
            if not is_loaded:
                logger.info(f"Model {runtime_model_name} successfully unloaded from memory.")
                return
                
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise ModelUnloadTimeoutError(f"Model {runtime_model_name} failed to unload within {timeout}s.")
                
            await asyncio.sleep(poll_interval)

    async def load_model(self, runtime_model_name: str, poll_interval: float = 1.0, timeout: float = 60.0) -> None:
        """Instructs Ollama to load model weights into VRAM and blocks until verified active."""
        logger.info(f"Requesting load of model: {runtime_model_name}")
        
        payload = {
            "model": runtime_model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": -1  # Load weights indefinitely
        }
        
        # Ollama loads in the background; we send a generate request to trigger the load
        try:
            await asyncio.to_thread(self._send_request, "/api/generate", "POST", payload, timeout=timeout)
        except Exception as e:
            raise ModelLoaderError(f"Ollama load API call failed: {e}")

        # Verify active status
        start_time = asyncio.get_event_loop().time()
        while True:
            running = await self.get_running_models()
            
            # Flexibly checks tags
            is_loaded = any(
                runtime_model_name == r or r.startswith(runtime_model_name + ":") or runtime_model_name.startswith(r + ":")
                for r in running
            )
            if is_loaded:
                logger.info(f"Model {runtime_model_name} is active in VRAM.")
                return
                
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise ModelLoadTimeoutError(f"Model {runtime_model_name} failed to activate within {timeout}s.")
                
            await asyncio.sleep(poll_interval)

    async def switch_model(self, model_id: str, load_timeout: float = 60.0, unload_timeout: float = 15.0) -> Dict[str, Any]:
        """Switches the active runtime model to match the requested AEGIS model_id. HandlesMutex locking."""
        from backend.security.audit import AuditLogger
        import time
        start_time = time.perf_counter()
        
        # 1. Validate target model exists in registry
        try:
            model_profile = self.registry_manager.get_model(model_id)
        except ModelRegistryError as e:
            AuditLogger.log_event(
                action="MODEL_SWITCH",
                component="models.loaders.manager",
                status="failure",
                resource=model_id,
                metadata={"model_id": model_id, "error_category": "invalid_model_id"}
            )
            raise ModelLoaderError(f"Invalid model_id parameter: {e}")

        runtime_model_name = model_profile["runtime_model_name"]
        
        # 2. Check runtime availability before acquiring lock
        if not await self.is_runtime_available():
            AuditLogger.log_event(
                action="MODEL_SWITCH",
                component="models.loaders.manager",
                status="failure",
                resource=model_id,
                metadata={"model_id": model_id, "error_category": "runtime_offline"}
            )
            raise RuntimeUnavailableError("Local inference runtime is offline or unreachable.")
            
        # 3. Acquire loader lock (ensures single active model operation)
        async with self.lock:
            logger.info(f"Acquired dynamic model loader lock for model '{model_id}'")
            
            # 4. Check currently active models
            running = await self.get_running_models()
            
            # Check if target is already running
            is_active = any(
                runtime_model_name == r or r.startswith(runtime_model_name + ":") or runtime_model_name.startswith(r + ":")
                for r in running
            )
            
            if is_active:
                logger.info(f"Model '{model_id}' is already active. Skipping swap.")
                self.current_model_id = model_id
                AuditLogger.log_event(
                    action="MODEL_SWITCH",
                    component="models.loaders.manager",
                    status="success",
                    resource=model_id,
                    metadata={"model_id": model_id, "status": "already_loaded"}
                )
                return {"status": "success", "model_id": model_id, "active_model": runtime_model_name, "details": "already_loaded"}
                
            # 5. Unload all running models to respect 6GB VRAM limit
            for active in running:
                logger.info(f"VRAM Constraint Guard: Unloading loaded model '{active}' before loading '{runtime_model_name}'")
                try:
                    await self.unload_model(active, timeout=unload_timeout)
                    AuditLogger.log_event(
                        action="MODEL_UNLOAD",
                        component="models.loaders.manager",
                        status="success",
                        resource=active,
                        metadata={"model_id": active}
                    )
                except Exception:
                    AuditLogger.log_event(
                        action="MODEL_UNLOAD",
                        component="models.loaders.manager",
                        status="failure",
                        resource=active,
                        metadata={"model_id": active, "error_category": "unload_timeout"}
                    )
                    raise
                
            # 6. Load target model weights
            try:
                await self.load_model(runtime_model_name, timeout=load_timeout)
                AuditLogger.log_event(
                    action="MODEL_LOAD",
                    component="models.loaders.manager",
                    status="success",
                    resource=runtime_model_name,
                    metadata={"model_id": model_id}
                )
            except Exception:
                AuditLogger.log_event(
                    action="MODEL_LOAD",
                    component="models.loaders.manager",
                    status="failure",
                    resource=runtime_model_name,
                    metadata={"model_id": model_id, "error_category": "load_timeout"}
                )
                AuditLogger.log_event(
                    action="MODEL_SWITCH",
                    component="models.loaders.manager",
                    status="failure",
                    resource=model_id,
                    metadata={"model_id": model_id, "error_category": "load_failure"}
                )
                raise
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            AuditLogger.log_event(
                action="MODEL_SWITCH",
                component="models.loaders.manager",
                status="success",
                resource=model_id,
                duration_ms=duration_ms,
                metadata={"model_id": model_id, "duration_ms": duration_ms}
            )
            
            self.current_model_id = model_id
            return {
                "status": "success",
                "model_id": model_id,
                "active_model": runtime_model_name,
                "details": "swapped"
            }
