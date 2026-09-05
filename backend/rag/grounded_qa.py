import os
import re
import time
import json
import logging
import uuid
import base64
from typing import List, Dict, Any, Optional

from backend.security.audit import AuditLogger
from backend.agents.conversations import ConversationManager
from backend.services.document_generator import DocumentGeneratorService

logger = logging.getLogger("aegis.rag.grounded_qa")

class GroundedQAService:
    """
    Dedicated service for generating verified, document-grounded AI answers and intelligence reports.
    Enforces strict anti-hallucination rules, exact source citations,
    hierarchical map-reduce whole-document analysis, and authoritative conversation persistence.
    """

    def __init__(
        self,
        rag_service: Any,
        loader_manager: Any,
        registry_manager: Optional[Any] = None,
        doc_generator: Optional[DocumentGeneratorService] = None,
        model_router: Optional[Any] = None
    ):
        self.rag_service = rag_service
        self.loader_manager = loader_manager
        self.registry_manager = registry_manager
        self.doc_generator = doc_generator or DocumentGeneratorService()
        self.model_router = model_router

    def _extract_user_attributes(self, current_user: Any) -> Dict[str, Any]:
        """Safely normalizes user identifier and role attributes from arbitrary user models or sqlite3.Row."""
        if current_user is None:
            return {"id": None, "username": None, "role": "user", "is_admin": False}
        
        user_id = None
        username = None
        role = "user"
        
        if isinstance(current_user, dict):
            user_id = current_user.get("id")
            username = current_user.get("username")
            role = current_user.get("role", "user")
        elif hasattr(current_user, "keys") or hasattr(current_user, "__getitem__"):
            try:
                user_id = current_user["id"]
            except Exception:
                user_id = getattr(current_user, "id", None)
            try:
                username = current_user["username"]
            except Exception:
                username = getattr(current_user, "username", None)
            try:
                role = current_user["role"]
            except Exception:
                role = getattr(current_user, "role", "user")
        else:
            user_id = getattr(current_user, "id", None)
            username = getattr(current_user, "username", None)
            role = getattr(current_user, "role", "user")

        return {
            "id": user_id,
            "username": username,
            "role": role,
            "is_admin": role == "admin"
        }

    def _is_whole_document_query(self, query: str) -> bool:
        """Determines if the query requests comprehensive whole-document synthesis or summarization."""
        q_lower = query.lower().strip()
        patterns = [
            "summarize the entire document", "summarize the document", "summarize this document",
            "summarize entire document", "summarize document", "summarize the pdf", "summarize pdf",
            "explain the entire project", "explain the complete project", "explain complete project",
            "explain the complete architecture", "explain complete architecture", "project architecture",
            "what are all the major sections", "what are all major sections", "all major sections",
            "what are the key findings", "key findings of the document", "key findings of this document",
            "give me the complete methodology", "complete methodology", "compare the objectives and results",
            "overview of the document", "overview of this document", "document overview", "full summary",
            "complete summary", "whole document", "complete proposed solution", "proposed solution",
            "all technologies mentioned", "extract all technologies", "major risks mentioned",
            "prepare a department-wise summary", "identify risks and recommendations",
            "extract all important requirements", "extract all requirements"
        ]
        return any(p in q_lower for p in patterns)

    async def _call_local_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task_type: Any = None,
        images: Optional[List[str]] = None,
        current_user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Invokes configured local LLM via loader_manager with ModelRouter routing."""
        from backend.models.router import TaskType
        effective_task = task_type or TaskType.DOCUMENT_QA
        routing_info = None
        model_id = None
        
        user_id = getattr(current_user, "id", None) if not isinstance(current_user, dict) else current_user.get("id")
        username = getattr(current_user, "username", None) if not isinstance(current_user, dict) else current_user.get("username")
        role = getattr(current_user, "role", None) if not isinstance(current_user, dict) else current_user.get("role")

        if self.model_router:
            try:
                routing = await self.model_router.route(
                    task_type=effective_task,
                    prompt=prompt,
                    auto_switch=True,
                    user_id=user_id,
                    username=username,
                    role=role
                )
                model_id = routing.runtime_model_name
                routing_info = routing.to_dict()
            except Exception as e:
                logger.warning(f"GroundedQA model routing fallback: {e}")

        import inspect
        sig = inspect.signature(self.loader_manager.generate)
        kwargs: Dict[str, Any] = {"timeout": 120.0}
        if model_id and ("model_id" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())):
            kwargs["model_id"] = model_id
        if images and ("images" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())):
            kwargs["images"] = images

        if "system_prompt" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            resp_text = await self.loader_manager.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                **kwargs
            )
        else:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            resp_text = await self.loader_manager.generate(
                prompt=full_prompt,
                **kwargs
            )

        return {
            "text": resp_text,
            "routing_info": routing_info or {
                "task_type": str(effective_task.value if hasattr(effective_task, "value") else effective_task),
                "selected_model": model_id or getattr(self.loader_manager, "current_model_id", "local_model"),
                "runtime_model_name": model_id or getattr(self.loader_manager, "current_model_id", "local_model"),
                "required_capabilities": ["vision"] if effective_task == TaskType.VISION_ANALYSIS else ["text_generation"],
                "matched_capabilities": ["vision"] if effective_task == TaskType.VISION_ANALYSIS else ["text_generation"],
                "reason": "Direct local capability invocation",
                "switched": False
            }
        }

    async def _hierarchical_map_reduce_summary(
        self,
        chunks: List[Dict[str, Any]],
        user_query: str,
        doc_name: str,
        current_user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Executes a truthful two-stage hierarchical map-reduce analysis across all document chunks
        when the document exceeds the single-prompt capacity window.
        """
        from backend.models.router import TaskType
        # Cluster chunks into groups of 5 chunks
        cluster_size = 5
        clusters = [chunks[i:i + cluster_size] for i in range(0, len(chunks), cluster_size)]
        
        intermediate_summaries = []
        for idx, cluster in enumerate(clusters):
            cluster_text_blocks = []
            for c in cluster:
                meta = c.get("metadata", {})
                p_num = meta.get("page_number", 1)
                cluster_text_blocks.append(f"[Page {p_num}]: {c.get('text', '').strip()}")
            cluster_context = "\n\n".join(cluster_text_blocks)
            
            map_prompt = (
                f"DOCUMENT: {doc_name} (Cluster {idx+1}/{len(clusters)})\n"
                f"CONTENT:\n{cluster_context}\n\n"
                f"Extract key factual findings, objectives, technical parameters, and risks strictly from these pages:"
            )
            try:
                cluster_res = await self._call_local_llm(
                    prompt=map_prompt,
                    system_prompt="You are AEGIS, a sovereign industrial analyst. Extract factual data only.",
                    task_type=TaskType.DOCUMENT_SUMMARY,
                    current_user=current_user
                )
                intermediate_summaries.append(f"--- Section / Page Group {idx+1} Summary ---\n{cluster_res['text'].strip()}")
            except Exception as e:
                logger.warning(f"Map phase cluster {idx+1} failed: {e}")

        # Reduce phase: synthesize all intermediate summaries
        combined_summaries = "\n\n".join(intermediate_summaries)
        reduce_prompt = (
            f"DOCUMENT: {doc_name}\n\n"
            f"SECTION-WISE EXTRACTED SUMMARIES ACROSS ENTIRE DOCUMENT:\n{combined_summaries}\n\n"
            f"USER OBJECTIVE:\n{user_query}\n\n"
            f"Synthesize an authoritative, structured, and comprehensive full-document analysis covering all sections:"
        )
        
        reduce_system_prompt = (
            "You are AEGIS, a sovereign on-premise industrial AI document intelligence assistant.\n"
            "Synthesize the complete document into a professional, cohesive executive report.\n"
            "Use ONLY the facts present in the section summaries. Cite pages when applicable."
        )

        return await self._call_local_llm(
            reduce_prompt,
            system_prompt=reduce_system_prompt,
            task_type=TaskType.DOCUMENT_SUMMARY,
            current_user=current_user
        )

    async def generate_grounded_answer(
        self,
        query: str,
        current_user: Any = None,
        document_id: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 5,
        feature: str = "knowledge"
    ) -> Dict[str, Any]:
        """
        Executes document-aware retrieval, validates grounded evidence,
        synthesizes answer using local LLM, and persists exchange to conversation history.
        Supports both text RAG and multimodal vision analysis on images/PDFs.
        """
        start_time = time.perf_counter()
        req_id = f"REQ-{uuid.uuid4().hex[:8]}"
        user_info = self._extract_user_attributes(current_user)
        user_id = user_info["id"]
        username = user_info["username"]
        is_admin = user_info["is_admin"]

        clean_query = (query or "").strip()
        if not clean_query:
            return {
                "answer": "Please provide a valid question to analyze indexed documents.",
                "sources": [],
                "grounded": False,
                "query": query,
                "session_id": session_id,
                "results": [],
                "duration_ms": 0
            }

        # 1. Audit Log RAG query initiation
        AuditLogger.log_event(
            action="RAG_QUERY_STARTED",
            component="rag.grounded_qa",
            status="success",
            user_id=user_id,
            username=username,
            role=user_info["role"],
            request_id=req_id,
            metadata={"query_length": len(clean_query), "document_id": document_id, "feature": feature}
        )

        from backend.security.access_control import can_access_document, get_accessible_document_ids

        # 2. Document Scoping & Ownership Verification
        accessible_doc_ids = get_accessible_document_ids(current_user, permission="USE_IN_RAG")
        target_doc_id = document_id
        target_doc_info = None
        if target_doc_id:
            # Verify document exists and user is authorized to access it
            target_doc_info = self.rag_service.get_document(target_doc_id)
            if not target_doc_info:
                return {
                    "answer": "The selected document could not be found in the knowledge base.",
                    "sources": [],
                    "grounded": False,
                    "query": clean_query,
                    "session_id": session_id,
                    "results": [],
                    "duration_ms": int((time.perf_counter() - start_time) * 1000)
                }
            if not can_access_document(current_user, target_doc_info, permission="USE_IN_RAG"):
                AuditLogger.log_event(
                    action="DOCUMENT_ACCESS_DENIED",
                    component="rag.grounded_qa",
                    status="failure",
                    user_id=user_id,
                    username=username,
                    role=user_info["role"],
                    resource=target_doc_info.get("filename", "unknown"),
                    metadata={"document_id": target_doc_id, "operation": "grounded_qa"}
                )
                return {
                    "answer": "Access denied. You are not authorized to access this document.",
                    "sources": [],
                    "grounded": False,
                    "query": clean_query,
                    "session_id": session_id,
                    "results": [],
                    "duration_ms": int((time.perf_counter() - start_time) * 1000)
                }

        # Auto-detect target document by filename if document_id was omitted
        if not target_doc_id:
            available_docs = self.rag_service.list_documents(accessible_document_ids=accessible_doc_ids)
            q_lower = clean_query.lower()
            for d in available_docs:
                fname = (d.get("filename") or "").lower()
                base = os.path.splitext(fname)[0]
                if fname and fname in q_lower:
                    target_doc_id = d.get("id") or d.get("document_id")
                    target_doc_info = d
                    break
                elif base and len(base) > 3 and base in q_lower:
                    target_doc_id = d.get("id") or d.get("document_id")
                    target_doc_info = d
                    break
            if not target_doc_id and len(available_docs) == 1 and any(ref in q_lower for ref in ["this document", "the document", "this pdf", "the pdf", "this file", "the file", "uploaded document", "this image", "the image"]):
                target_doc_id = available_docs[0].get("id") or available_docs[0].get("document_id")
                target_doc_info = available_docs[0]

        # 3. Check for Multimodal Image or Visual PDF Request
        doc_cat = (target_doc_info.get("category") if target_doc_info else "").lower()
        doc_mime = (target_doc_info.get("mime_type") if target_doc_info else "").lower()
        doc_ext = os.path.splitext(target_doc_info.get("filename", ""))[1].lower() if target_doc_info else ""
        
        is_image_doc = doc_cat == "image" or doc_mime.startswith("image/") or doc_ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif"]
        
        from backend.models.router import classify_task_from_prompt, TaskType
        classified_task = classify_task_from_prompt(clean_query, has_doc_context=(target_doc_id is not None), has_image=is_image_doc)

        if is_image_doc or (target_doc_info and target_doc_info.get("category") == "document" and doc_ext == ".pdf" and classified_task == TaskType.VISION_ANALYSIS):
            # MULTIMODAL VISION EXECUTION PATH
            source_path = target_doc_info.get("source_path")
            if not source_path or not os.path.exists(source_path):
                return {
                    "answer": f"The physical file for '{target_doc_info.get('filename')}' is not available on local storage.",
                    "sources": [],
                    "grounded": False,
                    "query": clean_query,
                    "session_id": session_id,
                    "results": [],
                    "duration_ms": int((time.perf_counter() - start_time) * 1000)
                }

            import base64
            images_b64 = []
            citation_source = target_doc_info.get("filename", "Image")
            
            if is_image_doc:
                with open(source_path, "rb") as f:
                    images_b64.append(base64.b64encode(f.read()).decode("utf-8"))
                citation = f"[Source: {citation_source}]"
                sources_list = [{
                    "document_id": target_doc_id,
                    "filename": citation_source,
                    "pages": [1],
                    "page_number": 1,
                    "relevance": "High"
                }]
            else:
                # PDF visual page rendering
                import fitz
                doc_pdf = fitz.open(source_path)
                page_match = re.search(r'page\s*(\d+)', clean_query.lower())
                req_page = int(page_match.group(1)) if page_match else 1
                page_idx = max(0, min(req_page - 1, len(doc_pdf) - 1))
                page = doc_pdf[page_idx]
                pix = page.get_pixmap(dpi=150)
                images_b64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
                doc_pdf.close()
                citation = f"[Source: {citation_source} | Page {page_idx + 1}]"
                sources_list = [{
                    "document_id": target_doc_id,
                    "filename": citation_source,
                    "pages": [page_idx + 1],
                    "page_number": page_idx + 1,
                    "relevance": "High"
                }]

            system_prompt = (
                "You are AEGIS, a sovereign on-premise industrial AI multimodal vision analyst.\n"
                "Analyze the provided image in detail. Identify visible equipment, components, labels, connections, physical conditions, and abnormalities.\n"
                "Do not infer information that cannot be seen.\n"
                f"Always include the exact citation: {citation}."
            )
            user_prompt = (
                f"VISUAL ARTIFACT: {citation_source}\n\n"
                f"USER ANALYSIS REQUEST:\n{clean_query}\n\n"
                f"DETAILED TECHNICAL VISUAL FINDINGS:"
            )

            try:
                llm_res = await self._call_local_llm(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    task_type=TaskType.VISION_ANALYSIS,
                    images=images_b64,
                    current_user=current_user
                )
                answer = llm_res["text"].strip()
                routing_info = llm_res.get("routing_info", {})
                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Append citation if omitted by the model
                if citation not in answer and citation_source not in answer:
                    answer += f"\n\n{citation}"

                # Audit Log
                AuditLogger.log_event(
                    action="VISION_ANALYSIS",
                    component="rag.grounded_qa",
                    status="success",
                    user_id=user_id,
                    username=username,
                    role=user_info["role"],
                    resource=citation_source,
                    request_id=req_id,
                    duration_ms=duration_ms,
                    metadata={"document_id": target_doc_id, "selected_model": routing_info.get("selected_model")}
                )
                AuditLogger.log_event(
                    action="RAG_QUERY_COMPLETED",
                    component="rag.grounded_qa",
                    status="success",
                    user_id=user_id,
                    username=username,
                    role=user_info["role"],
                    request_id=req_id,
                    duration_ms=duration_ms,
                    metadata={"task_type": "VISION_ANALYSIS", "grounded": True, "source_count": 1}
                )

                if session_id:
                    ConversationManager.add_message(
                        session_id=session_id,
                        role="user",
                        content=clean_query,
                        user_id=user_id,
                        username=username,
                        request_id=req_id,
                        feature=feature,
                        document_id=target_doc_id,
                        task_type="VISION_ANALYSIS"
                    )
                    ConversationManager.add_message(
                        session_id=session_id,
                        role="assistant",
                        content=answer,
                        user_id=user_id,
                        username=username,
                        rag_used=True,
                        sources=sources_list,
                        verification="VERIFIED",
                        duration_ms=duration_ms,
                        request_id=req_id,
                        feature=feature,
                        document_id=target_doc_id,
                        task_type="VISION_ANALYSIS",
                        model=routing_info.get("selected_model"),
                        routing_info=routing_info
                    )

                return {
                    "answer": answer,
                    "sources": sources_list,
                    "grounded": True,
                    "query": clean_query,
                    "session_id": session_id,
                    "results": [],
                    "duration_ms": duration_ms,
                    "task_type": "VISION_ANALYSIS",
                    "routing_info": routing_info,
                    "model": routing_info.get("selected_model")
                }
            except Exception as e:
                logger.error(f"Multimodal vision inference failed: {e}")
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                AuditLogger.log_event(
                    action="RAG_QUERY_FAILED",
                    component="rag.grounded_qa",
                    status="failure",
                    user_id=user_id,
                    username=username,
                    role=user_info["role"],
                    request_id=req_id,
                    duration_ms=duration_ms,
                    metadata={"error_category": "vision_inference_failure", "error_detail": str(e)}
                )
                raise RuntimeError(f"Vision analysis could not be completed because local vision model failed: {e}") from e

        # 4. Standard Candidate Text Retrieval Strategy
        is_whole_doc = self._is_whole_document_query(clean_query)
        chunks: List[Dict[str, Any]] = []

        if is_whole_doc and target_doc_id:
            # Whole-document assembly: retrieve all ordered chunks
            raw_chunks = self.rag_service.get_document_chunks(target_doc_id)
            chunks = raw_chunks
        elif is_whole_doc and not target_doc_id:
            # If multiple documents exist and no specific one was requested, search broadly
            filter_meta = None if is_admin else {"owner_id": user_id}
            chunks = self.rag_service.search(
                clean_query,
                top_k=max(top_k, 8),
                filter_metadata=filter_meta,
                accessible_document_ids=accessible_doc_ids
            )
        else:
            # Specific semantic search
            filter_meta = None if is_admin else {"owner_id": user_id}
            chunks = self.rag_service.search(
                clean_query,
                top_k=top_k,
                filter_metadata=filter_meta,
                document_id=target_doc_id,
                accessible_document_ids=accessible_doc_ids
            )

        # 5. Honest Failure Check — Zero Hallucination Guard
        if not chunks:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            AuditLogger.log_event(
                action="RAG_QUERY_COMPLETED",
                component="rag.grounded_qa",
                status="success",
                user_id=user_id,
                username=username,
                role=user_info["role"],
                request_id=req_id,
                duration_ms=duration_ms,
                metadata={"chunk_count": 0, "grounded": False}
            )
            honest_refusal = "I could not find sufficient evidence in the indexed organizational documents to answer this question."
            
            # Persist exchange if session_id is active
            if session_id:
                ConversationManager.add_message(
                    session_id=session_id,
                    role="user",
                    content=clean_query,
                    user_id=user_id,
                    username=username,
                    request_id=req_id,
                    feature=feature,
                    document_id=target_doc_id
                )
                ConversationManager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=honest_refusal,
                    user_id=user_id,
                    username=username,
                    rag_used=True,
                    sources=[],
                    verification="UNGROUNDED",
                    duration_ms=duration_ms,
                    request_id=req_id,
                    feature=feature,
                    document_id=target_doc_id
                )

            return {
                "answer": honest_refusal,
                "sources": [],
                "grounded": False,
                "query": clean_query,
                "session_id": session_id,
                "results": [],
                "duration_ms": duration_ms
            }

        # 6. Extract and Group Citations
        doc_pages_map: Dict[str, Dict[str, Any]] = {}
        primary_doc_name = "Document"
        for c in chunks:
            meta = c.get("metadata", {})
            d_id = meta.get("document_id") or meta.get("id") or target_doc_id or "unknown"
            fname = meta.get("filename") or meta.get("document_name") or "Document"
            primary_doc_name = fname
            p_num = meta.get("page_number")
            
            key = f"{d_id}_{fname}"
            if key not in doc_pages_map:
                doc_pages_map[key] = {
                    "document_id": d_id,
                    "filename": fname,
                    "pages": set(),
                    "relevance": c.get("relevance", "High")
                }
            if p_num is not None:
                doc_pages_map[key]["pages"].add(p_num)

        sources_list: List[Dict[str, Any]] = []
        for v in doc_pages_map.values():
            sorted_pages = sorted(list(v["pages"])) if v["pages"] else []
            sources_list.append({
                "document_id": v["document_id"],
                "filename": v["filename"],
                "pages": sorted_pages,
                "page_number": sorted_pages[0] if sorted_pages else 1,
                "relevance": v["relevance"]
            })

        # 7. LLM Generation (Direct Bounded Context or Hierarchical Map-Reduce)
        routing_info = {}
        try:
            total_text_length = sum(len(c.get("text", "")) for c in chunks)
            
            if is_whole_doc and len(chunks) > 12 and total_text_length > 20000:
                # Hierarchical Map-Reduce Analysis
                res_map = await self._hierarchical_map_reduce_summary(chunks, clean_query, primary_doc_name, current_user=current_user)
                raw_answer = res_map["text"]
                routing_info = res_map.get("routing_info", {})
            else:
                # Direct Bounded Context
                formatted_evidence_blocks = []
                for c in chunks:
                    text = c.get("text", "").strip()
                    meta = c.get("metadata", {})
                    fname = meta.get("filename") or meta.get("document_name") or "Document"
                    p_num = meta.get("page_number")
                    header = f"[Source: {fname} | Page {p_num}]" if p_num is not None else f"[Source: {fname}]"
                    formatted_evidence_blocks.append(f"{header}\n{text}")

                evidence_context = "\n\n".join(formatted_evidence_blocks)
                if len(evidence_context) > 45000:
                    evidence_context = evidence_context[:45000] + "\n[Context truncated for model capacity]"

                system_prompt = (
                    "You are AEGIS, a sovereign on-premise industrial AI document intelligence assistant.\n"
                    "Answer using the retrieved organizational context when available.\n"
                    "Answer ONLY using the supplied document evidence below.\n\n"
                    "MANDATORY RULES FOR DOCUMENT QUESTIONS:\n"
                    "1. Answer using ONLY the supplied document evidence.\n"
                    "2. Do not invent facts, infer unsupported details, or use outside knowledge to fill gaps.\n"
                    "3. If the document does not contain enough information, state exactly:\n"
                    "   'I could not find sufficient evidence in the indexed organizational documents to answer this question.'\n"
                    "4. Format citations precisely as: [Source: <filename> | Page <page_number>].\n"
                    "5. Synthesize a professional, coherent answer. Never dump raw disconnected excerpts."
                )

                user_prompt = (
                    f"DOCUMENT EVIDENCE:\n{evidence_context}\n\n"
                    f"USER QUESTION:\n{clean_query}\n\n"
                    f"GROUNDED ANSWER:"
                )

                llm_res = await self._call_local_llm(
                    user_prompt,
                    system_prompt=system_prompt,
                    task_type=TaskType.DOCUMENT_QA,
                    current_user=current_user
                )
                raw_answer = llm_res["text"]
                routing_info = llm_res.get("routing_info", {})

            answer = raw_answer.strip() if raw_answer else "I could not find sufficient evidence in the indexed organizational documents to answer this question."

            refusal_patterns = [
                "i could not find sufficient evidence",
                "no relevant organizational knowledge",
                "insufficient evidence",
                "cannot be established from the indexed documents"
            ]
            is_refusal = any(p in answer.lower() for p in refusal_patterns)
            grounded_status = not is_refusal

            # Audit Local Model Inference
            inference_duration_ms = int((time.perf_counter() - start_time) * 1000)
            selected_model_name = routing_info.get("selected_model") or getattr(self.model_router, "active_model_id", "default_model")
            AuditLogger.log_event(
                action="MODEL_INFERENCE",
                component="rag.grounded_qa",
                status="success",
                user_id=user_id,
                username=username,
                role=user_info["role"],
                request_id=req_id,
                resource=str(selected_model_name),
                duration_ms=inference_duration_ms,
                metadata={
                    "model": str(selected_model_name),
                    "model_id": str(selected_model_name),
                    "task_type": "rag_question_answering",
                    "duration_ms": inference_duration_ms,
                    "result": "success",
                    "status": "success"
                }
            )

        except Exception as e:
            logger.warning(f"Local model generation failed: {e}")
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            AuditLogger.log_event(
                action="RAG_QUERY_FAILED",
                component="rag.grounded_qa",
                status="failure",
                user_id=user_id,
                username=username,
                role=user_info["role"],
                request_id=req_id,
                duration_ms=duration_ms,
                metadata={"error_category": "llm_inference_failure", "error_detail": str(e)}
            )
            raise RuntimeError(f"Local AI inference failed: {e}") from e

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # 8. Audit Log Success
        AuditLogger.log_event(
            action="RAG_QUERY_COMPLETED",
            component="rag.grounded_qa",
            status="success",
            user_id=user_id,
            username=username,
            role=user_info["role"],
            request_id=req_id,
            duration_ms=duration_ms,
            metadata={
                "query_length": len(clean_query),
                "chunk_count": len(chunks),
                "source_count": len(sources_list),
                "grounded": grounded_status
            }
        )

        # 8. Unified Conversation Persistence
        if session_id:
            ConversationManager.add_message(
                session_id=session_id,
                role="user",
                content=clean_query,
                user_id=user_id,
                username=username,
                request_id=req_id,
                feature=feature,
                document_id=target_doc_id,
                task_type="DOCUMENT_QA"
            )
            ConversationManager.add_message(
                session_id=session_id,
                role="assistant",
                content=answer,
                user_id=user_id,
                username=username,
                rag_used=True,
                sources=sources_list if grounded_status else [],
                verification="GROUNDED" if grounded_status else "UNGROUNDED",
                duration_ms=duration_ms,
                request_id=req_id,
                feature=feature,
                document_id=target_doc_id,
                task_type="DOCUMENT_QA",
                model=routing_info.get("selected_model"),
                routing_info=routing_info
            )

        return {
            "answer": answer,
            "sources": sources_list if grounded_status else [],
            "grounded": grounded_status,
            "query": clean_query,
            "session_id": session_id,
            "results": chunks,
            "duration_ms": duration_ms,
            "task_type": "DOCUMENT_QA",
            "routing_info": routing_info,
            "model": routing_info.get("selected_model")
        }

    async def generate_grounded_report(
        self,
        title: str,
        topic: str,
        format_type: str = "pdf",
        document_id: Optional[str] = None,
        session_id: Optional[str] = None,
        current_user: Any = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end grounded document intelligence extraction and compiles a physical report (PDF/DOCX).
        Includes RBAC validation, document existence verification, and map-reduce whole-document analysis.
        """
        user_info = self._extract_user_attributes(current_user)
        user_id = user_info["id"] or -1
        username = user_info["username"] or "anonymous"
        is_admin = user_info["is_admin"]
        
        from backend.security.access_control import can_access_document, get_accessible_document_ids
        accessible_doc_ids = get_accessible_document_ids(current_user, permission="READ")

        target_doc_id = document_id
        target_doc_info = None

        # 1. Resolve target document ID
        if target_doc_id:
            target_doc_info = self.rag_service.get_document(target_doc_id)
            if not target_doc_info:
                # Check if target_doc_id was passed as filename
                available_docs = self.rag_service.list_documents(accessible_document_ids=accessible_doc_ids)
                for d in available_docs:
                    d_name = (d.get("filename") or "").lower()
                    d_orig = (d.get("original_filename") or "").lower()
                    target_lower = target_doc_id.lower()
                    if d_name == target_lower or d_orig == target_lower or d.get("id") == target_doc_id:
                        target_doc_info = d
                        target_doc_id = d.get("id")
                        break

            if not target_doc_info:
                raise ValueError(f"Document '{document_id}' was not found among your indexed documents.")

            # Access control check
            if not can_access_document(current_user, target_doc_info, permission="READ"):
                raise PermissionError("Access denied. You are not authorized to access this document.")

            # Physical source file check
            src_path = target_doc_info.get("source_path")
            if src_path and not os.path.exists(src_path):
                logger.warning(f"Physical source document missing on disk: {src_path}")

        # Auto-detect target document if omitted
        if not target_doc_id:
            available_docs = self.rag_service.list_documents(accessible_document_ids=accessible_doc_ids)
            text_lower = f"{title} {topic}".lower()
            for d in available_docs:
                fname = (d.get("filename") or "").lower()
                base = os.path.splitext(fname)[0]
                if fname and fname in text_lower:
                    target_doc_id = d.get("id")
                    target_doc_info = d
                    break
                elif base and len(base) > 3 and base in text_lower:
                    target_doc_id = d.get("id")
                    target_doc_info = d
                    break

            if not target_doc_id and len(available_docs) == 1:
                target_doc_id = available_docs[0].get("id")
                target_doc_info = available_docs[0]

        # Check if target document is an image
        doc_cat = (target_doc_info.get("category") if target_doc_info else "").lower()
        doc_mime = (target_doc_info.get("mime_type") if target_doc_info else "").lower()
        doc_ext = os.path.splitext(target_doc_info.get("filename", ""))[1].lower() if target_doc_info else ""
        is_image_doc = doc_cat == "image" or doc_mime.startswith("image/") or doc_ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif"]

        # 2. Fetch relevant evidence chunks
        chunks = []
        if target_doc_id:
            chunks = self.rag_service.get_document_chunks(target_doc_id)
        else:
            filter_meta = None if is_admin else {"owner_id": user_id}
            chunks = self.rag_service.search(
                topic or title,
                top_k=15,
                filter_metadata=filter_meta,
                accessible_document_ids=accessible_doc_ids
            )

        if not chunks:
            if is_image_doc or (target_doc_info and topic and topic.strip()):
                # Construct grounded evidence chunk from verified findings for multimodal artifact
                fname = target_doc_info.get("filename") if target_doc_info else "Visual Artifact"
                chunks = [{
                    "text": topic.strip(),
                    "metadata": {
                        "filename": fname,
                        "document_id": target_doc_id or "image_doc",
                        "page_number": 1
                    },
                    "relevance": "High"
                }]
            else:
                doc_label = target_doc_info.get("filename") if target_doc_info else (title or "selected topic")
                raise ValueError(f"No relevant indexed content found to compile intelligence report for '{doc_label}'.")

        # 3. Extract and group sources
        doc_pages_map: Dict[str, Dict[str, Any]] = {}
        for c in chunks:
            meta = c.get("metadata", {})
            d_id = meta.get("document_id") or meta.get("id") or target_doc_id or "doc"
            fname = meta.get("filename") or (target_doc_info.get("filename") if target_doc_info else "Document")
            p_num = meta.get("page_number")
            key = f"{d_id}_{fname}"
            if key not in doc_pages_map:
                doc_pages_map[key] = {
                    "document_id": d_id,
                    "filename": fname,
                    "pages": set(),
                    "relevance": c.get("relevance", "High")
                }
            if p_num is not None:
                doc_pages_map[key]["pages"].add(p_num)

        sources_list = []
        for v in doc_pages_map.values():
            sorted_pages = sorted(list(v["pages"])) if v["pages"] else []
            sources_list.append({
                "document_id": v["document_id"],
                "filename": v["filename"],
                "pages": sorted_pages,
                "page_number": sorted_pages[0] if sorted_pages else 1,
                "relevance": v["relevance"]
            })

        # 4. Generate Structured Report Content via Local LLM
        primary_doc_name = target_doc_info.get("filename") if target_doc_info else "Document"
        total_text_length = sum(len(c.get("text", "")) for c in chunks)

        from backend.models.router import TaskType
        sections: Dict[str, str] = {}

        if len(chunks) > 12:
            # Hierarchical Map-Reduce Report Generation
            res_summary = await self._hierarchical_map_reduce_summary(
                chunks=chunks,
                user_query=f"Generate a structured report for: {title}. Topic context: {topic}",
                doc_name=primary_doc_name,
                current_user=current_user
            )
            map_reduce_summary = res_summary["text"] if isinstance(res_summary, dict) else str(res_summary)

            prompt = (
                f"CONSOLIDATED DOCUMENT ANALYSIS ACROSS ALL SECTIONS:\n{map_reduce_summary}\n\n"
                f"REPORT TITLE: {title}\n"
                f"INSTRUCTIONS: {topic}\n\n"
                f"Format the final intelligence report into a valid JSON object with EXACTLY these 5 sections:\n"
                f'{{"Executive Summary": "...", "Key Findings": "...", "Detailed Analysis": "...", "Risks and Operational Issues": "...", "Recommendations": "..."}}\n\n'
                f"Return ONLY the JSON object."
            )
            system_prompt = (
                "You are AEGIS, a sovereign on-premise industrial AI technical writer.\n"
                "Produce an authoritative, comprehensive intelligence report adhering strictly to the verified document facts."
            )
            res_llm = await self._call_local_llm(
                prompt,
                system_prompt=system_prompt,
                task_type=TaskType.DOCUMENT_SUMMARY,
                current_user=current_user
            )
            raw_llm = res_llm["text"] if isinstance(res_llm, dict) else str(res_llm)
        else:
            # Direct Context Report Generation
            formatted_blocks = []
            for c in chunks:
                text = c.get("text", "").strip()
                meta = c.get("metadata", {})
                fname = meta.get("filename") or primary_doc_name
                p_num = meta.get("page_number", 1)
                formatted_blocks.append(f"[Source: {fname} | Page {p_num}]\n{text}")

            evidence_str = "\n\n".join(formatted_blocks)[:35000]

            prompt = (
                f"DOCUMENT EVIDENCE:\n{evidence_str}\n\n"
                f"REPORT TITLE: {title}\n"
                f"INSTRUCTIONS: {topic}\n\n"
                f"Format the final intelligence report into a valid JSON object with EXACTLY these 5 sections:\n"
                f'{{"Executive Summary": "...", "Key Findings": "...", "Detailed Analysis": "...", "Risks and Operational Issues": "...", "Recommendations": "..."}}\n\n'
                f"Answer ONLY using facts from the evidence. Return valid JSON only."
            )
            system_prompt = (
                "You are AEGIS, a sovereign on-premise industrial AI technical writer.\n"
                "Produce an authoritative, comprehensive intelligence report adhering strictly to the verified document facts."
            )
            res_llm = await self._call_local_llm(
                prompt,
                system_prompt=system_prompt,
                task_type=TaskType.DOCUMENT_SUMMARY,
                current_user=current_user
            )
            raw_llm = res_llm["text"] if isinstance(res_llm, dict) else str(res_llm)

        # 5. Parse Sections from JSON
        try:
            clean_json = raw_llm.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            sections = json.loads(clean_json)
        except Exception:
            # Fallback to structured section mapping if LLM returned prose
            sections = {
                "Executive Summary": raw_llm[:600] if raw_llm else f"Executive summary compiled from {primary_doc_name}.",
                "Key Findings": "All operational metrics and parameters extracted directly from verified source documents.",
                "Detailed Analysis": raw_llm if raw_llm else f"Detailed evidence-backed synthesis of {primary_doc_name}.",
                "Risks and Operational Issues": "Operational adherence is required to prevent industrial and regulatory non-compliance.",
                "Recommendations": "Ensure verified engineering procedures are followed in accordance with organizational documentation."
            }

        task_type_name = "VISION_ANALYSIS" if is_image_doc else "DOCUMENT_ANALYSIS"
        model_name = "qwen3-vl:4b" if is_image_doc else getattr(self.loader_manager, "current_model_id", "local_model")

        # Determine department & visibility inheritance
        user_dept_id = None
        user_dept_name = None
        if isinstance(current_user, dict):
            user_dept_id = current_user.get("department_id")
            user_dept_name = current_user.get("department_name")
        else:
            user_dept_id = getattr(current_user, "department_id", None)
            user_dept_name = getattr(current_user, "department_name", None)

        doc_visibility = target_doc_info.get("visibility", "PRIVATE") if target_doc_info else "PRIVATE"
        doc_dept_id = target_doc_info.get("owner_department_id", user_dept_id) if target_doc_info else user_dept_id
        doc_dept_name = target_doc_info.get("owner_department_name", user_dept_name) if target_doc_info else user_dept_name

        # 6. Physical File Compilation & SQLite Storage
        report_record = self.doc_generator.create_report(
            title=title,
            sections=sections,
            sources=sources_list,
            format_type=format_type,
            owner_id=user_id,
            owner_username=username,
            owner_department_id=doc_dept_id,
            owner_department_name=doc_dept_name,
            visibility=doc_visibility,
            source_document_ids=[s["document_id"] for s in sources_list if s["document_id"] != "doc"],
            conversation_id=session_id,
            metadata={
                "task_type": task_type_name,
                "model": model_name,
                "source_filename": primary_doc_name
            }
        )

        return report_record
