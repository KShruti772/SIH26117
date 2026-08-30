# AEGIS Phase 7A — Environment & Reproducibility Security Audit

## 1. Current Project Structure

```text
D:\SIH26117/
├── backend/
│   ├── app/
│   │   ├── config/
│   │   │   └── settings.py           # Application environment configuration using Pydantic Settings
│   │   ├── verification/             # Grounding verifier engine
│   │   └── main.py                   # FastAPI application entry point & router definitions
│   ├── agents/                       # Controller and conversation state management
│   ├── models/                       # Registry, loaders, and switching manager
│   ├── rag/                          # Embeddings, chunking, and ChromaDB pipeline
│   ├── security/                     # Auth, database initialization, audit logger, dependencies
│   ├── tools/                        # Code sandbox and document generator tools
│   ├── tests/                        # 57 Python backend unit tests
│   └── requirements.txt              # Backend dependencies requirements file
├── frontend/
│   ├── app/                          # Next.js App Router pages (Dashboard, Login, Chat, RAG, Models, Audit)
│   ├── components/                   # UI components, Layout, Sidebar, Header, AuthGuard
│   ├── lib/                          # API clients (client.ts, auth.ts, audit.ts, models.ts, rag.ts, health.ts)
│   ├── tests/                        # 34 Node.js frontend unit tests
│   ├── package.json                  # Next.js, React 19, Tailwind dependencies
│   └── next.config.ts                # Next.js configuration
├── scripts/                          # Setup, check, and execution scripts
├── deployment/                       # LAN deployment launcher scripts & Docker configs
├── data/
│   ├── private/                      # Local SQLite databases (aegis_auth.db) — Git Ignored
│   └── knowledge_base/               # Uploaded RAG document files — Git Ignored
├── vectorstore/                      # Local persistent ChromaDB vector index — Git Ignored
├── .env                              # Active environment configuration — Git Ignored
├── .env.example                      # Template environment configuration
├── README.md                         # Architecture & setup instructions
└── IMPLEMENTATION_STATUS.md          # Verification status ledger
```

---

## 2. Current Dependencies

### Backend Python Dependencies (`backend/requirements.txt`):
* `fastapi==0.141.1` — Async REST API framework
* `uvicorn==0.52.4` — ASGI server
* `pydantic==2.13.4` & `pydantic-settings==2.15.0` — Validation & configuration management
* `python-dotenv==1.2.3` — Environment variable loading
* `python-multipart==0.0.32` — Multipart form-data handling for document uploads
* `pypdf` & `pymupdf==1.25.3` — PDF text parsing and rendering
* `chromadb` — Local persistent vector database
* `sentence-transformers==3.3.0` — Local embedding model execution
* `pytesseract==0.3.13` — Local OCR extraction wrapper
* `python-docx==1.1.2`, `openpyxl==3.1.5`, `reportlab==4.3.1` — Local document generation (DOCX, XLSX, PDF)
* `bcrypt==4.1.2` — Password hashing
* `PyJWT==2.8.0` — Standard signed JWT token issuance & validation
* `Pillow==12.3.0` — Image processing
* `httpx2` — Async HTTP client for Ollama API communication

### Frontend Dependencies (`frontend/package.json`):
* `next: 16.3.3`
* `react: 19.2.8`
* `react-dom: 19.2.8`
* `lucide-react: ^1.34.0`
* `tailwindcss: ^4`
* `@types/node`, `@types/react`, `@types/react-dom`, `typescript: ^5`

---

## 3. Current Startup Process

1. **Backend**:
   * Executed via `uvicorn backend.app.main:app` or `python backend/app/main.py`.
   * Listens on `HOST` (default `127.0.0.1`) and `PORT` (default `8000`).
   * Automatically invokes `init_db()` in `[backend/security/database.py](file:///d:/SIH26117/backend/security/database.py)` on startup.
2. **Frontend**:
   * Executed via `npm run dev` in `frontend/` (development) or `npm run build && npm start` (production).
   * Listens on port `3000`.
   * Targets backend via `process.env.NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000` in `[frontend/lib/config/env.ts](file:///d:/SIH26117/frontend/lib/config/env.ts)`).

---

## 4. All Environment Variables Discovered

| Variable Name | Default Value | Usage Location | Purpose |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | `development` | `backend/app/config/settings.py` | Environment mode (`development` vs `production`). Enforces `SECRET_KEY` check in production. |
| `MODEL_MODE` | `local` | `backend/app/config/settings.py` | Model execution mode (`local` vs `airgapped`). |
| `MODEL_DIR` | `./models` | `backend/app/config/settings.py` | Path to local cached HuggingFace models (e.g. `all-MiniLM-L6-v2`). |
| `DATABASE_URL` | `""` | `backend/app/config/settings.py` | Database connection URL placeholder. |
| `VECTOR_DB_PATH` | `./vectorstore` | `backend/app/config/settings.py` | Storage path for local ChromaDB persistent index. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `backend/app/config/settings.py` | URL endpoint for local Ollama inference server. |
| `SECRET_KEY` | `CHANGE_ME` | `backend/app/config/settings.py` | HMAC-SHA256 secret key for signing JWT tokens. |
| `JWT_ALGORITHM` | `HS256` | `backend/app/config/settings.py` | JWT signature algorithm. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | `backend/app/config/settings.py` | Access token lifespan. |
| `AUTH_DB_PATH` | `data/private/aegis_auth.db` | `backend/app/config/settings.py` | Path to local SQLite auth database. |
| `HOST` | `127.0.0.1` | `backend/app/config/settings.py` | Bind IP for FastAPI uvicorn backend. |
| `PORT` | `8000` | `backend/app/config/settings.py` | Bind port for FastAPI uvicorn backend. |
| `ALLOW_EXTERNAL_APIS` | `false` | `backend/app/config/settings.py` | Sovereign guard flag blocking external cloud endpoints. |
| `CORS_ORIGINS` | `["http://localhost:3000", ...]` | `backend/app/config/settings.py` | Allowed CORS origins list. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `frontend/lib/config/env.ts` | Backend API base URL for frontend fetch calls. |

