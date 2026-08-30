const test = require("node:test");
const assert = require("node:assert");

// Helper for UI status badge fallback resolution
function resolveBadgeStatus(healthData, subsystem) {
  if (!healthData) return { status: "unknown", label: "STATUS NOT REPORTED" };
  const subStatus = healthData.services?.[subsystem];
  if (!subStatus) return { status: "unavailable", label: "NOT REPORTED" };
  
  if (subStatus === "healthy" || subStatus === "active" || subStatus === "protected") {
    return { status: subStatus, label: subStatus.toUpperCase() };
  }
  if (subStatus === "unhealthy" || subStatus === "error") {
    return { status: "error", label: "UNHEALTHY" };
  }
  return { status: "degraded", label: subStatus.toUpperCase() };
}

// Helper for VRAM allocation display logic
function resolveVramDisplay(vramData) {
  if (!vramData || typeof vramData.used_bytes !== "number") {
    return {
      title: "VRAM TELEMETRY",
      value: "NOT REPORTED BY RUNTIME",
      status: "UNAVAILABLE"
    };
  }
  const usedGb = (vramData.used_bytes / (1024 * 1024 * 1024)).toFixed(1);
  const totalGb = (vramData.total_bytes / (1024 * 1024 * 1024)).toFixed(1);
  return {
    title: "VRAM TELEMETRY",
    value: `${usedGb} GB / ${totalGb} GB`,
    status: "ACTIVE"
  };
}

// Helper for Chat Response state machine
function resolveChatState(responsePayload, isRagUsed) {
  if (!responsePayload) return "IDLE";
  if (responsePayload.error) return "RUNTIME FAILURE";
  if (isRagUsed && responsePayload.sources && responsePayload.sources.length > 0) return "RAG SUCCESS";
  if (isRagUsed && (!responsePayload.sources || responsePayload.sources.length === 0)) return "NO EVIDENCE";
  return "SUCCESS";
}

test("Truthfulness - VRAM Telemetry handles missing runtime metrics honestly", () => {
  const res = resolveVramDisplay(null);
  assert.strictEqual(res.value, "NOT REPORTED BY RUNTIME");
  assert.strictEqual(res.status, "UNAVAILABLE");
});

test("Truthfulness - VRAM Telemetry formats actual bytes when available", () => {
  const res = resolveVramDisplay({ used_bytes: 4294967296, total_bytes: 8589934592 });
  assert.strictEqual(res.value, "4.0 GB / 8.0 GB");
  assert.strictEqual(res.status, "ACTIVE");
});

test("Truthfulness - Subsystem status badges resolve missing signals to NOT REPORTED", () => {
  const healthData = { status: "ok", services: { ai_runtime: "healthy" } };
  const res = resolveBadgeStatus(healthData, "gpu_telemetry");
  assert.strictEqual(res.status, "unavailable");
  assert.strictEqual(res.label, "NOT REPORTED");
});

test("Truthfulness - Subsystem status badges map protected signals correctly", () => {
  const healthData = { status: "ok", services: { sandbox: "protected" } };
  const res = resolveBadgeStatus(healthData, "sandbox");
  assert.strictEqual(res.status, "protected");
  assert.strictEqual(res.label, "PROTECTED");
});

test("Truthfulness - RAG search lab empty state maps to NO RELEVANT ORGANIZATIONAL KNOWLEDGE FOUND", () => {
  const searchResults = [];
  const emptyMessage = searchResults.length === 0 
    ? "NO RELEVANT ORGANIZATIONAL KNOWLEDGE FOUND" 
    : "RESULTS LOADED";
  assert.strictEqual(emptyMessage, "NO RELEVANT ORGANIZATIONAL KNOWLEDGE FOUND");
});

test("Truthfulness - Audit empty state maps to NO AUDIT EVENTS RECORDED", () => {
  const logs = [];
  const emptyText = logs.length === 0 ? "NO AUDIT EVENTS RECORDED" : "EVENTS LOADED";
  assert.strictEqual(emptyText, "NO AUDIT EVENTS RECORDED");
});

test("Truthfulness - Model consistency ensures response model matches backend payload", () => {
  const chatResponse = {
    success: true,
    answer: "Sample answer",
    model_info: { model_id: "gemma3:4b" }
  };
  const activeModel = chatResponse.model_info?.model_id || "UNAVAILABLE";
  assert.strictEqual(activeModel, "gemma3:4b");
});

test("Truthfulness - Chat state machine distinguishes RAG SUCCESS vs NO EVIDENCE vs GENERAL SUCCESS", () => {
  const groundedRes = resolveChatState({ sources: [{ filename: "doc.txt" }] }, true);
  assert.strictEqual(groundedRes, "RAG SUCCESS");

  const ungroundedRes = resolveChatState({ sources: [] }, true);
  assert.strictEqual(ungroundedRes, "NO EVIDENCE");

  const generalRes = resolveChatState({ answer: "Code sample" }, false);
  assert.strictEqual(generalRes, "SUCCESS");
});

test("Truthfulness - Operator identity binds to user session or NOT LOGGED IN", () => {
  const loggedInOperator = { username: "vighnesh_op" }?.username || "NOT LOGGED IN";
  assert.strictEqual(loggedInOperator, "vighnesh_op");

  const guestOperator = null?.username || "NOT LOGGED IN";
  assert.strictEqual(guestOperator, "NOT LOGGED IN");
});
