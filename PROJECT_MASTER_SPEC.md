# AEGIS — PROJECT MASTER SPECIFICATION

---

## 1. Problem Statement
The Smart India Hackathon Problem Statement **SIH26117** requires the development of a self-hosted, on-premise, air-gapped **Agentic AI Workbench** utilizing open-weight models. High-security organizations (refineries, defence, PSUs) need to perform confidential industrial knowledge tasks (P&ID analysis, code generation, inspection summaries) without sending proprietary documents or query data to external/public cloud APIs (e.g., OpenAI, Anthropic, Gemini).

---

## 2. Problem Analysis
Industrial knowledge work at organizations like Mangalore Refinery and Petrochemicals Limited (MRPL) involves parsing documents containing critical operational data:
* **Refinery Asset Maps & Schematics:** P&IDs, equipment configurations, and hazard zone maps.
* **Maintenance logs:** Historical failure logs, plant turnaround files, and safety reports.
* **Commercial Records:** Vendor contract terms, bid negotiations, and pricing sheets.

Uploading these to cloud-based LLM nodes violates strict organizational data sovereignty policies, raises corporate espionage risks, and fails in remote or air-gapped areas where internet connectivity is blocked or unavailable.

---

## 3. Aegis Solution
AEGIS is an on-premise, air-gapped server instance providing an autonomous, multi-step Agentic AI Workbench:
* **Fully Local Execution:** Operates using open-weight models loaded via local runtimes (such as Ollama or llama.cpp).
* **Resource-Aware Swapping:** Manages model memory lifecycles dynamically, ensuring that inference fits within host workstation parameters.
* **Sandbox Verification:** Executes generated code blocks inside an isolated local process, capturing stdout/stderr and verifying output before delivery.
* **Document compilation:** Autonomously constructs final reports in official file formats (.docx, .xlsx, .pdf) grounded in internal SOP documents.

---

## 4. MVP Scope
The hackathon MVP is designed to run on resource-constrained local hardware, demonstrating:
1. **Local Model Inference:** Hosting and querying text, vision, and coding models locally via Ollama.
2. **Model Registry & Router:** Decoupled prompt routing to load the best-suited local model.
3. **Local RAG & Knowledge Base:** Document ingestion, local chunking, embedding, vector search, and grounding validation.
4. **Sandboxed Code Sandbox:** Executing Python scripts safely with resource limits and local loopback variables.
5. **Local OCR Pipeline:** Offline text extraction from scanned PDF/PNG files.
6. **Agentic Planning Loop:** Plan-Execute-Observe-Verify-Re-plan loop to compile a verified Word report from a scanned inspection sheet.
7. **Basic Security & Logs:** Hashed credentials database, JWT session tokens, and append-only local audit logs.

---

## 5. Final/Product Vision
A enterprise-grade sovereign AI ecosystem deployed across a refinery’s private intranet:
* **High-Availability Clusters:** Run multiple redundant nodes utilizing vLLM and GPU load balancers (A100/H100 pools).
* **MicroVM Sandboxing:** Execute python code in transient micro-virtual machines (e.g. AWS Firecracker) with absolute system isolation.
* **Multimodal Vector Knowledge Ingestion:** Automated indexing of thousands of scanned engineering drawings, voice logs, and spreadsheets.
* **Hardware-accelerated OCR & Parsing:** Native optical character recognition models optimized for massive engineering schematics and CAD layouts.

---

## 6. Architecture
AEGIS uses a modular architecture separating client interfaces, core backend controller services, local inference adapters, and programmatic execution tools.

```
[ Secure Web UI (Next.js) ]
          │ (REST API / WebSockets)
          ▼
[ FastAPI Backend Application ]
    ├── Authentication & Authorization (JWT / SQLite)
    ├── Audit Logging Service (Append-Only SQLite)
    │
    ├── [ Agent Controller ] ◄──► [ Verification Layer ]
    │         │ (Multi-Step Loop)
    │         ▼
    │   [ Model Router ] ──► [ Model Registry ]
    │         │
    │         ▼
    │   [ Model Loader & Swapper ]
    │         │ (Ollama CLI / API Host Control)
    │         ▼
    │   [ Local Runtimes: Ollama / llama.cpp ] ◄──► [ Quantized Weights (6GB VRAM limit) ]
    │
    └── [ Local Tool Bridge ]
              ├── Local RAG Engine (ChromaDB + Sentence Transformers)
              ├── Isolated Python Sandbox (Process Isolation)
              ├── Document Generator (python-docx / openpyxl / reportlab)
              ├── File Operations Module (Local Disk Read/Write)
              └── OCR Processor (EasyOCR / Tesseract-OCR)
```

---

