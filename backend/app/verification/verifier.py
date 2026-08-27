import os
import re
import logging
import time
from typing import List, Dict, Any, Optional, Callable

logger = logging.getLogger("aegis.verifier")
logger.setLevel(logging.INFO)

class VerificationError(Exception):
    """Base exception for verifier operations."""
    pass

class VerificationEvidence:
    """Represents a grounded evidence segment extracted from RAG retrieval metadata."""
    
    def __init__(self, source: str, page_number: int, chunk_id: str, text: str):
        self.source = source
        self.page_number = page_number
        self.chunk_id = chunk_id
        self.text = text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "page_number": self.page_number,
            "chunk_id": self.chunk_id,
            "text": self.text
        }

class VerificationResult:
    """Represents the outcome of a grounding check run."""
    
    def __init__(
        self,
        passed: bool,
        score: float,
        reasons: List[str],
        evidence: List[VerificationEvidence],
        missing_evidence: List[str],
        citation_count: int
    ):
        self.passed = passed
        self.score = score
        self.reasons = reasons
        self.evidence = evidence
        self.missing_evidence = missing_evidence
        self.citation_count = citation_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "reasons": self.reasons,
            "evidence": [e.to_dict() for e in self.evidence],
            "missing_evidence": self.missing_evidence,
            "citation_count": self.citation_count
        }

