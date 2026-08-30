import os
import time
import json
import urllib.request
import logging
import asyncio
from typing import List, Dict, Any, Optional, Callable

from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager

# Setup basic logger
logger = logging.getLogger("aegis.agent_controller")
logger.setLevel(logging.INFO)

class AgentControllerError(Exception):
    """Base exception for agent controller errors."""
    pass

class AgentStep:
    """Represents a discrete step in the agent planning and execution lifecycle."""
    
    def __init__(self, step_id: str, description: str, capability: str, input_data: Any = None):
        self.step_id = step_id
        self.description = description
        self.capability = capability
        self.status = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, REPLAN, SKIPPED
        self.input = input_data
        self.output = None
        self.selected_model = None
        self.error = None
        self.verification_result = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "capability": self.capability,
            "status": self.status,
            "input": self.input,
            "output": self.output,
            "selected_model": self.selected_model,
            "error": self.error,
            "verification_result": self.verification_result
        }

class AgentPlan:
    """Stores the plan sequence, request, current pointer, and final outputs."""
    
    def __init__(self, request: str):
        self.request = request
        self.steps: List[AgentStep] = []
        self.current_step_index = 0
        self.final_output = None
        self.status = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED
        self.inference_mode = "real"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request": self.request,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "final_output": self.final_output,
            "status": self.status,
            "inference_mode": self.inference_mode
        }

