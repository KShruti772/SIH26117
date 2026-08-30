const test = require("node:test");
const assert = require("node:assert");

// 1. Model Profile Discovery Mapper
function mapModelProfile(raw) {
  return {
    model_id: raw.model_id || raw.name || "unknown",
    display_name: raw.display_name || raw.name || "Unknown Model",
    runtime_model_name: raw.runtime_model_name || raw.name || "unknown",
    provider: raw.provider || "Ollama",
    runtime: "LOCAL",
    status: raw.status || "INSTALLED",
    is_installed: raw.is_installed ?? true,
    is_active: raw.is_active ?? false,
    parameter_size: raw.parameter_size || "4B",
    quantization: raw.quantization || "Q4_K_M",
    format: raw.format || "gguf",
    family: raw.family || "gemma3"
  };
}

// 2. Test Inference Result Parser
function parseTestInferenceResult(raw) {
  return {
    status: raw.status === "PASS" ? "PASS" : "FAIL",
    model: raw.model || "gemma3:4b",
    latency_ms: typeof raw.latency_ms === "number" ? raw.latency_ms : 0,
    response: raw.response || raw.error || "No response."
  };
}

test("Model Profile Mapper - Maps discovered Ollama model tags", () => {
  const raw = {
    name: "gemma3:4b",
    display_name: "Gemma 3 4B",
    runtime_model_name: "gemma3:4b",
    provider: "Google",
    status: "ACTIVE",
    is_active: true,
    parameter_size: "4.3B",
    quantization: "Q4_K_M"
  };

  const mapped = mapModelProfile(raw);
  assert.strictEqual(mapped.model_id, "gemma3:4b");
  assert.strictEqual(mapped.provider, "Google");
  assert.strictEqual(mapped.status, "ACTIVE");
  assert.strictEqual(mapped.is_active, true);
  assert.strictEqual(mapped.parameter_size, "4.3B");
});

test("Test Inference Parser - Parses PASS response payload with latency", () => {
  const raw = {
    status: "PASS",
    model: "gemma3:4b",
    latency_ms: 245,
    response: "AEGIS MODEL TEST PASSED"
  };

  const parsed = parseTestInferenceResult(raw);
  assert.strictEqual(parsed.status, "PASS");
  assert.strictEqual(parsed.model, "gemma3:4b");
  assert.strictEqual(parsed.latency_ms, 245);
  assert.strictEqual(parsed.response, "AEGIS MODEL TEST PASSED");
});

test("Test Inference Parser - Parses FAIL response payload gracefully", () => {
  const raw = {
    status: "FAIL",
    model: "nonexistent:model",
    latency_ms: 12,
    error: "Model unavailable in local Ollama daemon."
  };

  const parsed = parseTestInferenceResult(raw);
  assert.strictEqual(parsed.status, "FAIL");
  assert.strictEqual(parsed.response, "Model unavailable in local Ollama daemon.");
});
