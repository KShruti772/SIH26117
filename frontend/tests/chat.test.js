const test = require("node:test");
const assert = require("node:assert");

// 1. Simulated Input Validation Logic
function validatePrompt(prompt) {
  const trimmed = prompt.trim();
  if (!trimmed) {
    return { valid: false, error: "Empty prompt rejected." };
  }
  if (trimmed.length > 1000) {
    return { valid: false, error: "Prompt exceeds limit of 1000 characters." };
  }
  return { valid: true, text: trimmed };
}

// 2. Simulated Response Parser (chatApi return mapper)
function parseChatResponse(rawResponse) {
  return {
    success: !!rawResponse.success,
    answer: rawResponse.answer || "Agent execution failed.",
    sources: (rawResponse.sources || []).map(s => ({
      filename: s.filename || "Unknown Document",
      page_number: s.page_number || 1
    })),
    verification: rawResponse.verification || "PASS",
    request_id: rawResponse.request_id || "gen-id",
    duration_ms: rawResponse.duration_ms || 0
  };
}

// ==========================================
// TEST SCENARIOS
// ==========================================

test("Prompt Validation - Rejects empty inputs", () => {
  const res = validatePrompt("   ");
  assert.strictEqual(res.valid, false);
  assert.match(res.error, /Empty/);
});

test("Prompt Validation - Rejects oversized inputs", () => {
  const longPrompt = "a".repeat(1001);
  const res = validatePrompt(longPrompt);
  assert.strictEqual(res.valid, false);
  assert.match(res.error, /exceeds limit/);
});

test("Prompt Validation - Accepts valid prompt inputs and trims whitespace", () => {
  const res = validatePrompt("   valid query text   ");
  assert.strictEqual(res.valid, true);
  assert.strictEqual(res.text, "valid query text");
});

test("Response Parser - Maps success payloads, sources and verification tags", () => {
  const raw = {
    success: true,
    answer: "Safe response content",
    sources: [
      { filename: "safety_procedures.pdf", page_number: 3, raw_path: "/var/secret/path" }
    ],
    verification: "PASS (Score: 0.95)",
    request_id: "req-uuid-123",
    duration_ms: 120
  };

  const parsed = parseChatResponse(raw);
  
  assert.strictEqual(parsed.success, true);
  assert.strictEqual(parsed.answer, "Safe response content");
  assert.strictEqual(parsed.sources.length, 1);
  assert.strictEqual(parsed.sources[0].filename, "safety_procedures.pdf");
  assert.strictEqual(parsed.sources[0].raw_path, undefined, "Excludes absolute raw paths");
  assert.strictEqual(parsed.verification, "PASS (Score: 0.95)");
  assert.strictEqual(parsed.request_id, "req-uuid-123");
  assert.strictEqual(parsed.duration_ms, 120);
});

test("Response Parser - Handles failure outputs gracefully", () => {
  const raw = {
    success: false,
    answer: null,
    sources: [],
    verification: null,
    request_id: "failed-uuid",
    duration_ms: 5
  };

  const parsed = parseChatResponse(raw);
  assert.strictEqual(parsed.success, false);
  assert.strictEqual(parsed.answer, "Agent execution failed.");
});
