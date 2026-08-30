# AEGIS Phase 7C — Pre-Implementation Security, Resilience & Hardening Audit

## Executive Summary
This pre-implementation security and resilience audit evaluates the AEGIS Sovereign On-Premise Agentic AI Workbench against enterprise production standards. While Phases 1 through 7B verified core functional features, local Ollama execution, RBAC, session isolation, and reproducible setup, Phase 7C addresses **production security, cryptographic integrity, sandbox isolation, session revocation, air-gap enforcement, and fault tolerance**.

---

## Identified Production Security & Integrity Gaps

### 1. Audit Ledger Cryptographic Integrity (Tamper-Evidence)
* **Current State**: Audit events are stored in SQLite `audit_logs` table. Application endpoints cannot mutate audit records (`PUT`/`PATCH`/`DELETE /audit` do not exist).
* **Gap Identified**: Audit log rows lack cryptographic linkage (`previous_hash` and `entry_hash`). Direct manipulation of the SQLite file on disk (or out-of-band SQL execution) cannot be automatically detected.
* **Proposed Hardening**: 
  - Upgrade `audit_logs` schema to include `previous_hash` and `entry_hash` (HMAC-SHA256 chain).
  - Implement `AuditLogger.verify_chain_integrity()` to validate the ledger hash chain.
  - Add admin-only endpoint `GET /audit/verify` returning cryptographic verification status (`INTACT` / `TAMPERED`).

### 2. Token Revocation & Blacklisting (JWT Lifecycles)
* **Current State**: JWT tokens are signed using HS256 with `exp` claims. `POST /auth/logout` records `LOGOUT` audit logs and clears frontend tokens.
* **Gap Identified**: Issued JWTs remain valid until their expiration time (`exp`). If a user logs out or changes their password, previously issued tokens remain usable until natural expiration.
* **Proposed Hardening**:
  - Add SQLite `revoked_tokens` table (`token_hash`, `revoked_at`, `expires_at`).
  - Add `jti` (JWT ID) or token hash checking in `[backend/security/dependencies.py](file:///d:/SIH26117/backend/security/dependencies.py)`.
  - Revoke all active tokens for a user upon password change/reset.

### 3. Subprocess Code Sandbox Hardening
* **Current State**: `[backend/tools/code_sandbox/sandbox.py](file:///d:/SIH26117/backend/tools/code_sandbox/sandbox.py)` executes Python scripts in a separate process with scrubbed environment variables and output truncation.
* **Gap Identified**: Untrusted Python code can import low-level modules (`ctypes`, `subprocess`, `socket`, `winreg`, `os.system`) or create network sockets.
* **Proposed Hardening**:
  - Add AST-based static code analysis before sandbox execution to block forbidden modules (`ctypes`, `subprocess`, `winreg`, `socket`, `importlib`).
  - Inject socket monkey-patching wrapper (`socket.socket` raises `PermissionError`) inside the sandbox execution wrapper script to block outbound network requests on Windows.

### 4. Air-Gap Sovereignty & Offline Enforcement
* **Current State**: System operates locally against Ollama (`127.0.0.1:11434`).
* **Gap Identified**: SentenceTransformer and HuggingFace libraries can attempt background network checks if local model cache directories are misconfigured or missing.
* **Proposed Hardening**:
  - Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and `HF_DATASETS_OFFLINE=1` in `[backend/rag/embeddings.py](file:///d:/SIH26117/backend/rag/embeddings.py)` prior to loading local weights.
  - Explicitly verify local weight files exist (`pytorch_model.bin` / `model.safetensors`) before initializing embedding models.

### 5. Local LLM Runtime Resilience & Circuit Breaking
* **Current State**: `[backend/models/loaders/manager.py](file:///d:/SIH26117/backend/models/loaders/manager.py)` makes HTTP requests to Ollama.
* **Gap Identified**: If the Ollama daemon freezes or drops requests under heavy load, HTTP calls can hang or throw unhandled socket errors.
* **Proposed Hardening**:
  - Implement exponential backoff retries (max 3 attempts) for transient connection errors.
  - Add circuit breaker status detection (`get_runtime_health()`) to immediately report `RuntimeUnavailableError` rather than waiting for 30s timeouts.

### 6. Brute-Force Rate Limiting on Auth Endpoints
* **Current State**: `POST /auth/login` verifies credentials against SQLite.
* **Gap Identified**: Repeated invalid login attempts could allow brute-force password guessing.
* **Proposed Hardening**:
  - Implement in-memory rate limiter for `POST /auth/login` (max 5 failed attempts per username/IP within 5 minutes).

### 7. SQLite Concurrency & Lock Handling
* **Current State**: SQLite connections are opened per request via `get_db()`.
* **Gap Identified**: High concurrent writes to `audit_logs` or `conversations` could trigger `sqlite3.OperationalError: database is locked`.
* **Proposed Hardening**:
  - Configure `busy_timeout=5000` (5 seconds) and enable Write-Ahead Logging (`WAL` mode) on SQLite connection initialization.

---

## Conclusion & Next Step
All audit findings represent high-value production security and resilience improvements without altering existing UI or application architecture. Proceeding to Implementation Plan document.