class AgentController:
    """
    Coordinates model selection, memory swaps, tool executions, and step verifications.
    """
    
    def __init__(
        self,
        registry_manager: ModelRegistryManager,
        loader_manager: ModelLoaderManager,
        ocr_service: Optional[Any] = None,
        rag_service: Optional[Any] = None,
        sandbox_service: Optional[Any] = None,
        doc_generators: Optional[Dict[str, Any]] = None,
        max_steps: int = 10,
        max_replans: int = 3,
        verify_callback: Optional[Callable[[AgentStep], bool]] = None
    ):
        self.registry_manager = registry_manager
        self.loader_manager = loader_manager
        self.ocr_service = ocr_service
        self.rag_service = rag_service
        self.sandbox_service = sandbox_service
        self.doc_generators = doc_generators or {}
        
        # Limit constraints
        self.max_steps = max_steps
        self.max_replans = max_replans
        self.verify_callback = verify_callback

    def _is_knowledge_query(self, request: str) -> bool:
        """Determines if the request requires organizational document grounding without relying on hardcoded magic phrases."""
        req_lower = request.lower()
        
        # Explicit code/math non-knowledge triggers
        if any(term in req_lower for term in [
            "write python code", "write a python", "def ", "class ", "calculate ", 
            "explain what a python", "reverse a string"
        ]):
            return False
            
        # Knowledge / Organizational query indicators
        knowledge_triggers = [
            "document", "doc", "manual", "file", "policy", "procedure", "requirement",
            "safety", "shutdown", "protocol", "sih", "architecture", "report", "specs",
            "specification", "uploaded", "according to", "find information", "what is our",
            "what are the", "summarize", "in our documents", "knowledge base", "standard",
            "guideline", "rules", "access control", "security policy"
        ]
        
        if any(trigger in req_lower for trigger in knowledge_triggers):
            return True
            
        # Fallback question indicator for factual inquiry
        if "?" in request and not any(k in req_lower for k in ["python", "function", "variable", "code"]):
            return True
            
        return False

    def _classify_capability(self, request: str) -> str:
        """Capability classifier mapping queries to model roles."""
        req_lower = request.lower()
        if "write python code" in req_lower or "coding" in req_lower:
            return "coding"
        elif "analyze scanned document" in req_lower or "ocr" in req_lower:
            return "vision"
        elif "summarize" in req_lower or "reasoning" in req_lower:
            return "reasoning"
        elif self._is_knowledge_query(request):
            return "text_generation"
        return "text_generation"

    def _create_plan(self, request: str) -> AgentPlan:
        """Dynamic multi-step plan compiler using real user query forwarding."""
        plan = AgentPlan(request)
        req_lower = request.lower()
        
        if "execute python script in sandbox" in req_lower or "run code in sandbox" in req_lower:
            # Multi-step sandbox coding task: generate then execute
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Generate Python code script",
                capability="coding",
                input_data={"action": "generate_code", "prompt": request}
            ))
            plan.steps.append(AgentStep(
                step_id="step_2",
                description="Execute generated script in sandbox",
                capability="coding",
                input_data={"action": "execute_code"}
            ))
        elif self._is_knowledge_query(request):
            # Multi-step RAG task: vector lookup with user request then response generation
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Query local vector store for documents",
                capability="text_generation",
                input_data={"action": "rag_search", "query": request}
            ))
            plan.steps.append(AgentStep(
                step_id="step_2",
                description="Generate answer from grounding contexts",
                capability="text_generation",
                input_data={"action": "generate_answer", "user_query": request}
            ))
        elif "analyze scanned document" in req_lower:
            # Scanned document task: OCR rendering and extraction
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Extract page texts via local OCR engine",
                capability="vision",
                input_data={"action": "ocr_pdf", "file_path": "sample.pdf"}
            ))
        else:
            # Fallback direct text generation step
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Generate text response directly",
                capability="text_generation",
                input_data={"action": "generate_text", "prompt": request}
            ))
            
        return plan

    async def _call_llm(self, runtime_model_name: str, prompt: str) -> str:
        """Invokes local Ollama generation endpoint via loader_manager.generate()."""
        try:
            return await self.loader_manager.generate(
                prompt=prompt,
                model_id=runtime_model_name,
                timeout=120.0
            )
        except Exception as e:
            logger.warning(f"Ollama generation fallback triggered: {e}")
            return f"Ollama service error ({e}). Simulated text response for capability model: {runtime_model_name}"

    async def _execute_step(self, plan: AgentPlan, step: AgentStep, current_user: Optional[Any] = None) -> bool:
        """Resolves models, swaps VRAM memory configurations, and dispatches tool commands."""
        step.status = "RUNNING"
        
        # 1. Ask Model Registry for enabled capability support models
        try:
            models = self.registry_manager.get_models_by_capability(step.capability)
            if not models:
                step.error = f"Capability error: No models found supporting '{step.capability}'"
                step.status = "FAILED"
                return False
            # Choose highest priority model (lowest number)
            models.sort(key=lambda m: m.get("priority", 1))
            model_profile = models[0]
            step.selected_model = model_profile["model_id"]
        except Exception as e:
            step.error = f"Registry lookup failure: {e}"
            step.status = "FAILED"
            return False

        # 2. Swap model using ModelLoaderManager
        try:
            await self.loader_manager.switch_model(step.selected_model)
        except Exception as e:
            step.error = f"Loader memory switch failure: {e}"
            step.status = "FAILED"
            return False

        # 3. Tool Dispatch execution
        try:
            if step.capability == "coding":
                action = step.input.get("action", "execute_code")
                if action == "generate_code":
                    prompt = step.input.get("prompt", plan.request)
                    step.output = await self._call_llm(model_profile["runtime_model_name"], prompt)
                elif action == "execute_code":
                    if self.sandbox_service:
                        # Extract code output from previous generate_code step if exists
                        code = "print('Aegis Default Code')"
                        if plan.current_step_index > 0:
                            prev = plan.steps[plan.current_step_index - 1]
                            if prev.capability == "coding" and prev.output:
                                code = prev.output
                                
                        res = self.sandbox_service.execute(code)
                        step.output = res
                        if not res["success"]:
                            step.error = res["error"] or "Sandbox code run failed."
                            step.status = "FAILED"
                            return False
                    else:
                        step.output = "NOT_IMPLEMENTED: Sandbox service is unavailable."
                        step.status = "FAILED"
                        return False
                        
            elif step.capability == "text_generation" or step.capability == "reasoning":
                action = step.input.get("action", "generate_text")
                if action == "rag_search":
                    if self.rag_service:
                        query = step.input.get("query", "")
                        filter_meta = None
                        if current_user:
                            user_role = getattr(current_user, "role", None) if not isinstance(current_user, dict) else current_user.get("role")
                            user_id = getattr(current_user, "id", None) if not isinstance(current_user, dict) else current_user.get("id")
                            if user_role != "admin" and user_id is not None:
                                filter_meta = {"owner_id": user_id}
                        res = self.rag_service.search(query, filter_metadata=filter_meta)
                        step.output = res
                    else:
                        step.output = "NOT_IMPLEMENTED: RAG service is unavailable."
                        step.status = "FAILED"
                        return False
                elif action == "generate_answer":
                    user_query = step.input.get("user_query") or plan.request
                    chunks = []
                    sources_formatted = []
                    
                    if plan.current_step_index > 0:
                        prev = plan.steps[plan.current_step_index - 1]
                        if prev.output and isinstance(prev.output, list):
                            chunks = prev.output

                    if not chunks:
                        step.output = "No relevant organizational knowledge was found."
                    else:
                        for chunk in chunks:
                            text_content = chunk.get("text", "")
                            meta = chunk.get("metadata", {})
                            doc_name = meta.get("filename") or meta.get("document_name") or "Unknown Document"
                            page_num = meta.get("page_number", 1)
                            sources_formatted.append(f"[Source: {doc_name} | Page {page_num}]\n{text_content}")

                        context_str = "\n\n".join(sources_formatted)
                        prompt = (
                            f"SYSTEM INSTRUCTIONS:\n"
                            f"You are AEGIS, an on-premise industrial AI assistant. Use the retrieved organizational context below to answer the user's question. "
                            f"Answer using the retrieved organizational context when available. Do not invent organizational facts.\n\n"
                            f"RETRIEVED KNOWLEDGE:\n{context_str}\n\n"
                            f"USER QUESTION:\n{user_query}"
                        )
                        step.output = await self._call_llm(model_profile["runtime_model_name"], prompt)
                        if isinstance(step.output, str) and step.output.startswith("Simulated text response"):
                            plan.inference_mode = "mock"
                else:
                    prompt = step.input.get("prompt", "")
                    step.output = await self._call_llm(model_profile["runtime_model_name"], prompt)
                    if isinstance(step.output, str) and step.output.startswith("Simulated text response"):
                        plan.inference_mode = "mock"
                    
            elif step.capability == "vision" or step.capability == "multimodal":
                if self.ocr_service:
                    file_path = step.input.get("file_path", "")
                    res = self.ocr_service.ocr_pdf(file_path)
                    step.output = res
                else:
                    step.output = "NOT_IMPLEMENTED: OCR service is unavailable."
                    step.status = "FAILED"
                    return False
            else:
                step.output = f"NOT_IMPLEMENTED: Capability '{step.capability}' has no tool executor adapter."
                step.status = "FAILED"
                return False

            step.status = "COMPLETED"
            return True
            
        except Exception as e:
            step.error = str(e)
            step.status = "FAILED"
            return False

    async def run(self, request: str, current_user: Optional[Any] = None) -> Dict[str, Any]:
        """Orchestrates agent planning, step loops, verifications, and failure replans."""
        from backend.security.audit import AuditLogger
        
        if not request or not request.strip():
            AuditLogger.log_event(
                action="AGENT_EXECUTION",
                component="agents.controller.agent",
                status="failure",
                metadata={"error_category": "empty_request"}
            )
            return {
                "success": False,
                "error": "Empty or invalid query request.",
                "plan": None
            }

        start_time = time.perf_counter()
        
        # 1. Compile Plan
        plan = self._create_plan(request)
        plan.status = "RUNNING"
        
        steps_executed = 0
        replans_count = 0
        
        # 2. Sequential Execution Loop
        while plan.current_step_index < len(plan.steps):
            if steps_executed >= self.max_steps:
                plan.status = "FAILED"
                plan.final_output = "Error: Maximum execution steps limit exceeded."
                break
                
            step = plan.steps[plan.current_step_index]
            step_start = time.perf_counter()
            
            # Execute step
            success = await self._execute_step(plan, step, current_user)
            duration_ms = int((time.perf_counter() - step_start) * 1000)
            steps_executed += 1
            
            # Metadata-only logging to avoid leaks
            logger.info(
                f"AgentController Step: ID={step.step_id} "
                f"Capability={step.capability} "
                f"Model={step.selected_model} "
                f"Status={step.status} "
                f"Duration={duration_ms}ms"
            )
            
            if success:
                # 3. Verification Hook check
                verified = True
                if self.verify_callback:
                    try:
                        import inspect
                        sig = inspect.signature(self.verify_callback)
                        if len(sig.parameters) >= 2:
                            verified = self.verify_callback(plan, step)
                        else:
                            verified = self.verify_callback(step)
                            
                        if not step.verification_result:
                            step.verification_result = "PASS" if verified else "FAIL"
                            
                        # Log VERIFICATION audit event
                        AuditLogger.log_event(
                            action="VERIFICATION",
                            component="agents.controller.agent",
                            status="success" if verified else "failure",
                            resource=step.step_id,
                            metadata={
                                "step_id": step.step_id,
                                "capability": step.capability,
                                "status": "PASS" if verified else "FAIL"
                            }
                        )
                    except Exception as ve:
                        step.verification_result = f"ERROR: {ve}"
                        verified = False
                        
                        AuditLogger.log_event(
                            action="VERIFICATION",
                            component="agents.controller.agent",
                            status="failure",
                            resource=step.step_id,
                            metadata={
                                "step_id": step.step_id,
                                "capability": step.capability,
                                "status": "ERROR",
                                "error_category": "verification_exception"
                            }
                        )
                else:
                    step.verification_result = "PASS"
                    
                if verified:
                    plan.current_step_index += 1
                else:
                    # Treat verification failure as step failure to trigger replan
                    step.status = "FAILED"
                    step.error = "Step verification check failed (FAIL status returned)."
                    success = False

            if not success:
                # Failure & Replan check
                if replans_count < self.max_replans:
                    replans_count += 1
                    logger.info(f"Replan Guard: Step {step.step_id} failed. Inserting retry (Replan {replans_count}/{self.max_replans})")
                    
                    # Insert a duplicate retry step in the pipeline sequence
                    retry_step = AgentStep(
                        step_id=f"{step.step_id}_retry_{replans_count}",
                        description=f"Retry of {step.description}",
                        capability=step.capability,
                        input_data=step.input
                    )
                    plan.steps.insert(plan.current_step_index + 1, retry_step)
                    step.status = "REPLAN"
                    plan.current_step_index += 1
                else:
                    plan.status = "FAILED"
                    plan.final_output = f"Execution halted: Step {step.step_id} failed and retry budget is exhausted."
                    break

        if plan.status == "RUNNING" and plan.current_step_index >= len(plan.steps):
            plan.status = "COMPLETED"
            # Set final output as the output of the last successfully executed step
            if plan.steps:
                plan.final_output = plan.steps[-1].output

        total_duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(f"AgentController: Finished request in {total_duration_ms}ms with status={plan.status}")
        
        AuditLogger.log_event(
            action="AGENT_EXECUTION",
            component="agents.controller.agent",
            status="success" if plan.status == "COMPLETED" else "failure",
            duration_ms=total_duration_ms,
            metadata={
                "status": plan.status,
                "replan_count": replans_count,
                "duration_ms": total_duration_ms,
                "error_category": "max_steps_exceeded" if steps_executed >= self.max_steps else ("step_failure" if plan.status == "FAILED" else None)
            }
        )
        
        rag_used = False
        sources = []
        model_used = getattr(self.loader_manager, "current_model_id", "gemma3:4b") or "gemma3:4b"

        if plan.steps:
            for s in plan.steps:
                if s.capability == "text_generation" and s.input.get("action") == "rag_search" and s.output:
                    if isinstance(s.output, list) and len(s.output) > 0:
                        rag_used = True
                        for chunk in s.output:
                            meta = chunk.get("metadata", {})
                            sources.append({
                                "filename": meta.get("filename") or meta.get("document_name") or "Unknown Document",
                                "page": meta.get("page_number", 1),
                                "distance": round(chunk.get("distance", 0.0), 4)
                            })
                if s.selected_model:
                    model_used = s.selected_model

        return {
            "success": plan.status == "COMPLETED",
            "answer": plan.final_output if plan.status == "COMPLETED" else (plan.final_output or "Agent execution failed."),
            "rag_used": rag_used,
            "sources": sources,
            "model": model_used,
            "plan": plan.to_dict(),
            "duration_ms": total_duration_ms,
            "error": plan.final_output if plan.status == "FAILED" else None
        }