## 7. Components
* **API Portal (FastAPI):** Exposes JSON endpoints, routes incoming tasks, manages JWT sessions, and writes audit tables.
* **Agent Planner:** Compiles structured JSON checklists containing step-by-step instructions needed to complete the user request.
* **Model Orchestration Layer:** Contains the Model Registry (storing profiles), Model Router (task router), and Model Loader (VRAM memory cleaner).
* **Local Tool Bridge:** Integrates individual execution tools (file IO, code execution process, OCR parser, ChromaDB vector retrieval).
* **Verification Layer:** An automated rules checker that runs checks (e.g., citation checks, file existence tests, code exit codes) on agent results.

---

## 8. Agent Workflow
The cognitive loop follows the **Plan-Execute-Observe-Verify-Re-plan** loop:
1. **Understand:** User submits a request (e.g., "Analyze the corrosion log and compile an approval note").
2. **Plan:** The controller creates a sequential execution graph.
3. **Execute:** The controller selects the appropriate tool and model, command Ollama to load the model, and invokes the tool.
4. **Observe:** The controller captures stdout, parsed texts, database results, or compilation outputs.
5. **Verify:** The Verifier inspects outputs against specific parameters (e.g., "Are calculations grounded?", "Did python run with code 0?").
6. **Deliver / Re-plan:** If verification passes, the file is saved to outputs. If verification fails, the error trace is added to the agent's memory, and the planner loops back to Step 2.

---

## 9. Model Abstraction Strategy
To prevent agent modules or tools from hard-coding specific LLM APIs:
* All interactions with models occur through a unified `BaseModelProvider` interface wrapper.
* Runtimes implement standard methods: `load()`, `unload()`, `generate()`, `generate_stream()`, and `health_check()`.
* Adding a new LLM runtime (e.g., transitioning from Ollama to llama.cpp or a local vLLM server) only requires writing a new provider adapter class.

---

## 10. Model Registry
The registry is configured via `backend/app/models/registry/registry.json`. It defines profiles for available local weights:
* **Model ID:** Unique string signature (e.g. `llama32-3b-text`).
* **Runtime:** Local host runtime client wrapper to invoke (e.g. `ollama`).
* **System Capabilities:** List of functional tasks (e.g. `["planning", "reasoning", "coding"]`).
* **VRAM footprint:** Declared memory size in GB (e.g. `2.5` for 3B parameter models).

---

## 11. Model Router
The Model Router acts as a dispatcher:
* It reads the capability flag declared by the Agent Planner (e.g. `capability: "coding"`).
* It queries the Registry to filter candidate models.
* It checks the model's footprint against VRAM limits to select the most efficient, lightweight model that satisfies the task requirements.

---

## 12. Dynamic Model Loading Strategy
Due to our physical GPU hardware limits (**NVIDIA RTX 4050 with 6 GB VRAM**):
* Running multiple LLMs simultaneously is prohibited.
* The system enforces a **Mutex Lock (Mutual Exclusion)** at the model loader layer.
* When a model (e.g., Model B) is selected by the Router, the Loader checks active memory (via `GET http://localhost:11434/api/ps`).
* If another model (e.g., Model A) is running, the Loader issues an unload request (calling Ollama with `keep_alive: 0`) and waits for system memory resources to clear before starting Model B.

---

## 13. Multimodal Pipeline
Mixed documents (PDF files with visual diagrams or scanned tables) are parsed sequentially:
* **Native Text Parser:** Attempts direct layout extraction first.
* **Layout Segmenter:** If native text is absent, parses pages into image blocks.
* **Local OCR / Vision Routing:** Runs OCR on text blocks and queries a local vision LLM (e.g., Qwen2-VL-2B) to interpret visual drawings.
* **Markdown Compiler:** Combines text blocks, tables, and vision descriptions into a unified markdown format.

---

## 14. RAG Pipeline
* **Ingestion:** Documents in `data/knowledge_base/` are parsed using `PyPDF`/`docx-parser`.
* **Chunking:** Chunks text using recursive character splitting (e.g., 500-1000 character length blocks with a 10% overlap margin).
* **Embeddings:** Vectorizes blocks using a local HuggingFace embedding runtime (`sentence-transformers/all-MiniLM-L6-v2`) running on CPU/GPU.
* **Vector Store:** Saves vectors locally inside ChromaDB (`d:\SIH26117\vectorstore`).
* **Retrieval:** Converts query prompts to embeddings, executes cosine-similarity search, and injects context blocks into the LLM prompt.

---

## 15. Tool Architecture
Tools are structured Python helper classes inheriting from a common base:
* They declare a schema (arguments, name, and description) matching standard tool-calling specifications.
* The Agent Planner parses LLM outputs to identify tool calls, extracts the JSON arguments, passes them to the tool class, and executes the code.
* Outputs are returned to the agent context as structured dictionary responses (`{"status": "success/error", "data": ...}`).

---

## 16. Code Sandbox Architecture
* **Isolation:** Generated scripts run in a separate Python sub-process.
* **Resource Constraints:** Enforces execution time limits (e.g., `timeout=10` seconds) to prevent infinite loops.
* **Environment Scrubbing:** Clears system variables and blocks internet network access by binding the socket to local addresses only.
* **Logs Capture:** Captures and returns stdout, stderr, and execution codes to the agent controller.

