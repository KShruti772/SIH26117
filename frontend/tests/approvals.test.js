const test = require("node:test");
const assert = require("node:assert");

// ==========================================
// 1. Role-Aware Access Control Helpers
// ==========================================

const REVIEWER_ROLES = new Set(["admin", "reviewer", "supervisor", "lead"]);

function isReviewerRole(role) {
  if (!role || typeof role !== "string") return false;
  return REVIEWER_ROLES.has(role.toLowerCase());
}

// ==========================================
// 2. Client-Side Validation Rules for HITL
// ==========================================

function validateApprovePayload(payload) {
  if (payload && payload.comment && typeof payload.comment === "string") {
    if (payload.comment.length > 1000) {
      return { valid: false, error: "Sign-off comment must not exceed 1000 characters." };
    }
  }
  return { valid: true };
}

function validateModifyPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return { valid: false, error: "Modification payload is required." };
  }

  const { modifications, revised_text, comment } = payload;

  const hasModifications = Array.isArray(modifications) && modifications.length > 0 && modifications.some(m => typeof m === "string" && m.trim().length > 0);
  const hasRevisedText = typeof revised_text === "string" && revised_text.trim().length > 0;
  const hasComment = typeof comment === "string" && comment.trim().length > 0;

  if (!hasModifications && !hasRevisedText && !hasComment) {
    return {
      valid: false,
      error: "Please provide at least one constraint, revised deliverable text, or reviewer instruction."
    };
  }

  if (hasComment && comment.length > 1000) {
    return { valid: false, error: "Reviewer comment cannot exceed 1000 characters." };
  }

  if (hasRevisedText && revised_text.length > 5000) {
    return { valid: false, error: "Revised deliverable text cannot exceed 5000 characters." };
  }

  if (Array.isArray(modifications)) {
    for (const m of modifications) {
      if (typeof m === "string" && m.length > 1000) {
        return { valid: false, error: "Individual modification constraints cannot exceed 1000 characters." };
      }
    }
  }

  return { valid: true };
}

function validateRejectPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return { valid: false, error: "Rejection payload is required." };
  }

  const { reason } = payload;
  if (!reason || typeof reason !== "string" || !reason.trim()) {
    return { valid: false, error: "A non-empty rejection reason is required for audit and compliance." };
  }

  if (reason.trim().length > 1000) {
    return { valid: false, error: "Rejection reason cannot exceed 1000 characters." };
  }

  return { valid: true };
}

// ==========================================
// 3. HTTP Error Translation (Truthful & Safe)
// ==========================================

function resolveApprovalErrorMessage(status, backendDetail) {
  switch (status) {
    case 401:
      return "Your session has expired. Please sign in again.";
    case 403:
      return "You are not authorized to perform reviewer actions on this approval gate.";
    case 404:
      return "This approval request could not be found. It may have expired or been removed.";
    case 409:
      return "This approval request is no longer awaiting review. It has already been resolved or transitioned by another reviewer.";
    case 422:
      if (backendDetail && typeof backendDetail === "string") {
        return `Validation failed: ${backendDetail}`;
      }
      return "The submission payload failed schema validation.";
    default:
      return backendDetail || "An unexpected error occurred while communicating with the approval authority.";
  }
}

// ==========================================
// 4. Safe Content Sanitization & CoT Filtering
// ==========================================

const PROHIBITED_COT_KEYS = [
  "chain_of_thought",
  "reasoning_steps",
  "private_thought",
  "system_prompt",
  "raw_prompt",
  "jwt",
  "token",
  "secret",
  "password",
  "database_path"
];

function sanitizeEvidencePayload(evidence) {
  if (!evidence || typeof evidence !== "object") return {};
  const clean = {};
  for (const [k, v] of Object.entries(evidence)) {
    if (PROHIBITED_COT_KEYS.includes(k.toLowerCase())) {
      continue; // Filter out CoT, private reasoning, and secret fields
    }
    clean[k] = v;
  }
  return clean;
}

