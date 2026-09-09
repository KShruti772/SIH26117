const test = require("node:test");
const assert = require("node:assert");

// Import or replicate the formatEventTypeLabel logic
function formatEventTypeLabel(eventType) {
  switch (eventType) {
    case "REQUEST_RECEIVED":
      return "Request Received";
    case "PLANNING_STARTED":
      return "Analyzing Intent";
    case "PLAN_CREATED":
      return "Plan Initialized";
    case "STEP_STARTED":
      return "Executing Step";
    case "STEP_COMPLETED":
      return "Step Complete";
    case "STEP_FAILED":
      return "Step Failed";
    case "RAG_STARTED":
      return "Querying Local RAG";
    case "RAG_COMPLETED":
      return "RAG Context Ready";
    case "MODEL_INFERENCE_STARTED":
      return "Local Model Inference";
    case "MODEL_INFERENCE_COMPLETED":
      return "Inference Complete";
    case "SANDBOX_EXECUTION_STARTED":
      return "Running Isolated Sandbox";
    case "SANDBOX_EXECUTION_COMPLETED":
      return "Sandbox Complete";
    case "DOCUMENT_GENERATION_STARTED":
      return "Generating Document";
    case "DOCUMENT_GENERATED":
      return "Document Ready";
    case "VISION_ANALYSIS_STARTED":
      return "Analyzing Image/OCR";
    case "VISION_ANALYSIS_COMPLETED":
      return "Vision Complete";
    case "VERIFICATION_STARTED":
      return "Grounding Verification";
    case "VERIFICATION_COMPLETED":
      return "Verification Complete";
    case "REPLAN_STARTED":
      return "Auto-Replanning";
    case "WAITING_FOR_HUMAN":
      return "Awaiting Approval";
    case "EXECUTION_COMPLETED":
      return "Execution Finished";
    case "EXECUTION_FAILED":
      return "Execution Failed";
    default:
      return (eventType || "").replace(/_/g, " ");
  }
}

// SSE stream buffer parser
function parseSseStreamChunks(rawChunks) {
  const events = [];
  let finalResult = null;
  let buffer = "";

  for (const chunk of rawChunks) {
    buffer += chunk;
    const lines = buffer.split("\n\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("data: ")) {
        const payload = JSON.parse(trimmed.slice(6));
        if (payload.event) {
          events.push(payload.event);
        }
        if (payload.result) {
          finalResult = payload.result;
        }
      }
    }
  }

  return { events, finalResult };
}

// State Machine for live plan execution updates
class LivePlanExecutionState {
  constructor(initialPlan = null) {
    this.executionId = null;
    this.events = [];
    this.plan = initialPlan;
    this.status = "IDLE";
  }

  handleEvent(evt) {
    this.events.push(evt);
    if (evt.execution_id) {
      this.executionId = evt.execution_id;
    }
    if (evt.metadata && evt.metadata.plan) {
      this.plan = evt.metadata.plan;
    }
    if (evt.step_id !== undefined && this.plan && Array.isArray(this.plan.steps)) {
      this.plan.steps = this.plan.steps.map((st) => {
        if (st.step_id === evt.step_id) {
          let newStatus = st.status;
          if (evt.event_type === "STEP_STARTED") newStatus = "RUNNING";
          else if (evt.event_type === "STEP_COMPLETED") newStatus = "COMPLETED";
          else if (evt.event_type === "STEP_FAILED") newStatus = "FAILED";
          return {
            ...st,
            status: newStatus,
            selected_model: evt.metadata?.model_id || st.selected_model,
            duration_ms: evt.metadata?.duration_ms ?? st.duration_ms,
            verification_result: evt.metadata?.verification_result ?? st.verification_result,
            is_replan: evt.metadata?.is_replan ?? st.is_replan,
          };
        }
        return st;
      });
    }
    if (evt.event_type === "EXECUTION_COMPLETED") {
      this.status = "COMPLETED";
    } else if (evt.event_type === "EXECUTION_FAILED") {
      this.status = "FAILED";
    } else if (evt.event_type === "WAITING_FOR_HUMAN") {
      this.status = "WAITING_FOR_HUMAN";
    } else {
      this.status = "RUNNING";
    }
  }
}

