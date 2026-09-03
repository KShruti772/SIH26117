import os
import time
import json
import re
import logging
import asyncio
from typing import List, Dict, Any, Optional, Callable

from backend.models.registry.manager import ModelRegistryManager
from backend.models.loaders.manager import ModelLoaderManager
from backend.models.router import ModelRouter, TaskType, RoutingDecision, classify_task_from_prompt

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
        self.routing_decision = None
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
            "routing_decision": self.routing_decision,
            "error": self.error,
            "verification_result": self.verification_result
        }

class AgentPlan:
    """Stores the plan sequence, request, current pointer, and final outputs."""
    
    def __init__(self, request: str, category: str = "CATEGORY_A"):
        self.request = request
        self.category = category
        self.steps: List[AgentStep] = []
        self.current_step_index = 0
        self.final_output = None
        self.status = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED
        self.inference_mode = "real"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request": self.request,
            "category": self.category,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "final_output": self.final_output,
            "status": self.status,
            "inference_mode": self.inference_mode
        }

class AgentController:
    """
    Coordinates model selection, memory swaps, tool executions, document analysis, and step verifications.
    """
    
    def __init__(
        self,
        registry_manager: ModelRegistryManager,
        loader_manager: ModelLoaderManager,
        ocr_service: Optional[Any] = None,
        rag_service: Optional[Any] = None,
        sandbox_service: Optional[Any] = None,
        doc_generators: Optional[Dict[str, Any]] = None,
        model_router: Optional[ModelRouter] = None,
        max_steps: int = 10,
        max_replans: int = 3,
        verify_callback: Optional[Callable[[Any, Any], bool]] = None
    ):
        self.registry_manager = registry_manager
        self.loader_manager = loader_manager
        self.model_router = model_router or ModelRouter(registry_manager, loader_manager)
        self.ocr_service = ocr_service
        self.rag_service = rag_service
        self.sandbox_service = sandbox_service
        self.doc_generators = doc_generators or {}
        
        # Limit constraints
        self.max_steps = max_steps
        self.max_replans = max_replans
        self.verify_callback = verify_callback

    def _classify_capability(self, prompt: str) -> str:
        """Helper for capability classification mapping keywords to capabilities."""
        p_lower = prompt.lower()
        if any(w in p_lower for w in ["scanned", "ocr", "layout", "image", "diagram ocr"]) or bool(re.search(r"\bvision\b", p_lower)):
            return "vision"
        if any(w in p_lower for w in ["python", "code", "coding", "sandbox", "program", "def ", "class "]):
            return "coding"
        if any(w in p_lower for w in ["summarize logic", "reasoning", "reason"]):
            return "reasoning"
        return "text_generation"

    def _extract_clean_user_prompt(self, raw_request: str) -> str:
        """Extracts the actual new user prompt if prefixed by conversation context."""
        if "User's new question:\n" in raw_request:
            return raw_request.split("User's new question:\n", 1)[1].strip()
        return raw_request.strip()

    def _find_referenced_document(self, query: str, user_id: Optional[int] = None, is_admin: bool = False) -> Optional[Dict[str, Any]]:
        """Identifies if a specific document is referenced in the query by filename or alias."""
        if not self.rag_service:
            return None
        try:
            docs = self.rag_service.list_documents(owner_id=user_id, is_admin=is_admin)
            if not docs or not isinstance(docs, list):
                return None
                
            query_lower = query.lower()
            for doc in docs:
                fname = doc.get("filename", "").lower()
                base_name = os.path.splitext(fname)[0]
                if fname and fname in query_lower:
                    return doc
                if base_name and len(base_name) > 3 and base_name in query_lower:
                    return doc
                    
            # If query explicitly refers to a document and only 1 document is indexed
            explicit_refs = ["this document", "the document", "this pdf", "the pdf", "this file", "the file", "uploaded document", "uploaded file", "our document"]
            if any(p in query_lower for p in explicit_refs) and len(docs) == 1:
                return docs[0]
                
            return None
        except Exception:
            return None

    def _classify_query(self, query: str, current_user: Optional[Any] = None) -> Dict[str, Any]:
        """
        Classifies the incoming user request into one of the 4 strict categories:
        - CATEGORY_A: General question (no RAG)
        - CATEGORY_B: Specific document question (grounded vector RAG)
        - CATEGORY_C: Document-wide question (hierarchical / full-document analysis)
        - CATEGORY_D: Coding / calculation question (code generation + sandbox execution)
        """
        q_lower = query.lower().strip()
        user_id = getattr(current_user, "id", None) if not isinstance(current_user, dict) else current_user.get("id")
        user_role = getattr(current_user, "role", None) if not isinstance(current_user, dict) else current_user.get("role")
        is_admin = user_role == "admin"
        
        target_doc = self._find_referenced_document(query, user_id=user_id, is_admin=is_admin)

        # 1. Check for vision / image analysis patterns
        vision_patterns = [
            "scanned image", "image analysis", "read image", "look at this image",
            "diagram ocr", "ocr image", "scanned document", "scanned diagram",
            "image diagram", "analyze image"
        ]
        if any(w in q_lower for w in vision_patterns) or bool(re.search(r"\bvision\b", q_lower)):
            return {"category": "CATEGORY_OCR", "target_doc": target_doc}

        # 2. Check for definitional / conceptual general knowledge questions
        if q_lower.startswith(("explain what", "what is a ", "what is an ", "what are ", "how does a ", "how do ")) and not any(k in q_lower for k in ["in the document", "in this document", "our", "internal", "uploaded", "ft_03", "in this", "according to"]):
            if target_doc is None:
                return {"category": "CATEGORY_A", "target_doc": None}

        # 3. Check for doc indicators
        doc_indicators = [
            "document", "doc", "pdf", "file", "manual", "policy", "procedure", "requirement",
            "safety", "protocol", "sih", "architecture", "report", "specs", "specification",
            "uploaded", "according to", "in our documents", "knowledge base", "standard",
            "guideline", "rules", "cooling system", "turbine", "reactor", "valve", "alpha cooling",
            "operating temperature", "emergency action", "vendor", "foodsync", "ft_03",
            "team id", "project title", "methodology", "problem statement", "this document"
        ]
        has_doc_indicator = any(k in q_lower for k in doc_indicators) or (target_doc is not None)

        # 3. Check for coding patterns
        coding_patterns = [
            "write python", "write a python", "write code", "create python", "generate python",
            "python function", "write a function", "create a function", "implement ", "def ",
            "class ", "execute python", "run code in sandbox", "run python", "sandbox",
            "calculate the average", "calculate average", "compute the average", "compute the sum",
            "calculate percentage", "calculate compound interest", "compound interest", "calculate",
            "compute", "write a program", "write program"
        ]
        is_coding = any(p in q_lower for p in coding_patterns) and not q_lower.startswith("what is")

        if is_coding and has_doc_indicator:
            return {"category": "CATEGORY_MIXED", "target_doc": target_doc}

        if is_coding:
            return {"category": "CATEGORY_D", "target_doc": target_doc}

        # 4. Check for CATEGORY C: Document-wide Analysis / Summarization
        whole_doc_patterns = [
            "summarize the entire document", "summarize the document", "summarize this document",
            "summarize entire document", "summarize document", "summarize the pdf", "summarize pdf",
            "explain the entire project", "explain the complete project", "explain complete project",
            "what are all the major sections", "what are all major sections", "all major sections",
            "what are the key findings", "key findings of the document", "key findings of this document",
            "give me the complete methodology", "complete methodology", "compare the objectives and results",
            "overview of the document", "overview of this document", "document overview", "full summary",
            "complete summary", "whole document"
        ]
        is_whole_doc = any(p in q_lower for p in whole_doc_patterns) or (
            "summarize" in q_lower and (target_doc is not None or "ft_03" in q_lower or "document" in q_lower or "presentation" in q_lower)
        )

        if is_whole_doc:
            return {"category": "CATEGORY_C", "target_doc": target_doc}

        # 5. Specific Document Question
        if has_doc_indicator:
            return {"category": "CATEGORY_B", "target_doc": target_doc}

        # 6. Otherwise: CATEGORY A: General question (Direct LLM reasoning)
        return {"category": "CATEGORY_A", "target_doc": None}

    def _create_plan(self, raw_request: str, current_user: Optional[Any] = None) -> AgentPlan:
        """Dynamic plan compiler routing queries to appropriate multi-step pipelines."""
        clean_query = self._extract_clean_user_prompt(raw_request)
        classification = self._classify_query(clean_query, current_user=current_user)
        category = classification["category"]
        target_doc = classification.get("target_doc")
        target_doc_id = target_doc.get("id") if target_doc else None
        target_filename = target_doc.get("filename") if target_doc else None

        plan = AgentPlan(raw_request, category=category)

        if category == "CATEGORY_C":
            # Document-wide analysis / Map-Reduce pipeline
            plan.steps.append(AgentStep(
                step_id="step_1",
                description=f"Aggregate full document structure for '{target_filename or 'target document'}'",
                capability="text_generation",
                input_data={
                    "action": "document_wide_analysis",
                    "document_id": target_doc_id,
                    "filename": target_filename,
                    "query": clean_query
                }
            ))
            plan.steps.append(AgentStep(
                step_id="step_2",
                description="Synthesize comprehensive document-level analysis",
                capability="text_generation",
                input_data={
                    "action": "synthesize_document_summary",
                    "user_query": clean_query,
                    "filename": target_filename
                }
            ))

        elif category == "CATEGORY_B":
            # Specific grounded RAG question
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Query local vector store for grounded document evidence",
                capability="text_generation",
                input_data={
                    "action": "rag_search",
                    "query": clean_query,
                    "document_id": target_doc_id
                }
            ))
            plan.steps.append(AgentStep(
                step_id="step_2",
                description="Synthesize grounded answer with accurate citations",
                capability="text_generation",
                input_data={
                    "action": "generate_answer",
                    "user_query": clean_query,
                    "filename": target_filename
                }
            ))

        elif category == "CATEGORY_MIXED":
            # Mixed RAG + Coding task
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Retrieve document context for calculation",
                capability="text_generation",
                input_data={"action": "rag_search", "query": clean_query, "document_id": target_doc_id}
            ))
            plan.steps.append(AgentStep(
                step_id="step_2",
                description="Generate executable Python code using document values",
                capability="coding",
                input_data={"action": "generate_code", "prompt": clean_query}
            ))
            plan.steps.append(AgentStep(
                step_id="step_3",
                description="Execute generated script in sandbox",
                capability="coding",
                input_data={"action": "execute_code"}
            ))

        elif category == "CATEGORY_D":
            # Pure coding / calculation task
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Generate executable Python code for calculation",
                capability="coding",
                input_data={"action": "generate_code", "prompt": clean_query}
            ))
            plan.steps.append(AgentStep(
                step_id="step_2",
                description="Execute generated script in isolated sandbox",
                capability="coding",
                input_data={"action": "execute_code"}
            ))

        elif category == "CATEGORY_OCR":
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Extract text via local OCR engine",
                capability="vision",
                input_data={"action": "ocr_pdf", "file_path": target_filename or "sample.pdf"}
            ))

        else:
            # CATEGORY A: General question (Direct local LLM reasoning)
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Generate direct reasoning response",
                capability="text_generation",
                input_data={"action": "generate_text", "prompt": clean_query}
            ))

        return plan

    async def _call_llm(
        self,
        runtime_model_name: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        images: Optional[List[str]] = None
    ) -> str:
        """Invokes local Ollama generation endpoint via loader_manager.generate()."""
        try:
            import inspect
            sig = inspect.signature(self.loader_manager.generate)
            kwargs: Dict[str, Any] = {"timeout": 120.0, "model_id": runtime_model_name}
            if images and ("images" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())):
                kwargs["images"] = images

            if "system_prompt" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                return await self.loader_manager.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    **kwargs
                )
            else:
                full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
                return await self.loader_manager.generate(
                    prompt=full_prompt,
                    **kwargs
                )
        except Exception as e:
            logger.warning(f"Local model generation failed: {e}")
            raise RuntimeError(f"Local model generation failed: {e}") from e

    async def _execute_step(self, plan: AgentPlan, step: AgentStep, current_user: Optional[Any] = None) -> bool:
        """Resolves models, swaps VRAM memory configurations, and executes discrete capability steps."""
        step.status = "RUNNING"
        
        # 1. Route to optimal local model for the required capability
        try:
            user_id = getattr(current_user, "id", None) if not isinstance(current_user, dict) else current_user.get("id")
            username = getattr(current_user, "username", None) if not isinstance(current_user, dict) else current_user.get("username")
            role = getattr(current_user, "role", None) if not isinstance(current_user, dict) else current_user.get("role")
            step_prompt = (step.input.get("prompt") if isinstance(step.input, dict) else None) or plan.request
            routing = await self.model_router.route(
                required_capabilities=[step.capability],
                prompt=step_prompt,
                auto_switch=True,
                user_id=user_id,
                username=username,
                role=role
            )
            step.selected_model = routing.selected_model
            step.routing_decision = routing.to_dict()
            model_profile = {
                "model_id": routing.selected_model,
                "runtime_model_name": routing.runtime_model_name
            }
        except Exception as e:
            step.error = f"Model routing failure: {e}"
            step.status = "FAILED"
            return False

        # 3. Tool Dispatch execution
        try:
            # -------------------------------------------------------------
            # CODING CAPABILITY
            # -------------------------------------------------------------
            if step.capability == "coding":
                action = step.input.get("action", "execute_code")
                if action == "generate_code":
                    prompt_task = step.input.get("prompt", plan.request)
                    
                    # Check for RAG context chunks
                    rag_context_chunks = []
                    for s in reversed(plan.steps[:plan.current_step_index]):
                        if s.input and s.input.get("action") in ("rag_search", "document_wide_analysis") and isinstance(s.output, list):
                            rag_context_chunks = s.output
                            break

                    system_prompt = (
                        "You are AEGIS Code Generator, an industrial on-premise AI coding assistant.\n"
                        "Generate ONLY clean, optimal, syntactically correct Python 3 code wrapped inside a ```python ``` markdown block.\n"
                        "The script must compute the requested logic or perform the requested file operation and output the final result using print().\n"
                        "CRITICAL: DO NOT add arbitrary or dummy print statements (e.g. print(0)).\n"
                        "CRITICAL: DO NOT include any conversational text or explanation outside the ```python ``` code block."
                    )
                    
                    if rag_context_chunks:
                        context_texts = [f"[{c.get('metadata', {}).get('filename', 'doc')} | Page {c.get('metadata', {}).get('page_number', 1)}]: {c.get('text', '')}" for c in rag_context_chunks]
                        context_block = "\n\n".join(context_texts)
                        full_prompt = (
                            f"DOCUMENT CONTEXT:\n{context_block}\n\n"
                            f"TASK:\n{prompt_task}\n\n"
                            f"Write a Python script to compute the result and print it clearly."
                        )
                    else:
                        full_prompt = f"TASK:\n{prompt_task}\n\nWrite a Python script that solves this and prints the output."

                    step.output = await self._call_llm(model_profile["runtime_model_name"], full_prompt, system_prompt=system_prompt)

                elif action == "execute_code":
                    if self.sandbox_service:
                        # Check if this is a retry step and previous execute_code had an error
                        previous_error = None
                        failing_code = None
                        for s in reversed(plan.steps[:plan.current_step_index]):
                            if s.capability == "coding" and s.status in ("REPLAN", "FAILED") and s.error:
                                previous_error = s.error
                                break
                        
                        raw_code_to_use = None
                        if previous_error:
                            # Re-prompt model with error feedback to fix code before execution
                            for s in reversed(plan.steps[:plan.current_step_index]):
                                if s.capability == "coding" and isinstance(s.output, str):
                                    failing_code = s.output
                                    break
                            
                            fix_prompt = (
                                f"The previous Python script failed execution in the sandbox with the following error:\n"
                                f"ERROR / STDERR:\n{previous_error}\n\n"
                                f"FAILING CODE:\n{failing_code or ''}\n\n"
                                f"ORIGINAL TASK:\n{plan.request}\n\n"
                                f"Fix the bug in the Python script. Provide the corrected, complete, working Python script inside a ```python ``` block."
                            )
                            system_prompt = (
                                "You are AEGIS Code Generator, an industrial on-premise AI coding assistant.\n"
                                "Generate ONLY clean, optimal, syntactically correct Python 3 code wrapped inside a ```python ``` markdown block.\n"
                                "CRITICAL: DO NOT add arbitrary or dummy print statements (e.g. print(0))."
                            )
                            corrected_raw = await self._call_llm(model_profile["runtime_model_name"], fix_prompt, system_prompt=system_prompt)
                            raw_code_to_use = corrected_raw
                        else:
                            for s in reversed(plan.steps[:plan.current_step_index]):
                                if s.capability == "coding" and s.output and isinstance(s.output, str):
                                    raw_code_to_use = s.output
                                    break

                        code = None
                        if raw_code_to_use:
                            if "```python" in raw_code_to_use:
                                code = raw_code_to_use.split("```python", 1)[1].split("```", 1)[0].strip()
                            elif "```" in raw_code_to_use:
                                code = raw_code_to_use.split("```", 1)[1].split("```", 1)[0].strip()
                            else:
                                code = raw_code_to_use.strip()

                        if not code:
                            step.error = "No executable Python code was generated by the local model."
                            step.status = "FAILED"
                            return False
                        
                        # Check for input files
                        input_files: Dict[str, Any] = {}
                        if isinstance(step.input, dict) and step.input.get("files"):
                            input_files.update(step.input["files"])
                        
                        # If a target document was classified in the plan, mount it
                        if plan.category == "CATEGORY_MIXED" and self.rag_service:
                            target_doc = getattr(plan, "target_doc", None)
                            if target_doc and target_doc.get("source_path") and os.path.exists(target_doc["source_path"]):
                                fname = target_doc.get("filename", os.path.basename(target_doc["source_path"]))
                                try:
                                    with open(target_doc["source_path"], "rb") as fh:
                                        input_files[fname] = fh.read()
                                except Exception as e:
                                    logger.warning(f"Could not mount document '{fname}' into sandbox: {e}")
                                
                        user_id = getattr(current_user, "id", None) if not isinstance(current_user, dict) else current_user.get("id")
                        username = getattr(current_user, "username", None) if not isinstance(current_user, dict) else current_user.get("username")
                        
                        res = self.sandbox_service.execute(
                            code=code,
                            files=input_files if input_files else None,
                            user_id=user_id,
                            username=username
                        )
                        step.output = res
                        if not res.get("success"):
                            step.error = res.get("stderr") or res.get("error") or "Sandbox code execution failed."
                            step.status = "FAILED"
                            return False
                    else:
                        step.output = "NOT_IMPLEMENTED: Sandbox service is unavailable."
                        step.status = "FAILED"
                        return False

            # -------------------------------------------------------------
            # TEXT GENERATION & REASONING CAPABILITY
            # -------------------------------------------------------------
            elif step.capability == "text_generation" or step.capability == "reasoning":
                action = step.input.get("action", "generate_text")

                # A. Specific Document RAG Search
                if action == "rag_search":
                    if self.rag_service:
                        query = step.input.get("query", "")
                        doc_id = step.input.get("document_id")
                        filter_meta = None
                        if current_user:
                            user_role = getattr(current_user, "role", None) if not isinstance(current_user, dict) else current_user.get("role")
                            user_id = getattr(current_user, "id", None) if not isinstance(current_user, dict) else current_user.get("id")
                            if user_role != "admin" and user_id is not None:
                                filter_meta = {"owner_id": user_id}
                        res = self.rag_service.search(query, top_k=5, filter_metadata=filter_meta, document_id=doc_id)
                        step.output = res
                    else:
                        step.output = "NOT_IMPLEMENTED: RAG service is unavailable."
                        step.status = "FAILED"
                        return False

                # B. Document-Wide Aggregation (Category C)
                elif action == "document_wide_analysis":
                    if not self.rag_service:
                        step.output = "NOT_IMPLEMENTED: RAG service is unavailable."
                        step.status = "FAILED"
                        return False

                    doc_id = step.input.get("document_id")
                    if not doc_id:
                        user_id = getattr(current_user, "id", None) if not isinstance(current_user, dict) else current_user.get("id")
                        user_role = getattr(current_user, "role", None) if not isinstance(current_user, dict) else current_user.get("role")
                        docs = self.rag_service.list_documents(owner_id=user_id, is_admin=(user_role == "admin"))
                        if docs:
                            doc_id = docs[0]["id"]

                    if not doc_id:
                        step.output = []
                    else:
                        chunks = self.rag_service.get_document_chunks(doc_id)
                        step.output = chunks

                # C. Synthesize Whole Document Summary (Category C)
                elif action == "synthesize_document_summary":
                    user_query = step.input.get("user_query") or plan.request
                    chunks = []
                    for s in reversed(plan.steps[:plan.current_step_index]):
                        if s.input and s.input.get("action") == "document_wide_analysis" and isinstance(s.output, list):
                            chunks = s.output
                            break

                    if not chunks:
                        step.output = "I could not find the target document in the knowledge base to summarize."
                    else:
                        # Group by page numbers
                        pages_dict = {}
                        doc_name = "Document"
                        for c in chunks:
                            meta = c.get("metadata", {})
                            doc_name = meta.get("filename") or meta.get("document_name") or doc_name
                            p_num = meta.get("page_number", 1)
                            if p_num not in pages_dict:
                                pages_dict[p_num] = []
                            pages_dict[p_num].append(c.get("text", ""))

                        structured_pages = []
                        for p_num in sorted(pages_dict.keys()):
                            p_text = "\n".join(pages_dict[p_num])
                            structured_pages.append(f"--- [Page {p_num}] ---\n{p_text}")

                        full_document_text = "\n\n".join(structured_pages)
                        
                        system_prompt = (
                            "You are AEGIS, a sovereign on-premise industrial AI document analysis assistant.\n"
                            "Your task is to provide an authoritative, coherent, and comprehensive document-level analysis.\n\n"
                            "MANDATORY GUIDELINES:\n"
                            "1. Synthesize the complete document logically into professional sections:\n"
                            "   - Executive Summary\n"
                            "   - Key Objectives & Problem Statement\n"
                            "   - Methodology & System Architecture\n"
                            "   - Implementation Details & Results\n"
                            "   - Conclusion\n"
                            "2. Use ONLY facts present in the provided document pages. Do not invent facts or extrapolate.\n"
                            "3. Include citations formatted as: [Source: <filename> | Page <page_number>].\n"
                            "4. End with a clean 'Sources' section listing the referenced pages."
                        )

                        # Context safety: truncate if exceeds 60,000 chars
                        safe_doc_text = full_document_text[:60000]
                        prompt = (
                            f"DOCUMENT: {doc_name}\n\n"
                            f"COMPLETE DOCUMENT TEXT BY PAGES:\n{safe_doc_text}\n\n"
                            f"USER REQUEST:\n{user_query}\n\n"
                            f"Provide a comprehensive, highly structured analysis of the entire document:"
                        )

                        step.output = await self._call_llm(model_profile["runtime_model_name"], prompt, system_prompt=system_prompt)

                # D. Generate Grounded Specific Answer (Category B)
                elif action == "generate_answer":
                    user_query = step.input.get("user_query") or plan.request
                    chunks = []
                    for s in reversed(plan.steps[:plan.current_step_index]):
                        if s.input and s.input.get("action") == "rag_search" and isinstance(s.output, list):
                            chunks = s.output
                            break

                    if not chunks:
                        step.output = "I could not find sufficient evidence in the indexed organizational documents to answer this question."
                    else:
                        sources_formatted = []
                        for chunk in chunks:
                            text_content = chunk.get("text", "")
                            meta = chunk.get("metadata", {})
                            doc_name = meta.get("filename") or meta.get("document_name") or "Unknown Document"
                            page_num = meta.get("page_number", 1)
                            chunk_header = f"[Source: {doc_name} | Page {page_num}]"
                            sources_formatted.append(f"{chunk_header}\n{text_content}")

                        context_str = "\n\n".join(sources_formatted)
                        
                        prompt = (
                            f"SYSTEM INSTRUCTIONS:\n"
                            f"You are AEGIS, a sovereign on-premise industrial AI assistant.\n"
                            f"Answer using the retrieved organizational context when available.\n"
                            f"Answer using ONLY the supplied document evidence below.\n\n"
                            f"MANDATORY RULES FOR DOCUMENT QUESTIONS:\n"
                            f"1. Answer using ONLY the supplied document evidence.\n"
                            f"2. Do not invent facts, infer unsupported details, or use outside knowledge to fill gaps.\n"
                            f"3. If the document does not contain enough information, state exactly:\n"
                            f"   'I could not find sufficient evidence in the indexed organizational documents to answer this question.'\n"
                            f"4. Format citations precisely as: [Source: <filename> | Page <page_number>].\n"
                            f"5. Synthesize a professional, coherent answer. Never dump raw disconnected excerpts.\n\n"
                            f"RETRIEVED KNOWLEDGE:\n{context_str}\n\n"
                            f"USER QUESTION:\n{user_query}\n\n"
                            f"Answer:"
                        )

                        step.output = await self._call_llm(model_profile["runtime_model_name"], prompt)

                # E. General Direct Text Generation (Category A)
                else:
                    prompt = step.input.get("prompt", plan.request)
                    system_prompt = (
                        "You are AEGIS, a sovereign on-premise AI assistant for enterprise and industrial engineering.\n"
                        "Provide accurate, clear, and direct responses to the user's inquiry."
                    )
                    step.output = await self._call_llm(model_profile["runtime_model_name"], prompt, system_prompt=system_prompt)
                    
            # -------------------------------------------------------------
            # VISION CAPABILITY
            # -------------------------------------------------------------
            elif step.capability == "vision" or step.capability == "multimodal":
                if self.ocr_service and step.input.get("action") == "ocr_pdf":
                    file_path = step.input.get("file_path", "")
                    res = self.ocr_service.ocr_pdf(file_path)
                    step.output = res
                else:
                    prompt = step.input.get("prompt", plan.request)
                    system_prompt = (
                        "You are AEGIS Vision & Multimodal Analyzer.\n"
                        "Analyze the visual diagram, scanned image, or engineering schematic and provide detailed technical findings.\n"
                        "Do not infer information that cannot be seen in the visual artifact."
                    )
                    
                    # Resolve visual image bytes if target file exists
                    images_b64 = []
                    target_file = step.input.get("file_path") or step.input.get("filename")
                    if not target_file and self.rag_service:
                        user_id = getattr(current_user, "id", None) if not isinstance(current_user, dict) else current_user.get("id")
                        user_role = getattr(current_user, "role", None) if not isinstance(current_user, dict) else current_user.get("role")
                        tdoc = self._find_referenced_document(plan.request, user_id=user_id, is_admin=(user_role == "admin"))
                        if tdoc:
                            target_file = tdoc.get("source_path") or tdoc.get("filename")

                    if target_file and os.path.exists(target_file):
                        import base64
                        ext = os.path.splitext(target_file)[1].lower()
                        if ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif"]:
                            with open(target_file, "rb") as f:
                                images_b64.append(base64.b64encode(f.read()).decode("utf-8"))
                        elif ext == ".pdf":
                            try:
                                import fitz
                                doc_pdf = fitz.open(target_file)
                                if len(doc_pdf) > 0:
                                    pix = doc_pdf[0].get_pixmap(dpi=150)
                                    images_b64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
                                doc_pdf.close()
                            except Exception as pe:
                                logger.warning(f"Failed to render PDF page for vision: {pe}")

                    step.output = await self._call_llm(
                        model_profile["runtime_model_name"],
                        prompt,
                        system_prompt=system_prompt,
                        images=images_b64 if images_b64 else None
                    )
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
        plan = self._create_plan(request, current_user=current_user)
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
                    plan.final_output = f"Execution halted: Step {step.step_id} failed and retry budget is exhausted. Cause: {step.error or 'Unknown step failure.'}"
                    break

        if plan.status == "RUNNING" and plan.current_step_index >= len(plan.steps):
            plan.status = "COMPLETED"
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
        model_used = getattr(self.loader_manager, "current_model_id", None) or "not reported"
        primary_routing = None
        any_switched = False

        if plan.steps:
            for s in plan.steps:
                if s.input and s.input.get("action") in ("rag_search", "document_wide_analysis") and s.output:
                    if isinstance(s.output, list) and len(s.output) > 0:
                        rag_used = True
                        for chunk in s.output:
                            meta = chunk.get("metadata", {})
                            sources.append({
                                "filename": meta.get("filename") or meta.get("document_name") or "Unknown Document",
                                "page": meta.get("page_number", 1),
                                "page_number": meta.get("page_number", 1),
                                "distance": round(chunk.get("distance", 0.0), 4) if "distance" in chunk else 0.0,
                                "similarity": chunk.get("similarity", 1.0)
                            })
                if s.selected_model:
                    model_used = s.selected_model
                if s.routing_decision:
                    if not primary_routing:
                        primary_routing = s.routing_decision
                    if s.routing_decision.get("switched"):
                        any_switched = True

        category_to_task_type = {
            "CATEGORY_A": "GENERAL_TEXT",
            "CATEGORY_B": "DOCUMENT_QA",
            "CATEGORY_C": "DOCUMENT_SUMMARY",
            "CATEGORY_D": "CALCULATION" if any(w in request.lower() for w in ["calculate", "compute", "factorial"]) else "CODING",
            "CATEGORY_MIXED": "CODING",
            "CATEGORY_OCR": "VISION_ANALYSIS"
        }
        derived_task_type = category_to_task_type.get(plan.category, "GENERAL_TEXT")

        routing_info = {
            "task_type": primary_routing.get("task_type") if primary_routing else derived_task_type,
            "selected_model": model_used,
            "routing": "automatic",
            "switched": any_switched,
            "reason": primary_routing.get("reason") if primary_routing else f"Automatically routed to {model_used} for {derived_task_type}",
            "required_capabilities": primary_routing.get("required_capabilities") if primary_routing else [],
            "matched_capabilities": primary_routing.get("matched_capabilities") if primary_routing else [],
            "rag_used": rag_used
        }

        # Inspect sandbox execution results if coding was performed
        sandbox_execution: Optional[Dict[str, Any]] = None
        code_str: str = ""
        for s in plan.steps:
            if s.capability == "coding" and s.input and s.input.get("action") == "generate_code" and isinstance(s.output, str):
                raw_out = s.output
                if "```python" in raw_out:
                    code_str = raw_out.split("```python", 1)[1].split("```", 1)[0].strip()
                elif "```" in raw_out:
                    code_str = raw_out.split("```", 1)[1].split("```", 1)[0].strip()
                else:
                    code_str = raw_out.strip()
            if s.capability == "coding" and s.input and s.input.get("action") == "execute_code" and isinstance(s.output, dict):
                sandbox_execution = s.output

        if sandbox_execution:
            sandbox_execution["code"] = code_str

        final_answer = plan.final_output
        if sandbox_execution:
            if sandbox_execution.get("success"):
                clean_stdout = sandbox_execution.get("stdout", "").strip()
                final_answer = f"```python\n{code_str}\n```\n\n**Sandbox Execution Output:**\n```\n{clean_stdout}\n```"
            else:
                clean_stderr = (sandbox_execution.get("stderr") or sandbox_execution.get("error") or "Execution failed.").strip()
                final_answer = f"```python\n{code_str}\n```\n\n**Sandbox Execution Failed (Exit code {sandbox_execution.get('exit_code', -1)}):**\n```\n{clean_stderr}\n```"
        elif isinstance(final_answer, dict):
            final_answer = json.dumps(final_answer)
        elif final_answer is None:
            final_answer = "Agent execution failed." if plan.status == "FAILED" else "Agent execution completed with no output."
        else:
            final_answer = str(final_answer)

        return {
            "success": plan.status == "COMPLETED",
            "answer": final_answer,
            "category": plan.category,
            "task_type": routing_info["task_type"],
            "rag_used": rag_used,
            "sources": sources,
            "model": model_used,
            "plan": plan.to_dict(),
            "duration_ms": total_duration_ms,
            "error": plan.final_output if plan.status == "FAILED" else None,
            "routing_info": routing_info,
            "sandbox_execution": sandbox_execution
        }