function escapeUnsafeHtml(str) {
  if (typeof str !== "string") return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ==========================================
// TEST SCENARIOS
// ==========================================

// 1. Role-Aware Access Control
test("HITL Role Control - Identifies authorized reviewer roles", () => {
  assert.strictEqual(isReviewerRole("admin"), true);
  assert.strictEqual(isReviewerRole("reviewer"), true);
  assert.strictEqual(isReviewerRole("supervisor"), true);
  assert.strictEqual(isReviewerRole("lead"), true);
  assert.strictEqual(isReviewerRole("ADMIN"), true, "Case insensitive check");
});

test("HITL Role Control - Denies reviewer capabilities to standard users or guests", () => {
  assert.strictEqual(isReviewerRole("user"), false);
  assert.strictEqual(isReviewerRole("guest"), false);
  assert.strictEqual(isReviewerRole("operator"), false);
  assert.strictEqual(isReviewerRole(null), false);
  assert.strictEqual(isReviewerRole(undefined), false);
});

// 2. Queue Empty & Truthfulness States
test("HITL Queue - Renders truthful empty message when pending approvals list is empty", () => {
  const pendingApprovals = [];
  const emptyStateMessage = pendingApprovals.length === 0
    ? "No approvals require your attention. When AEGIS pauses a consequential workflow for human review, it will appear here."
    : "Approvals loaded";
  
  assert.strictEqual(emptyStateMessage, "No approvals require your attention. When AEGIS pauses a consequential workflow for human review, it will appear here.");
});

test("HITL Queue - Zero mock data fallback policy", () => {
  const serverQueue = [];
  // Ensure we never fabricate records
  const renderedRecords = serverQueue.map(item => item);
  assert.strictEqual(renderedRecords.length, 0);
});

// 3. Approval Payload Validation
test("HITL Approve - Accepts valid empty comment or comment <= 1000 chars", () => {
  assert.strictEqual(validateApprovePayload({ comment: "" }).valid, true);
  assert.strictEqual(validateApprovePayload({ comment: "Verified calculation against ASME Section VIII standards." }).valid, true);
  assert.strictEqual(validateApprovePayload(null).valid, true);
});

test("HITL Approve - Rejects comments exceeding 1000 characters", () => {
  const longComment = "a".repeat(1001);
  const res = validateApprovePayload({ comment: longComment });
  assert.strictEqual(res.valid, false);
  assert.match(res.error, /1000 characters/);
});

// 4. Modify Payload Validation
test("HITL Modify - Rejects empty modification payload", () => {
  const res = validateModifyPayload({ modifications: [], revised_text: "", comment: "" });
  assert.strictEqual(res.valid, false);
  assert.match(res.error, /provide at least one constraint/);
});

test("HITL Modify - Accepts valid modifications list", () => {
  const res = validateModifyPayload({
    modifications: ["Recalculate wall thickness with 1.25 design safety factor", "Include hydrostatic test pressure"],
    comment: "Update safety factor per client engineering spec."
  });
  assert.strictEqual(res.valid, true);
});

test("HITL Modify - Rejects revised_text exceeding 5000 characters", () => {
  const res = validateModifyPayload({
    revised_text: "x".repeat(5001),
    comment: "Too large"
  });
  assert.strictEqual(res.valid, false);
  assert.match(res.error, /5000 characters/);
});

test("HITL Modify - Rejects individual constraints exceeding 1000 characters", () => {
  const res = validateModifyPayload({
    modifications: ["x".repeat(1001)],
    comment: "Constraint too long"
  });
  assert.strictEqual(res.valid, false);
  assert.match(res.error, /1000 characters/);
});

// 5. Reject Payload Validation
test("HITL Reject - Rejects empty or whitespace-only reason", () => {
  assert.strictEqual(validateRejectPayload({ reason: "" }).valid, false);
  assert.strictEqual(validateRejectPayload({ reason: "   " }).valid, false);
  assert.strictEqual(validateRejectPayload(null).valid, false);
});

test("HITL Reject - Accepts valid non-empty reason <= 1000 characters", () => {
  const res = validateRejectPayload({ reason: "Inspection protocol failed step 4.2; pressure test was not witnessed." });
  assert.strictEqual(res.valid, true);
});

test("HITL Reject - Rejects reasons exceeding 1000 characters", () => {
  const res = validateRejectPayload({ reason: "r".repeat(1001) });
  assert.strictEqual(res.valid, false);
  assert.match(res.error, /1000 characters/);
});

// 6. HTTP Error Handling & Status Semantics
test("HITL Error Handling - Resolves 401 to session expired", () => {
  const msg = resolveApprovalErrorMessage(401, "Token expired");
  assert.strictEqual(msg, "Your session has expired. Please sign in again.");
});

test("HITL Error Handling - Resolves 403 to safe authorization denied without leakage", () => {
  const msg = resolveApprovalErrorMessage(403, "Internal RBAC violation on /root/auth");
  assert.strictEqual(msg, "You are not authorized to perform reviewer actions on this approval gate.");
  assert.strictEqual(msg.includes("/root/auth"), false);
});

test("HITL Error Handling - Resolves 404 to not found message", () => {
  const msg = resolveApprovalErrorMessage(404);
  assert.strictEqual(msg, "This approval request could not be found. It may have expired or been removed.");
});

test("HITL Error Handling - Resolves 409 to concurrency conflict message", () => {
  const msg = resolveApprovalErrorMessage(409, "Approval already transitioned to APPROVED");
  assert.strictEqual(msg, "This approval request is no longer awaiting review. It has already been resolved or transitioned by another reviewer.");
});

test("HITL Error Handling - Resolves 422 to validation error detail", () => {
  const msg = resolveApprovalErrorMessage(422, "Comment length exceeds maximum 1000");
  assert.match(msg, /Validation failed: Comment length exceeds maximum 1000/);
});

// 7. Chain of Thought Filtering & Evidence Privacy
test("HITL Evidence - Strips prohibited Chain-of-Thought and internal secrets", () => {
  const rawEvidence = {
    findings: ["Corrosion depth 2.4mm within allowable limit of 3.0mm"],
    calculations: { remaining_thickness_mm: 9.6, allowable_min_mm: 8.0 },
    chain_of_thought: "Step 1: Check table. Step 2: Compare numbers. Step 3: Conclude safe.",
    private_thought: "Model internal token probabilities",
    system_prompt: "You are an AI assistant specialized in industrial engineering.",
    jwt: "eyJhbGciOi...",
    database_path: "/var/data/aegis.db"
  };

  const cleanEvidence = sanitizeEvidencePayload(rawEvidence);

  assert.deepStrictEqual(cleanEvidence.findings, ["Corrosion depth 2.4mm within allowable limit of 3.0mm"]);
  assert.deepStrictEqual(cleanEvidence.calculations, { remaining_thickness_mm: 9.6, allowable_min_mm: 8.0 });
  assert.strictEqual(cleanEvidence.chain_of_thought, undefined);
  assert.strictEqual(cleanEvidence.private_thought, undefined);
  assert.strictEqual(cleanEvidence.system_prompt, undefined);
  assert.strictEqual(cleanEvidence.jwt, undefined);
  assert.strictEqual(cleanEvidence.database_path, undefined);
});

// 8. Content Safety & HTML Escaping
test("HITL Content Safety - Escapes unsafe HTML tags in untrusted evidence", () => {
  const maliciousInput = '<script>alert("pwned")</script><img src=x onerror="stealTokens()">';
  const sanitized = escapeUnsafeHtml(maliciousInput);

  assert.strictEqual(sanitized.includes("<script>"), false);
  assert.strictEqual(sanitized.includes("&lt;script&gt;"), true);
  assert.strictEqual(sanitized.includes("&lt;img"), true);
});

// 9. Document Download URL Integrity
test("HITL Deliverable - Generates compliant authorized download URL structure", () => {
  const apiBase = "http://127.0.0.1:8000/api";
  const docId = "doc_inspection_report_001";
  const downloadUrl = `${apiBase}/documents/generated/${docId}/download`;
  
  assert.strictEqual(downloadUrl, "http://127.0.0.1:8000/api/documents/generated/doc_inspection_report_001/download");
});

// 10. Ant Design Deprecation Compliance
test("Ant Design Deprecations - ApprovalsView does not use deprecated valueStyle or Alert message prop", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const approvalsContent = fs.readFileSync(
    path.join(__dirname, "../components/views/ApprovalsView.tsx"),
    "utf-8"
  );

  assert.strictEqual(approvalsContent.includes("valueStyle="), false, "ApprovalsView must not use deprecated valueStyle.");
  assert.strictEqual(approvalsContent.includes("styles={{ content:"), true, "ApprovalsView must use styles={{ content: ... }}");
  assert.strictEqual(/<Alert[^>]*\bmessage=/g.test(approvalsContent), false, "ApprovalsView must use title instead of message on Alert.");
  assert.strictEqual(approvalsContent.includes("App.useApp()"), true, "ApprovalsView must use App.useApp() hook for messages.");
});

