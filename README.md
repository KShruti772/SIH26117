# AEGIS — Confidential Industrial Agentic AI Workbench

Sovereign On-Premise Agentic AI Workbench using Open-Weight Multimodal LLMs for Confidential Industrial Work.

---

## 1. What is AEGIS?

AEGIS is an on-premise, self-hosted, air-gapped Agentic AI Workbench designed for confidential industrial organizational data (oil refineries, defence, power grids, PSUs). AEGIS enables enterprise operators to analyze confidential documents, execute technical code, generate deliverables, and perform RAG semantic search without routing proprietary data to external cloud APIs (e.g., OpenAI, Anthropic, Gemini).

---

## 2. Architecture Overview

```text
Operator / User (Browser UI)
          │
          ▼
Next.js Application Shell (Localhost:3000)
          │ (JWT Bearer Auth)
          ▼
FastAPI Sovereign Backend (Localhost:8000)
    ├── Authentication & RBAC Engine (SQLite)
    ├── Local Audit Ledger (Append-Only SQLite)
    ├── Agent Planner & Controller
    ├── Local Ollama LLM Manager (gemma3:4b)
    ├── Local Vector Database (ChromaDB + all-MiniLM-L6-v2)
    └── Subprocess Code Sandbox
```

---

## 3. System Requirements

* **Operating System**: Windows 10 / 11 (64-bit) or Linux.
* **Python Runtime**: Python 3.12+
* **Node.js Runtime**: Node.js v20+ with `npm`
* **Local Inference Engine**: Ollama daemon installed locally (`https://ollama.com`)
* **Hardware Recommendation**: NVIDIA GPU with 6GB+ VRAM (e.g. RTX 4050/3060) or CPU with 16GB RAM.

---

## 4. Internet Requirements vs Air-Gap Runtime

### Installation Phase (Internet Required)
Internet connectivity is required **only during initial environment installation**:
- Downloading Python wheels (`pip install -r backend/requirements.txt`).
- Downloading Node modules (`npm install` in `frontend/`).
- Downloading Ollama application installer.
- Pulling local open-weight model tags (`ollama pull gemma3:4b`) and HuggingFace embedding weights.

### Runtime Phase (100% Air-Gapped Sovereign Execution)
Once installation is complete:
- **Zero Cloud Dependencies**: The system operates 100% offline without external internet calls.
- **Physical Disconnect Ready**: Verified to execute cleanly with network interface adapters disabled.

---

## 5. Cross-Laptop Quick Start Guide

### Step 1: Copy Project Files
Copy the AEGIS root folder to any directory on the target laptop (e.g., `C:\AEGIS` or `D:\Projects\AEGIS`).

### Step 2: Automated Environment Setup
Open PowerShell in the project root and run the setup script:
```powershell
powershell .\scripts\setup.ps1
```
*(This script initializes `.env`, creates directories `data/private` and `vectorstore`, sets up Python virtualenv `backend/.venv`, installs dependencies, initializes SQLite schema, and installs frontend node_modules).*

### Step 3: Run Diagnostic Health Check
Verify system setup using the diagnostic script:
```powershell
powershell .\scripts\check-environment.ps1
```

### Step 4: Inspect & Prepare Local Ollama LLM Model
Ensure the Ollama application is running, then inspect model weights:
```powershell
powershell .\scripts\prepare-models.ps1
```
*(Prompts user to run `ollama pull gemma3:4b` if the model is missing from local Ollama).*

### Step 5: Launch Services
Start the FastAPI backend daemon:
```powershell
powershell .\scripts\start-backend.ps1
```

Open a second terminal window and start the Next.js frontend:
```powershell
powershell .\scripts\start-frontend.ps1
```

Access the AEGIS Workbench in your browser at:
`http://localhost:3000`

---

## 6. Manual Setup & Configuration

### Python Backend Setup
```powershell
# 1. Create virtual environment
python -m venv backend/.venv

# 2. Install requirements
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt

# 3. Initialize SQLite database schema
backend\.venv\Scripts\python -c "from backend.security.database import init_db; init_db()"
```

### Node.js Frontend Setup
```powershell
cd frontend
npm install
npm run build
```

### macOS/Linux Local Bootstrap
```bash
# From the project root
cp .env.example .env  # only when .env does not already exist
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
python scripts/seed-users.py

cd frontend
npm install
```

`scripts/seed-users.py` is the repository's idempotent local demo-account bootstrap step. It initializes the SQLite schema, creates only missing demo accounts, and stores bcrypt hashes rather than plaintext passwords. It is intended for local development/evaluation; production accounts must be provisioned through the approved administrative process.

---

## 7. Environment Configuration (`.env`)

Configuration parameters are loaded from `.env` in the root directory:

```env
# Application Mode
APP_ENV=development
MODEL_MODE=local

# Network Settings
HOST=127.0.0.1
PORT=8000
OLLAMA_BASE_URL=http://localhost:11434

# Storage Paths (Project Relative)
AUTH_DB_PATH=data/private/aegis_auth.db
VECTOR_DB_PATH=./vectorstore
MODEL_DIR=./models

# Authentication Security
SECRET_KEY=CHANGE_ME
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Air-Gap Protection
ALLOW_EXTERNAL_APIS=false
```

> [!IMPORTANT]
> In production environments (`APP_ENV=production`), the application fails safely if `SECRET_KEY` remains set to the default `"CHANGE_ME"` placeholder value.

---

## 8. Verification & Testing Commands

* **Run Backend Test Suite (57 Unit Tests)**:
  ```powershell
  backend\.venv\Scripts\python -m unittest backend/tests/test_audit.py backend/tests/test_rbac.py backend/tests/test_auth.py backend/tests/test_model_management.py backend/tests/test_conversations.py backend/tests/test_embedding_generation.py backend/tests/test_similarity_retrieval.py backend/tests/test_rag_orchestration.py backend/tests/test_rag_ollama_integration.py
  ```

* **Run Frontend Unit Tests (34 Unit Tests)**:
  ```powershell
  cd frontend
  node --test tests/auth.test.js tests/chat.test.js tests/rag.test.js tests/models.test.js tests/truthfulness.test.js
  ```

* **Run Frontend Production Build**:
  ```powershell
  cd frontend
  npm run build
  ```

---

## 9. Security Warnings & Truthfulness Policy

* **Append-Only Application Audit Log**: System audit logs are written using parameterized SQL to local SQLite tables (`data/private/aegis_auth.db`). No application endpoints exist to edit or delete audit logs.
* **Truthfulness Requirement**: AEGIS UI displays real telemetry metrics fetched directly from local backends. Missing metrics are labeled `NOT REPORTED` or `UNAVAILABLE` rather than displaying hardcoded or simulated values.

---

## 10. Troubleshooting

* **Ollama Connection Refused**: Verify Ollama app is running (`http://localhost:11434/api/tags`).
* **Database Errors**: Delete temporary test DB files or run `powershell .\scripts\setup.ps1` to re-initialize schema.
* **401 Session Expired**: Expired JWT tokens automatically trigger local token clearance and single navigation redirect to `/login?expired=true`.