---

## 17. Verification Architecture
The system integrates programmatic validation rules at the output interface:
* **Grounding Checker:** Inspects if output facts exist as substrings or semantic matches within the RAG context blocks.
* **Code Sandbox Tester:** Asserts that generated scripts exit with return code `0` and return correct console variables.
* **Format Validator:** Ensures JSON files are readable and generated reports match structure guidelines.

---

## 18. Security Architecture
Designed to function inside closed environments:
* **Private Subnet Access:** Web portal bound to local interfaces (`0.0.0.0`) to restrict access to the LAN.
* **Network Block:** Environment configuration strictly enforces `ALLOW_EXTERNAL_APIS=false`.
* **Hashed Storage:** Hashed database credentials to prevent local plain-text exploits.

---

## 19. Authentication/Authorization
* **Users Table:** Maintained in a local, password-secured SQLite file (`data/private/aegis.db`).
* **JWT Engine:** Encodes sessions using HS256 JWT tokens.
* **Role Management (RBAC):**
  * `Admin`: Manages vector documents, logs, and registry settings.
  * `Authorized User`: Runs planning loops, compiles spreadsheets, and analyzes documents.
  * `Viewer`: Searches RAG logs and downloads compiled reports.

---

## 20. Audit Logging
* **Mechanism:** All user requests, model choices, tool calls, and verification status results are logged in SQLite.
* **Format:** Records Timestamp, User, Source IP, Selected Model, Tool Inputs, Status, and export files.
* **Security:** Write-only from application threads to prevent modification of logs.

---

## 21. Network Sovereignty Strategy
* **Local Dependency Cache:** All Python dependencies are pre-compiled and hosted on disk.
* **Model Storage:** Weights are saved in Ollama's local directory.
* **Offline Verification:** Verification scripts run tests with host ethernet/wifi cards disabled to ensure no network calls occur.

---

## 22. Deployment Modes
* **Developer Local Mode:** Runs directly on the development computer (FastAPI + Next.js scaffold + local Ollama daemon).
* **Docker Compose Subnet Mode:** Containers package Next.js frontend, FastAPI backend, SQLite, ChromaDB, and Ollama.
* **Air-Gapped LAN Server:** Extracted docker images and GGUF model files installed via script on a LAN-bound workstation.

---

## 23. Hardware Assumptions
* **Development Workstation:** Intel i7-13620H, 16 GB system RAM, Intel UHD graphics.
* **Primary Local Inference Host:** NVIDIA RTX 4050 (6 GB VRAM), 16 GB system RAM, 512 GB SSD.
* **Model Footprint Allocation:**
  * Host OS + UI overhead: ~1.5 GB VRAM.
  * Available inference VRAM: ~4.5 GB.
  * Selected model parameter target: 1B - 3B quantized classes.

---

## 24. MVP Limitations
* **VRAM Concurrency:** Single user limit. Dynamic swapping causes latency (10-20 seconds) when switching tasks.
* **Complex Vision Schematics:** 2B vision models may miss detailed text in high-resolution P&ID diagrams.
* **No CPU Inference:** Heavy 7B-8B parameter models running on CPU/system RAM will experience high latency (1-3 tokens/second).

---

## 25. Development Phases
* **Phase 1: Foundation (Current):** Setup directories, configure registry structures, write specifications, and initialize tests.
* **Phase 2: Runtimes & Routing:** Write Ollama API wrappers, implement registry parser, and code model load-unloader locks.
* **Phase 3: Core Tools & RAG:** Implement OCR, code sandbox execution loops, and ChromaDB vector search.
* **Phase 4: Agent Controller:** Program the cognitive planner, execute tools, and verify outputs.
* **Phase 5: UI & Deployment:** Create Next.js panel interfaces, secure routes, and write Nginx and Docker compose packages.

---

## 26. Demo Scenario
1. **User Login:** Authenticates over local LAN and accesses the AEGIS dashboard.
2. **Inspection Report Upload:** User uploads a scanned, noisy PDF of a refinery tank thickness test.
3. **Execution Routing:** System triggers OCR, extracts text, queries ChromaDB RAG, loads Llama-3.2-3B to VRAM, plans steps, and writes python code to calculate corrosion rate.
4. **Sandbox Run:** Python code executes inside the sandbox to calculate the rates.
5. **Report Generation:** Agent drafts a Word DOCX report containing the findings and outputs it.
6. **Grounding Audit:** Verifier audits citations and exports the verified DOCX report to output folders.

---

## 27. Acceptance Criteria
* **Local Operation:** Must run completely offline with internet disconnected.
* **Model Routing:** Task capability routes are resolved without hard-coded model calls.
* **VRAM Limit Compliance:** Inference fits inside the 6GB VRAM limit on the RTX 4050 without OOM crashes.
* **Sandboxed Safety:** Executed code must execute inside isolated processes and enforce resource limits.
* **Grounded Output:** Compiled reports must contain accurate references to knowledge base files.