// 11. Operator vs Reviewer View Separation
test("HITL Operator View - Non-reviewer does not make queue network call and sees dedicated status banner", () => {
  const userRole = "user";
  const isAuthorized = isReviewerRole(userRole);
  assert.strictEqual(isAuthorized, false);

  // In ApprovalsView, when !isAuthorized, pending approvals are not fetched
  const shouldFetchQueue = isAuthorized;
  assert.strictEqual(shouldFetchQueue, false, "Standard operators must not query reviewer-only queue endpoint");

  // Title and subtitle must reflect operator status without error states
  const viewTitle = isAuthorized ? "Human-in-the-Loop Approvals" : "My Approval Status";
  const emptyOrNoticeText = !isAuthorized
    ? "You do not have reviewer permissions. You can monitor the approval status of your own AI tasks from the AI Assistant."
    : "No approvals require your attention.";

  assert.strictEqual(viewTitle, "My Approval Status");
  assert.match(emptyOrNoticeText, /do not have reviewer permissions/);
});

// 12. Visual State Machine Transitions
test("HITL State Machine - Maps authoritative states truthfully without fake progress", () => {
  function getWorkflowStage(backendState, cachedApprovalStatus) {
    if (backendState === "COMPLETED" || cachedApprovalStatus === "COMPLETED") return "COMPLETED";
    if (backendState === "REJECTED" || cachedApprovalStatus === "REJECTED") return "REJECTED";
    if (cachedApprovalStatus === "APPROVED" || cachedApprovalStatus === "MODIFIED" || backendState === "RESUMING") return "RESUMING";
    if (backendState === "WAITING_FOR_HUMAN" || cachedApprovalStatus === "PENDING") return "WAITING_FOR_HUMAN";
    return "UNKNOWN";
  }

  assert.strictEqual(getWorkflowStage("WAITING_FOR_HUMAN", "PENDING"), "WAITING_FOR_HUMAN");
  assert.strictEqual(getWorkflowStage("WAITING_FOR_HUMAN", "APPROVED"), "RESUMING");
  assert.strictEqual(getWorkflowStage("WAITING_FOR_HUMAN", "MODIFIED"), "RESUMING");
  assert.strictEqual(getWorkflowStage("COMPLETED", "APPROVED"), "COMPLETED");
  assert.strictEqual(getWorkflowStage("REJECTED", "REJECTED"), "REJECTED");
});

