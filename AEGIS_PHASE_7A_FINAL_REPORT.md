# AEGIS Phase 7A — Reproducible Environment & Cross-Laptop Deployment Final Report

## 1. Files Added
* `[AEGIS_PHASE_7A_ENVIRONMENT_AUDIT.md](file:///d:/SIH26117/AEGIS_PHASE_7A_ENVIRONMENT_AUDIT.md)` — Comprehensive audit document detailing project architecture, configuration variables, storage locations, and machine dependency risks.
* `[scripts/check-environment.ps1](file:///d:/SIH26117/scripts/check-environment.ps1)` — Automated environment diagnostic script verifying Python, Node, NPM, virtualenv, `.env`, SQLite DB, ChromaDB, Ollama daemon, and model availability with real runtime metrics.
* `[scripts/setup.ps1](file:///d:/SIH26117/scripts/setup.ps1)` — Automated environment setup script creating `.env`, virtual environment `backend/.venv`, pip packages, npm dependencies, directory infrastructure (`data/private`, `data/knowledge_base`), and SQLite schema initialization.
* `[scripts/prepare-models.ps1](file:///d:/SIH26117/scripts/prepare-models.ps1)` — Interactive model inspection script querying local Ollama daemon for required tags (`gemma3:4b`) and prompting user before executing `ollama pull`.
* `[scripts/start-backend.ps1](file:///d:/SIH26117/scripts/start-backend.ps1)` — Portable PowerShell script launching the FastAPI backend service using relative project paths.
* `[scripts/start-frontend.ps1](file:///d:/SIH26117/scripts/start-frontend.ps1)` — Portable PowerShell script launching the Next.js frontend development server.

---

## 2. Files Modified
* `[README.md](file:///d:/SIH26117/README.md)` — Comprehensive architecture, installation, air-gap operations, environment configuration, and quick-start deployment guide.

---

## 3. Machine-Specific Dependencies Removed
* All backend settings (`[backend/app/config/settings.py](file:///d:/SIH26117/backend/app/config/settings.py)`) and file storage utilities resolve relative paths (`data/private/aegis_auth.db`, `./vectorstore`, `data/knowledge_base`).
* Hardcoded absolute machine paths (`D:\SIH26117`) have been audited and replaced with relative path calculations across all launcher scripts.
* Database initialization automatically creates missing directory structures on fresh machines.

---

## 4. Environment Variables

| Variable Name | Default Value | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | Deployment environment mode (`development` / `production`). |
| `MODEL_MODE` | `local` | Execution mode (`local` / `airgapped`). |
| `MODEL_DIR` | `./models` | Directory path for local HuggingFace embedding weights. |
| `VECTOR_DB_PATH` | `./vectorstore` | Local ChromaDB vector database index directory. |
| `AUTH_DB_PATH` | `data/private/aegis_auth.db` | Local SQLite database file path. |
| `SECRET_KEY` | `CHANGE_ME` | HMAC-SHA256 secret key for signing JWT tokens. |
| `HOST` | `127.0.0.1` | Bind IP for FastAPI uvicorn daemon (`0.0.0.0` for LAN). |
| `PORT` | `8000` | Port for FastAPI uvicorn daemon. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint URL for local Ollama inference server. |
| `ALLOW_EXTERNAL_APIS` | `false` | Sovereign guard blocking external cloud APIs. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base API URL configured for Next.js frontend client. |

---

## 5. Setup & Startup Process

1. **Environment Setup**: `powershell .\scripts\setup.ps1`
2. **Environment Diagnostic Verification**: `powershell .\scripts\check-environment.ps1`
3. **Model Preparation**: `powershell .\scripts\prepare-models.ps1`
4. **Backend Daemon Launch**: `powershell .\scripts\start-backend.ps1`
5. **Frontend Service Launch**: `powershell .\scripts\start-frontend.ps1`

---

## 6. Ollama & Model Requirements

* **Local Inference Engine**: Ollama daemon installed and running locally on `http://localhost:11434`.
* **Primary Verified Model**: `gemma3:4b` (4B open-weight multimodal model).
* **Secondary Model Option**: `qwen3:4b` / `qwen2.5-3b-instruct`.
* **Embedding Model**: `all-MiniLM-L6-v2` (Local SentenceTransformer embedding model).

---

## 7. Database & ChromaDB Behavior

* **Fresh Installation**: Automatically creates `data/private/aegis_auth.db` and populates `users`, `audit_logs`, `conversations`, and `messages` tables.
* **Knowledge Base Storage**: `data/knowledge_base/` holds uploaded TXT and PDF documents per tenant.
* **VectorStore Initialization**: ChromaDB creates `./vectorstore` on first document upload. If no documents are uploaded, the UI and API accurately report `KNOWLEDGE BASE EMPTY`.

---

## 8. Internet Requirements & Air-Gap Assumptions

* **Installation Phase (Internet Required)**:
  - Downloading Python wheels via `pip install -r backend/requirements.txt`.
  - Downloading NPM packages via `npm install`.
  - Downloading Ollama installer from `https://ollama.com`.
  - Downloading model weights via `ollama pull gemma3:4b` and HuggingFace embedding weights.
* **Runtime Phase (Air-Gapped Sovereign Execution)**:
  - 100% local execution. No cloud API calls (OpenAI, Anthropic, Gemini, cloud vector stores) are permitted or executed.

---

## 9. Exact Test & Build Verification Results

* **Python Backend Unit Tests (`57/57 PASS`)**:
  ```text
  Ran 57 tests in 18.337s
  OK
  ```
* **Node Frontend Unit Tests (`34/34 PASS`)**:
  ```text
  # tests 34
  # pass 34
  # fail 0
  # duration_ms 176.2ms
  ```
* **Next.js Production Build**:
  ```text
  ▲ Next.js 16.3.3 (Turbopack)
  ✓ Compiled successfully in 969ms
  Finished TypeScript in 2.4s ...
  ✓ Generating static pages using 6 workers (5/5) in 823ms
  ```

---

## 10. Remaining Limitations

* **OCR Tesseract Binary**: Image OCR parsing relies on `pytesseract`. If Tesseract OCR binary is not installed on host OS, PDF text extraction uses PyMuPDF native text layer fallback.

---

## NEW LAPTOP QUICK START

```powershell
# 1. Copy or clone AEGIS project repository to target directory (e.g. C:\AEGIS)
cd C:\AEGIS

# 2. Run automated setup script
powershell .\scripts\setup.ps1

# 3. Run environment health check
powershell .\scripts\check-environment.ps1

# 4. Check & prepare local Ollama model weights
powershell .\scripts\prepare-models.ps1

# 5. Launch backend daemon
powershell .\scripts\start-backend.ps1

# 6. Open a second terminal window and launch frontend service
powershell .\scripts\start-frontend.ps1

# 7. Access AEGIS Workbench in browser
# Open http://localhost:3000
```

---

*Phase 7A Completed and Verified. Stopping execution as instructed before Phase 7B.*
