# AEGIS Phase 7B — Complete Runtime Inventory & Verification Audit

## 1. Environment & Host Runtime Inventory

* **Host Operating System**: Windows 11 / x86_64
* **Python Runtime**: Python 3.12.8 (Virtual Environment: `backend/.venv`)
* **Node.js Runtime**: Node.js v20.20.2 (`npm` 10.8.2)
* **Local Inference Daemon**: Ollama (`http://localhost:11434`) — **ONLINE**
* **Local Database**: SQLite 3 (`data/private/aegis_auth.db`)
* **Local Vector Database**: ChromaDB (`./vectorstore`)
* **Local Embedding Weights**: `sentence-transformers/all-MiniLM-L6-v2` (`models/all-MiniLM-L6-v2`)

---

## 2. Local Ollama Runtime Inspection

Query against `http://localhost:11434/api/tags`:

| Model Tag | Model Digest | Parameter Size | Format | Quantization | Disk Size | Capabilities | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `gemma3:4b` | `a2af6cc3eb7f...` | `4.3B` | `gguf` | `Q4_K_M` | `3.34 GB` | `completion` | **INSTALLED & LOADED** |
| `qwen3:4b` | `359d7dd4bcda...` | `4.0B` | `gguf` | `Q4_K_M` | `2.50 GB` | `completion, tools, thinking` | **INSTALLED** |

Query against `http://localhost:11434/api/ps`:
* **Currently Active Memory Model**: `gemma3:4b`
* **Context Length**: `4,096`
* **Memory Allocated**: `2,881,811,905 bytes` (~2.88 GB)
* **GPU VRAM Telemetry**: `NOT REPORTED BY RUNTIME` (0 bytes reported via API)

---

## 3. Backend Subsystem Inventory

| Subsystem Module | File Location | Operational Target | Current Verification Status |
| :--- | :--- | :--- | :--- |
| **FastAPI Backbone** | `[backend/app/main.py](file:///d:/SIH26117/backend/app/main.py)` | HTTP REST API, CORS middleware, Request Correlation Middleware | **VERIFIED (68 Backend Tests Pass)** |
| **Authentication Router** | `[backend/security/auth_router.py](file:///d:/SIH26117/backend/security/auth_router.py)` | Login, Registration, Token Issuance, User Admin, Password Management | **VERIFIED (SQLite + JWT HS256)** |
| **RBAC Guard Policy** | `[backend/security/dependencies.py](file:///d:/SIH26117/backend/security/dependencies.py)` | `RoleChecker(["admin"])`, Session Ownership Enforcer | **VERIFIED (HTTP 403 On Violation)** |
| **Audit Ledger Logger** | `[backend/security/audit.py](file:///d:/SIH26117/backend/security/audit.py)` | Parameterized SQL Append-Only Logger, Metadata Allowlist Filtering | **VERIFIED (Append-Only, No Mutation API)** |
| **Conversation Manager** | `[backend/agents/conversations.py](file:///d:/SIH26117/backend/agents/conversations.py)` | SQLite Session & Message Persistence, User Ownership Indexing | **VERIFIED (Session Isolated)** |
| **Local Model Loader** | `[backend/models/loaders/manager.py](file:///d:/SIH26117/backend/models/loaders/manager.py)` | Ollama API HTTP Adapter, Model Tag Discovery, Switching Lock | **VERIFIED (gemma3:4b + qwen3:4b)** |
| **Local RAG Service** | `[backend/rag/pipeline.py](file:///d:/SIH26117/backend/rag/pipeline.py)` | Local PyPDF/TXT Ingestion, Chunk Splitting, ChromaDB Vector Indexing | **VERIFIED (Metadata Tenant Filtering)** |
| **Local Embeddings** | `[backend/rag/embeddings.py](file:///d:/SIH26117/backend/rag/embeddings.py)` | `all-MiniLM-L6-v2` SentenceTransformer Embedding Weights | **VERIFIED (Offline File Execution)** |
| **Subprocess Code Sandbox** | `[backend/tools/code_sandbox/sandbox.py](file:///d:/SIH26117/backend/tools/code_sandbox/sandbox.py)` | Isolated Python Process Executor, Timeout & Output Caps | **VERIFIED (Subprocess Isolated)** |
| **Grounding Verifier** | `[backend/app/verification/verifier.py](file:///d:/SIH26117/backend/app/verification/verifier.py)` | Grounding Overlap Analysis, Citation Verification, Grounding Tags | **VERIFIED (GROUNDED vs UNVERIFIED)** |

---

## 4. Frontend Application Inventory

| View Screen | Route | Key Functionality | Truthfulness Rule |
| :--- | :--- | :--- | :--- |
| **Dashboard** | `/` (Tab 0) | System Overview, Service Health, Model Status Cards | Real telemetry metrics or `NOT REPORTED` |
| **AI Assistant** | `/` (Tab 1) | Industrial Agentic Chat, Grounding Citations, Model Selection | Real Ollama response & Session Persistence |
| **Knowledge Base** | `/` (Tab 2) | Document Upload, Semantic Search Lab, Index Telemetry | Real ChromaDB results or `KNOWLEDGE BASE EMPTY` |
| **Model Management** | `/` (Tab 3) | Model Switching, Latency Test Bench, Profile Specs | Real Ollama test latency or `UNAVAILABLE` |
| **Audit Ledger** | `/` (Tab 4) | Append-Only Event Log Viewer, Filters, Summary Metrics | Real SQLite logs or `NO AUDIT EVENTS RECORDED` |
| **Code Sandbox** | `/` (Tab 5) | Python Execution Bench, Stdout/Stderr Output Capture | Real subprocess execution output |
| **Access Control** | `/` (Tab 6) | Admin User Administration, User Enable/Disable/Reset | Real SQLite RBAC policies |
| **Settings** | `/` (Tab 7) | System Configuration Parameters & Air-Gap Guards | Real environment settings |
| **Login View** | `/login` | Authentication Guard, Session Restoration, 401 Lockout | Real JWT authentication |

---

## 5. Security & Network Posture Audit

* **External API Check**: Zero dependencies on external cloud APIs (OpenAI, Anthropic, Gemini, cloud vector stores).
* **Allowed Host Boundaries**: FastAPI server binds strictly to configured `HOST` (default `127.0.0.1`).
* **Metadata Secret Protection**: `ALLOWED_METADATA_KEYS` filter prevents passwords, bearer tokens, or full prompt/document bodies from being stored in audit logs.
* **Append-Only Property**: API route table contains zero `PUT`, `PATCH`, or `DELETE` endpoints for `/audit`.

---

*Task 1 Inventory Complete. Proceeding to End-to-End Task Verification suite.*
