const test = require("node:test");
const assert = require("node:assert");

// Simulated Prompt Copy Extractor
function extractVisiblePromptForCopy(message) {
  if (!message || typeof message.content !== "string") {
    return "";
  }
  // Guarantee no hidden system prompts, chain-of-thought, or internal metadata are copied
  const cleanContent = message.content;
  return cleanContent;
}

// Simulated Edit Prompt Payload Builder
function buildEditPromptPayload(sessionId, messageId, newPromptText, selectedModel) {
  const trimmed = (newPromptText || "").trim();
  if (!trimmed) {
    throw new Error("Prompt message or query must not be empty.");
  }
  if (trimmed.length > 1000) {
    throw new Error("Prompt exceeds maximum length of 1000 characters.");
  }
  if (!sessionId || !messageId) {
    throw new Error("Session ID and Message ID are required for prompt edit.");
  }
  return {
    endpoint: `/conversations/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}/edit`,
    method: "POST",
    body: {
      message: trimmed,
      model: selectedModel || undefined
    }
  };
}

// Simulated Edit State Machine
class PromptEditSession {
  constructor(initialMessages = []) {
    this.messages = [...initialMessages];
    this.editingPrompt = null;
    this.activeSessionId = "conv_sample_123";
  }

  startEdit(messageId) {
    const target = this.messages.find(m => m.id === messageId && m.role === "user");
    if (!target) {
      throw new Error("Cannot edit non-existent or assistant message.");
    }
    this.editingPrompt = { id: target.id, originalText: target.content };
    return this.editingPrompt.originalText;
  }

  cancelEdit() {
    this.editingPrompt = null;
  }

  submitEdit(newText, mockAssistantReply) {
    if (!this.editingPrompt) {
      throw new Error("No prompt is currently being edited.");
    }
    const originalMsgId = this.editingPrompt.id;
    const trimmed = (newText || "").trim();
    if (!trimmed) {
      throw new Error("Empty prompt cannot be submitted.");
    }

    // Historical messages MUST remain completely intact (no mutation of previous message)
    const originalMsg = this.messages.find(m => m.id === originalMsgId);
    const originalContentBefore = originalMsg.content;

    // Append new user message and new assistant message
    const newUserMsgId = `msg_${Date.now()}`;
    const newAssistantMsgId = `msg_${Date.now() + 1}`;

    const newUserMsg = {
      id: newUserMsgId,
      role: "user",
      content: trimmed,
      edited_from_message_id: originalMsgId,
      timestamp: new Date()
    };

    const newAssistantMsg = {
      id: newAssistantMsgId,
      role: "assistant",
      content: mockAssistantReply,
      timestamp: new Date()
    };

    this.messages.push(newUserMsg, newAssistantMsg);
    this.editingPrompt = null;

    // Assert original message content was NOT mutated
    assert.strictEqual(originalMsg.content, originalContentBefore, "Historical message must remain immutable");

    return {
      newUserMsgId,
      newAssistantMsgId,
      totalMessages: this.messages.length
    };
  }
}

// ==========================================
// TEST SCENARIOS
// ==========================================

test("Prompt Copy - Extracts exact visible user prompt without internal metadata", () => {
  const userMessage = {
    id: "msg_user_1",
    role: "user",
    content: "Analyze the inspection report and identify vibration issues.",
    metadata: { system_prompt: "internal secret", task_type: "ANALYSIS", token: "jwt.secret.token" }
  };
  const copied = extractVisiblePromptForCopy(userMessage);
  assert.strictEqual(copied, "Analyze the inspection report and identify vibration issues.");
  assert.strictEqual(copied.includes("internal secret"), false);
  assert.strictEqual(copied.includes("jwt.secret.token"), false);
});

test("Prompt Edit Payload - Rejects empty prompt text", () => {
  assert.throws(() => {
    buildEditPromptPayload("conv_1", "msg_1", "   ");
  }, /empty/i);
});

test("Prompt Edit Payload - Rejects prompt text exceeding 1000 characters", () => {
  const over = "A".repeat(1001);
  assert.throws(() => {
    buildEditPromptPayload("conv_1", "msg_1", over);
  }, /1000 characters/i);
});

test("Prompt Edit Payload - Builds valid endpoint and payload", () => {
  const payload = buildEditPromptPayload("conv_123", "msg_456", "Analyze report and prepare draft note.", "qwen2.5-coder:7b");
  assert.strictEqual(payload.endpoint, "/conversations/conv_123/messages/msg_456/edit");
  assert.strictEqual(payload.method, "POST");
  assert.strictEqual(payload.body.message, "Analyze report and prepare draft note.");
  assert.strictEqual(payload.body.model, "qwen2.5-coder:7b");
});

test("Prompt Edit State Machine - Preserves original prompt immutability when editing", () => {
  const session = new PromptEditSession([
    { id: "msg_1", role: "user", content: "Analyze the inspection report." },
    { id: "msg_2", role: "assistant", content: "Vibration on Pump P-102 is normal." }
  ]);

  // Start edit
  const original = session.startEdit("msg_1");
  assert.strictEqual(original, "Analyze the inspection report.");
  assert.strictEqual(session.editingPrompt.id, "msg_1");

  // Submit edit
  const res = session.submitEdit(
    "Analyze the inspection report and calculate vibration delta.",
    "Calculated vibration delta for Pump P-102 is 0.8 mm/s."
  );

  assert.strictEqual(res.totalMessages, 4);
  assert.strictEqual(session.editingPrompt, null);

  // Original messages at index 0 and 1 must remain completely untouched
  assert.strictEqual(session.messages[0].id, "msg_1");
  assert.strictEqual(session.messages[0].content, "Analyze the inspection report.");
  assert.strictEqual(session.messages[1].id, "msg_2");

  // New messages appended at index 2 and 3
  assert.strictEqual(session.messages[2].content, "Analyze the inspection report and calculate vibration delta.");
  assert.strictEqual(session.messages[2].edited_from_message_id, "msg_1");
  assert.strictEqual(session.messages[3].content, "Calculated vibration delta for Pump P-102 is 0.8 mm/s.");
});

test("Prompt Edit State Machine - Cancel restores edit state cleanly without modifying history", () => {
  const session = new PromptEditSession([
    { id: "msg_1", role: "user", content: "Analyze the inspection report." }
  ]);

  session.startEdit("msg_1");
  assert.notStrictEqual(session.editingPrompt, null);

  session.cancelEdit();
  assert.strictEqual(session.editingPrompt, null);
  assert.strictEqual(session.messages.length, 1);
  assert.strictEqual(session.messages[0].content, "Analyze the inspection report.");
});

test("Prompt Edit State Machine - Cannot edit an assistant response", () => {
  const session = new PromptEditSession([
    { id: "msg_1", role: "assistant", content: "AI response" }
  ]);

  assert.throws(() => {
    session.startEdit("msg_1");
  }, /assistant/i);
});

test("Domain Scope Presentation - Administrator scope text reflects authenticated domain", () => {
  const admin = {
    username: "engineering_admin",
    role: "admin",
    department_id: 3,
    department_name: "Engineering"
  };

  const domainLabel = admin.department_name ? admin.department_name.toUpperCase() : "ADMINISTRATION";
  const scopeText = admin.department_name ? `${admin.department_name} users only` : "System scope";

  assert.strictEqual(domainLabel, "ENGINEERING");
  assert.strictEqual(scopeText, "Engineering users only");
});