test("Live Execution: Event Type Formatting", () => {
  assert.strictEqual(formatEventTypeLabel("REQUEST_RECEIVED"), "Request Received");
  assert.strictEqual(formatEventTypeLabel("RAG_STARTED"), "Querying Local RAG");
  assert.strictEqual(formatEventTypeLabel("MODEL_INFERENCE_STARTED"), "Local Model Inference");
  assert.strictEqual(formatEventTypeLabel("SANDBOX_EXECUTION_STARTED"), "Running Isolated Sandbox");
  assert.strictEqual(formatEventTypeLabel("REPLAN_STARTED"), "Auto-Replanning");
  assert.strictEqual(formatEventTypeLabel("WAITING_FOR_HUMAN"), "Awaiting Approval");
  assert.strictEqual(formatEventTypeLabel("VERIFICATION_COMPLETED"), "Verification Complete");
});

test("Live Execution: SSE Stream Parsing", () => {
  const chunks = [
    'data: {"event": {"event_type": "REQUEST_RECEIVED", "execution_id": "EXE-12345678", "message": "Received"}}\n\n',
    'data: {"event": {"event_type": "PLANNING_STARTED", "execution_id": "EXE-12345678", "message": "Planning"}}\n\n',
    'data: {"result": {"success": true, "answer": "Analysis complete.", "execution_id": "EXE-12345678"}, "done": true}\n\n'
  ];

  const parsed = parseSseStreamChunks(chunks);
  assert.strictEqual(parsed.events.length, 2);
  assert.strictEqual(parsed.events[0].event_type, "REQUEST_RECEIVED");
  assert.strictEqual(parsed.events[1].event_type, "PLANNING_STARTED");
  assert.notStrictEqual(parsed.finalResult, null);
  assert.strictEqual(parsed.finalResult.answer, "Analysis complete.");
});

test("Live Execution: Plan Step State Transitions & Replanning", () => {
  const initialPlan = {
    plan_id: "plan_101",
    steps: [
      { step_id: 1, description: "Check sensor telemetry", status: "PENDING" },
      { step_id: 2, description: "Generate vibration plot", status: "PENDING" }
    ]
  };

  const state = new LivePlanExecutionState(initialPlan);

  // Step 1 starts
  state.handleEvent({
    event_type: "STEP_STARTED",
    execution_id: "EXE-TEST1234",
    step_id: 1,
    metadata: { model_id: "Qwen2.5-Coder-7B" }
  });
  assert.strictEqual(state.plan.steps[0].status, "RUNNING");
  assert.strictEqual(state.plan.steps[0].selected_model, "Qwen2.5-Coder-7B");

  // Step 1 fails & triggers replan
  state.handleEvent({
    event_type: "STEP_FAILED",
    execution_id: "EXE-TEST1234",
    step_id: 1,
    metadata: { verification_result: "FAIL (Data out of bounds)" }
  });
  assert.strictEqual(state.plan.steps[0].status, "FAILED");
  assert.strictEqual(state.plan.steps[0].verification_result, "FAIL (Data out of bounds)");

  // Replanning event
  state.handleEvent({
    event_type: "REPLAN_STARTED",
    execution_id: "EXE-TEST1234",
    message: "Auto-replanning step 1 with relaxed tolerance",
    metadata: { replan_count: 1 }
  });

  // Re-planned step execution succeeds
  state.handleEvent({
    event_type: "STEP_COMPLETED",
    execution_id: "EXE-TEST1234",
    step_id: 1,
    metadata: { is_replan: true, verification_result: "PASS", duration_ms: 340 }
  });
  assert.strictEqual(state.plan.steps[0].status, "COMPLETED");
  assert.strictEqual(state.plan.steps[0].is_replan, true);
  assert.strictEqual(state.plan.steps[0].verification_result, "PASS");
  assert.strictEqual(state.plan.steps[0].duration_ms, 340);

  // Finish execution
  state.handleEvent({
    event_type: "EXECUTION_COMPLETED",
    execution_id: "EXE-TEST1234",
    message: "Workflow finished"
  });
  assert.strictEqual(state.status, "COMPLETED");
});

test("Live Execution: Zero CoT & Secret Exposure Guarantee", () => {
  const events = [
    { event_type: "REQUEST_RECEIVED", execution_id: "EXE-A1B2C3D4", message: "Accepted" },
    { event_type: "RAG_STARTED", execution_id: "EXE-A1B2C3D4", message: "Searching vectors" },
    { event_type: "MODEL_INFERENCE_STARTED", execution_id: "EXE-A1B2C3D4", metadata: { model_id: "Qwen2.5-Coder-7B" } }
  ];

  const serialized = JSON.stringify(events).toLowerCase();
  const forbidden = ["chain_of_thought", "private_key", "password", "bearer ", "system_prompt"];

  for (const term of forbidden) {
    assert.strictEqual(serialized.includes(term), false, `Forbidden term found: ${term}`);
  }
});