---

## 5. All Persistent Storage Locations

1. **Authentication & Audit Ledger**: `data/private/aegis_auth.db` (SQLite database containing `users`, `audit_logs`, `conversations`, `messages` tables).
2. **RAG Vector Database Index**: `./vectorstore` (ChromaDB persistent collection files).
3. **Uploaded Knowledge Base Files**: `data/knowledge_base/` (Physical TXT/PDF files uploaded by operators).
4. **Local Embedding Model Weight Storage**: `models/all-MiniLM-L6-v2` (Local SentenceTransformer weights).

---

## 6. All External / Local Runtime Dependencies

1. **Local Ollama Daemon**: `http://localhost:11434` (Inference engine for LLM weights such as `gemma3:4b` or `qwen3:4b`).
2. **Python Runtime**: Python 3.12+ with virtual environment `backend/.venv`.
3. **Node.js Runtime**: Node.js v20+ with `npm`.
4. **Tesseract OCR (Optional)**: Local binary for image-to-text OCR processing (`pytesseract`).

---

## 7. Absolute Paths & Machine-Specific Hardcoded References Audit

* **Source Code Inspection**: All source code paths use relative paths or environment settings (e.g. `data/private/aegis_auth.db`, `./vectorstore`, `backend/models/registry/registry.json`).
* **Documentation & Specifications**: References to `D:\SIH26117` exist inside documentation files (`IMPLEMENTATION_STATUS.md`, `PROJECT_MASTER_SPEC.md`).
* **Conclusion**: Source code has zero hardcoded absolute Windows paths, making relative path execution fully portable across system directories (`C:\AEGIS`, `D:\Projects\AEGIS`, etc.).

---

## 8. All Hardcoded Ports

* Backend Default Port: `8000`
* Frontend Default Port: `3000`
* Ollama Default Port: `11434`

---

## 9. All Hardcoded Model References

* Default Fallback Active Model: `gemma3:4b` (Configured in `[backend/models/registry/registry.json](file:///d:/SIH26117/backend/models/registry/registry.json)` and `[backend/models/loaders/manager.py](file:///d:/SIH26117/backend/models/loaders/manager.py)`).
* Secondary Discovered Model: `qwen3:4b` / `qwen2.5-3b-instruct`.
* Local Embedding Model: `all-MiniLM-L6-v2`.

---

## 10. Current Setup Assumptions & Cross-Laptop Risks

1. **Missing Ollama Installation**: If a new laptop does not have Ollama installed or running on `localhost:11434`, model switching and chat inference calls fail.
2. **Missing Local Embedding Weights**: If `models/all-MiniLM-L6-v2` is not present, `get_local_embedding_model` downloads weights or raises error.
3. **Uninitialized Databases**: If `data/private` or `vectorstore` directories do not exist, runtime initialization must create them cleanly without crashing.
4. **Uninitialized `.env`**: If `.env` is missing on a new laptop, settings default to `SECRET_KEY="CHANGE_ME"` and `127.0.0.1:8000`.

---

## 11. Proposed Minimal Fixes & Reproducibility Plan

1. **Create Verification Script (`scripts/check-environment.ps1`)**:
   Perform real, non-simulated runtime checks for Python version, Node/NPM, backend dependencies, frontend dependencies, Ollama daemon status, installed Ollama models, SQLite database, ChromaDB vector store, and `.env` configuration.
2. **Create Setup Script (`scripts/setup.ps1`)**:
   Automate virtual environment creation, pip installation of `requirements.txt`, npm package installation, directory creation (`data/private`, `data/knowledge_base`), `.env` creation from `.env.example`, and fresh SQLite database schema initialization.
3. **Create Model Preparation Script (`scripts/prepare-models.ps1`)**:
   Query local Ollama daemon for installed tags, detect missing required models (`gemma3:4b`), and offer explicit user-prompted model pulling via `ollama pull`.
4. **Create Daemon Launcher Scripts (`scripts/start-backend.ps1`, `scripts/start-frontend.ps1`)**:
   Provide clean, portable execution scripts for backend and frontend servers.
5. **Update README.md**:
   Add clear, step-by-step cross-laptop quick start documentation and air-gap operational guidance.

---

*Audit Complete. Proceeding to implementation of Phase 7A scripts and setup automation.*