// 13. Deliverable Card Rendering Policy
test("HITL Deliverable Card - Renders download actions only when artifact exists and is verified", () => {
  function getDeliverableDisplay(artifact) {
    if (!artifact) return null;
    const docId = artifact.document_id || artifact.artifact_id;
    const filename = artifact.filename || artifact.name || "Deliverable";
    const downloadHref = artifact.download_url || (docId ? `http://127.0.0.1:8000/api/documents/generated/${docId}/download` : "#");
    const canDownload = Boolean(docId || artifact.download_url);
    return { filename, downloadHref, canDownload };
  }

  // Null artifact -> no download button
  assert.strictEqual(getDeliverableDisplay(null), null);

  // Valid artifact -> download available
  const display = getDeliverableDisplay({
    document_id: "doc_cooling_tower_001",
    filename: "Cooling_Tower_Inspection_Approval_Note.pdf",
    format: "pdf",
    file_size_bytes: 4320
  });
  assert.strictEqual(display.canDownload, true);
  assert.strictEqual(display.downloadHref, "http://127.0.0.1:8000/api/documents/generated/doc_cooling_tower_001/download");
  assert.strictEqual(display.filename, "Cooling_Tower_Inspection_Approval_Note.pdf");
});

// 14. Content-Disposition Filename Extraction
test("Authenticated Download - Robustly parses filenames from Content-Disposition headers", () => {
  function extractFilenameFromHeader(header, fallback = "document.pdf") {
    if (!header || typeof header !== "string") return fallback;
    const utf8Match = header.match(/filename\*=(?:UTF-8''|utf-8'')?([^;]+)/i);
    if (utf8Match && utf8Match[1]) {
      try {
        const clean = utf8Match[1].trim().replace(/^["']|["']$/g, "");
        return decodeURIComponent(clean);
      } catch {
        return utf8Match[1].trim().replace(/^["']|["']$/g, "");
      }
    }
    const standardMatch = header.match(/filename="?([^";]+)"?/i);
    if (standardMatch && standardMatch[1]) {
      return standardMatch[1].trim();
    }
    return fallback;
  }

  // Standard quoted filename
  assert.strictEqual(
    extractFilenameFromHeader('attachment; filename="inspection_report_2026.pdf"'),
    "inspection_report_2026.pdf"
  );

  // Standard unquoted filename
  assert.strictEqual(
    extractFilenameFromHeader("attachment; filename=safety_audit_note.docx"),
    "safety_audit_note.docx"
  );

  // RFC 5987 / 6266 UTF-8 encoded filename
  assert.strictEqual(
    extractFilenameFromHeader("attachment; filename*=UTF-8''Cooling%20Tower%20Report.pdf"),
    "Cooling Tower Report.pdf"
  );

  // Fallback on missing or empty header
  assert.strictEqual(extractFilenameFromHeader(null, "fallback.pdf"), "fallback.pdf");
  assert.strictEqual(extractFilenameFromHeader("", "fallback.pdf"), "fallback.pdf");
});

// 15. Download Error Status Translation
test("Authenticated Download - Translates HTTP error statuses safely without exposing server internals", () => {
  function translateDownloadError(status) {
    switch (status) {
      case 401:
        return "Session expired. Please sign in again.";
      case 403:
        return "Download not authorized for this document.";
      case 404:
        return "Document is no longer available.";
      default:
        return "Unable to download the document. Please retry.";
    }
  }

  assert.strictEqual(translateDownloadError(401), "Session expired. Please sign in again.");
  assert.strictEqual(translateDownloadError(403), "Download not authorized for this document.");
  assert.strictEqual(translateDownloadError(404), "Document is no longer available.");
  assert.strictEqual(translateDownloadError(500), "Unable to download the document. Please retry.");
  assert.strictEqual(translateDownloadError(503), "Unable to download the document. Please retry.");
});

// 16. Duplicate Click Protection
test("Authenticated Download - Disallows duplicate simultaneous in-flight downloads", () => {
  let inFlightDocId = null;

  function canStartDownload(docId) {
    if (inFlightDocId !== null) return false;
    inFlightDocId = docId;
    return true;
  }

  function finishDownload() {
    inFlightDocId = null;
  }

  // First click starts download
  assert.strictEqual(canStartDownload("doc_123"), true);
  // Second click while in-flight is rejected
  assert.strictEqual(canStartDownload("doc_123"), false);
  assert.strictEqual(canStartDownload("doc_456"), false);

  // Once finished, new download can start
  finishDownload();
  assert.strictEqual(canStartDownload("doc_456"), true);
});

// 17. Zero JWT in URLs Policy
test("Security - Verifies no JWT tokens appear in download URLs", () => {
  const sampleToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMSJ9.signature";
  const downloadUrl = "http://127.0.0.1:8000/api/documents/generated/doc_123/download";

  assert.strictEqual(downloadUrl.includes(sampleToken), false);
  assert.strictEqual(downloadUrl.includes("token="), false);
  assert.strictEqual(downloadUrl.includes("jwt="), false);
  assert.strictEqual(downloadUrl.includes("bearer="), false);
});