class GroundingVerifier:
    """
    Evaluates whether generated agent output is deterministically supported by retrieved RAG evidence.
    
    ---------------------------------------------------------------------------
    DISCLAIMER:
    ---------------------------------------------------------------------------
    This MVP verifier checks grounding/evidence consistency. It does NOT prove
    semantic factual correctness of arbitrary text.
    ---------------------------------------------------------------------------
    """
    
    def __init__(self, safe_directories: Optional[List[str]] = None, min_pass_score: float = 0.7):
        self.safe_directories = [os.path.abspath(d) for d in (safe_directories or [os.getcwd()])]
        self.min_pass_score = min_pass_score

    def _validate_safe_path(self, path: str) -> bool:
        """Enforces that evidence source files live strictly inside safe workspace folders."""
        abs_path = os.path.abspath(path)
        return any(abs_path.startswith(d) for d in self.safe_directories)

    def parse_citations(self, text: str) -> List[Dict[str, Any]]:
        """
        Parses structured citations from the generated answer.
        Format expected: [source: filename.pdf, page: 4, chunk: chunk_id]
        """
        pattern = r"\[source:\s*([^,\]]+),\s*page:\s*(\d+),\s*chunk:\s*([^\]]+)\]"
        matches = re.findall(pattern, text, re.IGNORECASE)
        citations = []
        for m in matches:
            citations.append({
                "source": m[0].strip(),
                "page": int(m[1]),
                "chunk_id": m[2].strip()
            })
        return citations

    def verify(self, output: str, rag_results: List[Dict[str, Any]]) -> VerificationResult:
        """Evaluates alignment between output text citations and RAG retrieved document chunks."""
        start_time = time.perf_counter()
        reasons = []
        evidence_list = []
        missing_evidence = []
        
        # 1. Parse citations from output
        citations = self.parse_citations(output)
        citation_count = len(citations)
        
        # 2. Extract and validate RAG grounding evidence metadata
        for chunk in rag_results:
            meta = chunk.get("metadata", {})
            source_path = meta.get("source_path")
            
            # Enforce path security
            if source_path and not self._validate_safe_path(source_path):
                reasons.append(f"Security violation: evidence path lies outside safe boundaries: '{source_path}'")
                logger.error("Verifier: Security violation. Path escape detected.")
                
                from backend.security.audit import AuditLogger
                AuditLogger.log_event(
                    action="VERIFICATION",
                    component="app.verification.verifier",
                    status="failure",
                    metadata={"error_category": "security_violation"}
                )
                
                return VerificationResult(
                    passed=False,
                    score=0.0,
                    reasons=reasons,
                    evidence=[],
                    missing_evidence=[],
                    citation_count=citation_count
                )
                
            evidence_list.append(VerificationEvidence(
                source=meta.get("filename", ""),
                page_number=meta.get("page_number", 0),
                chunk_id=meta.get("chunk_id", ""),
                text=chunk.get("text", "")
            ))
            
        # Scoring metrics
        avail_score = 0.0
        presence_score = 0.0
        valid_score = 0.0
        overlap_score = 0.0
        
        # Check A: Evidence exists (Max 0.2 points)
        if len(rag_results) > 0:
            avail_score = 0.2
        else:
            reasons.append("Grounding error: No grounding evidence chunks retrieved from vector store.")
            
        # Check B: Citation presence in text (Max 0.2 points)
        if citation_count > 0:
            presence_score = 0.2
        else:
            reasons.append("Grounding warning: Generated output does not contain any bracket source citations.")
            
        # Check C: Citation validity (Max 0.3 points)
        if citation_count > 0 and len(rag_results) > 0:
            invalid_citations = []
            for cit in citations:
                matched = False
                for chunk in rag_results:
                    meta = chunk.get("metadata", {})
                    # Direct check: verify citation coordinates map back to a RAG result
                    if (meta.get("filename") == cit["source"] and
                        meta.get("page_number") == cit["page"] and
                        meta.get("chunk_id") == cit["chunk_id"]):
                        matched = True
                        break
                if not matched:
                    invalid_citations.append(f"[{cit['source']}:{cit['page']}:{cit['chunk_id']}]")
                    
            if invalid_citations:
                reasons.append(f"Grounding error: Citations reference ungrounded source coordinates: {', '.join(invalid_citations)}")
                missing_evidence.extend(invalid_citations)
                valid_score = 0.0
            else:
                valid_score = 0.3
        elif citation_count == 0 and len(rag_results) > 0:
            reasons.append("Grounding error: Vector evidence was retrieved but not cited in output.")
            
        # Check D: Textual overlap / grounding ratio (Max 0.3 points)
        if len(rag_results) > 0 and output.strip():
            # Lowercase alphanumeric token overlap check
            out_words = set(re.findall(r"\w+", output.lower()))
            evidence_text = " ".join(chunk.get("text", "") for chunk in rag_results).lower()
            ev_words = set(re.findall(r"\w+", evidence_text))
            
            if out_words:
                overlap_ratio = len(out_words.intersection(ev_words)) / len(out_words)
                overlap_score = min(0.3, overlap_ratio * 0.3)
                
                if overlap_ratio < 0.2:
                    reasons.append(f"Grounding error: Output text has low word overlap with evidence ({overlap_ratio:.2f} ratio).")
            else:
                overlap_score = 0.0
                
        # Total composite score
        score = round(avail_score + presence_score + valid_score + overlap_score, 2)
        passed = (score >= self.min_pass_score) and (not any("Security violation" in r for r in reasons))
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        if passed:
            reasons.append(f"Verification passed: Output is grounded in retrieval sources (Score: {score:.2f}).")
        else:
            reasons.append(f"Verification failed: Insufficient grounding score (Score: {score:.2f} < Min: {self.min_pass_score:.2f}).")
            
        # Safe logging (exclude actual prompts/contents)
        logger.info(
            f"Verifier Result: Passed={passed} "
            f"Score={score} "
            f"Citations={citation_count} "
            f"Duration={duration_ms}ms"
        )
        
        from backend.security.audit import AuditLogger
        AuditLogger.log_event(
            action="VERIFICATION",
            component="app.verification.verifier",
            status="success" if passed else "failure",
            duration_ms=duration_ms,
            metadata={
                "score": score,
                "citation_count": citation_count,
                "duration_ms": duration_ms,
                "reasons": "; ".join(reasons) if not passed else None
            }
        )
        
        return VerificationResult(
            passed=passed,
            score=score,
            reasons=reasons,
            evidence=evidence_list,
            missing_evidence=missing_evidence,
            citation_count=citation_count
        )

def make_grounding_verify_callback(verifier: GroundingVerifier) -> Callable[[Any, Any], bool]:
    """Factory creating an AgentController-compatible verify_callback hook."""
    
    def callback(plan: Any, step: Any) -> bool:
        # Grounding check only applies to generate_answer actions in RAG sequence
        if step.capability == "text_generation" and step.input.get("action") == "generate_answer":
            # Retrieve RAG results from the preceding step in the plan
            rag_results = []
            if plan.current_step_index > 0:
                prev_step = plan.steps[plan.current_step_index - 1]
                if prev_step.input.get("action") == "rag_search" and isinstance(prev_step.output, list):
                    rag_results = prev_step.output
            
            output_text = str(step.output)
            res = verifier.verify(output_text, rag_results)
            
            # Format verification result detail string
            step.verification_result = f"PASS (Score: {res.score})" if res.passed else f"FAIL (Score: {res.score})"
            return res.passed
        return True
        
    return callback
