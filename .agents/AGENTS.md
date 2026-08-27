# AEGIS — IMPLEMENTATION / TEST / VERIFY / STATUS CONTROL RULE

This document outlines the strict workflow that all development agents and team members must follow when working on the Aegis project for SIH Problem Statement 26117:
"Sovereign On-Premise Agentic AI Workbench using Open-Weight Multimodal LLMs for Confidential Industrial Work."

---

## The Core Lifecycle Workflow
Every development task must advance through these sequential phases:

```
[IMPLEMENT] ──→ [TEST] ──→ [VERIFY] ──→ [UPDATE STATUS] ──→ [MOVE TO NEXT TASK]
```

---

## 1. IMPLEMENT Phase

Before changing any code:
1. **Read & Inspect:** Review [PROJECT_MASTER_SPEC.md](file:///d:/SIH26117/PROJECT_MASTER_SPEC.md), [IMPLEMENTATION_STATUS.md](file:///d:/SIH26117/IMPLEMENTATION_STATUS.md), and relevant source code/test files.
2. **Understand:** Identify the functional target, existing system dependencies, and confirm no other teammate or agent is currently working on the same files.
3. **No Mocks as Real Features:** Do not replace real implementation logic with hard-coded outputs, dummy model API payloads, simulated router logs, or placeholder messages. Mocks are only allowed when isolated in unit tests.

---

## 2. TEST Phase

After writing code, verify execution with actual tests corresponding to the feature:
* **Model Loading:** Actually load model weights, run local inference, observe memory consumption, and verify the model unloads cleanly to release VRAM.
* **Model Routing:** Submit diverse inputs (text reasoning, code generation, vision tasks) and verify that the router routes each to the correct model.
* **Model Switching:** Sequence model loading/unloading (Model A load -> inference -> unload -> Model B load -> inference) to confirm memory stability.
* **Local RAG:** Ingest real documents, perform semantic search queries, and confirm context grounding in the generated response.
* **OCR/Vision:** Process scanned PDF/image pages to verify the accuracy of text extraction.
* **Code Sandbox:** Execute test scripts in the sandbox to verify process isolation, resource limits, and output capture.
* **File Generation:** Create actual files (DOCX, XLSX, PPTX, PDF) and confirm they open correctly without syntax or formatting corruption.
* **Agent Workflow:** Execute a multi-step workflow and verify the agent's plan-execute-observe-verify loop functions end-to-end.

*A feature is not complete just because code builds, endpoints return 200, or a stub function exists.*

---

## 3. VERIFY Phase

Verify that the implementation satisfies the requirements using concrete evidence (e.g., test suites, model logs, file buffers, database records, network captures).

For important features, document:
1. **Feature Name**
2. **What Was Tested**
3. **How It Was Tested**
4. **Result**
5. **Evidence** (command outputs, logs, database state, files)
6. **Limitations**

---

## 4. Status Tracking

Maintain strict status definitions in [IMPLEMENTATION_STATUS.md](file:///d:/SIH26117/IMPLEMENTATION_STATUS.md):

* 🔴 **NOT STARTED** — No meaningful implementation exists.
* 🟡 **IN PROGRESS** — Implementation is currently being developed.
* 🟠 **IMPLEMENTED — NOT VERIFIED** — Code exists, but real testing has not yet confirmed it works.
* 🟢 **VERIFIED** — Implementation has been tested successfully with evidence.
* 🔵 **DEMO READY** — Verified and integrated into the complete hackathon demonstration flow.
* ⚫ **BLOCKED** — Development is halted due to a known dependency or hardware issue.

### Status Update Format
For every task updated to `🟠`, `🟢`, or `🔵`, record the following details in `IMPLEMENTATION_STATUS.md`:
```markdown
### Feature:
[feature name]

### Status:
[appropriate status]

### Implementation:
[what was actually implemented]

### Tested:
[exact test performed]

### Result:
[actual result]

### Evidence:
[logs / test name / generated file / screenshot / command / measurable result]

### Limitations:
[anything that does not yet work]

### Files Changed:
[list important files]

### Dependencies:
[related modules/features]

### Next Step:
[what should happen next]
```

---

## 5. Network Sovereignty & Air-Gap Rules
* **No Cloud Backdoors:** Do not introduce dependencies on external cloud APIs (e.g., OpenAI, Claude, Gemini, cloud vector stores, cloud OCR engines).
* **Physical Disconnect Testing:** Never mark the sovereignty requirement complete until the application has been successfully tested with physical or system-level network cards disabled.

---

## 6. Project Preservation Guidelines
* **Read Existing Logic:** Do not overwrite or rebuild existing features from scratch. Inspect, test, and adapt them before deciding to rewrite.
* **Failure Documentation:** If a test fails, do not mark it verified. If it cannot be fixed, mark it `⚫ BLOCKED` and document errors, attempted fixes, and proposed workarounds.
* **No Simulated Demos:** Clearly label mock features as `DEMO MOCK / SIMULATION` and do not present them as completed requirements.

---

## 7. Hand-Off Reporting Structure
At the completion of each task, the agent must output a final response summarizing:
1. **Task:** Description of requested work.
2. **Implementation:** Code files changed or added.
3. **Tests Completed:** Verification methods and tool metrics.
4. **Verification Result:** Current status label.
5. **Evidence:** Concrete terminal outputs, file names, or execution logs.
6. **Remaining Limitations:** Unimplemented edge-cases or hardware-related bugs.
7. **Next Recommended Task:** The next logical work item.
