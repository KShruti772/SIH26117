# Aegis

## SIH26117 — Sovereign On-Premise Agentic AI Workbench

Aegis is a self-hosted, modular, agentic AI workbench designed for confidential industrial work.

### Core Goals

- Local AI inference
- No external AI APIs
- Open-weight models
- Model routing
- Multimodal document understanding
- Local RAG
- Agentic task execution
- Code sandbox
- Local file operations
- Real document deliverables
- Authentication and authorization
- Auditability
- Air-gapped deployment capability

## Architecture

User
↓
Secure Web UI
↓
Agent Controller
↓
Model Router
↓
Specialized Local Models
↓
Local Tools / RAG
↓
Verifier
↓
Deliverable

## Project Status

🚧 MVP under development

## Problem Statement

SIH26117

## Team

Team Aegis

## Development Setup

### Backend virtual environment setup
To initialize the backend environment on your local development machine:

1. **Create the virtual environment**:
   ```bash
   python -m venv backend/.venv
   ```

2. **Install dependencies**:
   ```bash
   backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
   ```

3. **Verify backend setup**:
   ```bash
   backend\.venv\Scripts\python.exe -c "import fastapi, pydantic, uvicorn, dotenv; print('Core imports verified!')"
   ```

## Authentication & Authorization

Aegis includes a self-contained, offline authentication system built with SQLite, bcrypt password hashing, and JWT tokens.

### Configuration
Update the `.env` file at the root of the workspace to configure token secrets and expiration times:
```env
# Authentication Configuration
SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
AUTH_DB_PATH=data/private/aegis_auth.db
```
> [!IMPORTANT]
> In production environments (`APP_ENV=production`), the application will fail safely if `SECRET_KEY` remains set to the default `"CHANGE_ME"` value.

### Starting the Backend
Launch the FastAPI uvicorn daemon:
```bash
backend\.venv\Scripts\python.exe backend\app\main.py
```

### API Endpoints
* **`POST /auth/register`**: Registers a new user. Passwords must be at least 8 characters. Users with usernames containing "admin" are automatically assigned the `admin` role; others receive the `user` role.
* **`POST /auth/login`**: Accepts `application/json` or `application/x-www-form-urlencoded` credentials. Returns a JWT access token and user info.
* **`GET /auth/me`**: Returns the profile details for the currently authenticated bearer token. Send the header `Authorization: Bearer <token>`.

### Roles & Security Controls
* **`user`**: Permitted to interact with RAG, code execution sandbox, document compilation, and request planning.
* **`admin`**: Full access, including user administration, configuration updates, and log auditing.
* **Brute-Force & Rate Limiting**: *Production requirement: persistent/distributed login rate limiting.*
* **Sovereignty**: All password hashes and registration tables reside locally in `data/private/aegis_auth.db` (git-ignored) with no cloud backdoors or telemetry hooks.

## Audit Logging Ledger

Aegis includes a structured, append-oriented local audit logging system to record security-sensitive operations.

### Stored Metadata
For each logged event, the ledger parameters capture:
* **Who**: `user_id`, `username`, and `role` (automatically resolved from context variable bindings).
* **What**: `action` (e.g. `AUTH_LOGIN`, `MODEL_SWITCH`, `SANDBOX_EXECUTION`, `RAG_SEARCH`, `VERIFICATION`).
* **When**: UTC `timestamp` generated automatically by SQLite.
* **Which Component**: name of the originating code module.
* **Correlation**: `request_id` (a unique UUID correlated across the entire execution flow).
* **Result**: `status` ("success" or "failure"), execution `duration_ms`, and `metadata_json`.

### Excluded Sensitive Data
To prevent privacy breaches, the audit logger enforces an allowlist of metadata keys. **It deliberately excludes**:
* Plaintext passwords or bcrypt hashes.
* JWT access tokens or Authorization headers.
* User query prompt text or generated model responses.
* Grounded passage snippets or source document contents.
* API keys or system secrets.

### Access Control
* **`GET /audit`**: Restricted strictly to the `admin` role. Returns the system log entries. Normal users attempting access will receive a `403 Forbidden` error.

> [!NOTE]
> *The MVP audit ledger is append-oriented but is not cryptographically tamper-proof.* True cryptographic signing and write-once-read-many (WORM) hardware storage are production enhancements.

## Private LAN Deployment

To deploy AEGIS on a local area network (LAN) for multi-machine on-premise access:

### 1. Configuration Settings
Ensure the `.env` file at the workspace root is updated to listen for external traffic. Set `HOST` to `0.0.0.0` (all interfaces):
```env
HOST=0.0.0.0
PORT=8000
OLLAMA_BASE_URL=http://localhost:11434
```
To restrict access to a specific Ethernet or Wi-Fi network card, bind to that specific LAN IP (e.g. `HOST=192.168.1.50`).

### 2. Startup Script
Aegis provides double-clickable launcher scripts in the `deployment/` directory to simplify startup and IP discovery on Windows:
* **Option A: PowerShell**
  Open a PowerShell terminal and run:
  ```powershell
  deployment\start_aegis.ps1
  ```
* **Option B: Command Prompt / Windows Explorer**
  Double-click `deployment\start_aegis.bat` to launch the server background processes.

During execution, the startup daemon automatically queries network adapters and lists all active IPv4 LAN addresses where AEGIS can be reached.

### 3. Verify Connection from another Machine
From another computer on the same subnet, open a web browser or use a command utility (like `curl`) to target the host machine's LAN IP:
```bash
curl http://<HOST_LAN_IP>:<PORT>/health
```
**Expected Response:**
```json
{
  "status": "ok"
}
```

### 4. Stopping the Service
Press `Ctrl+C` in the running PowerShell or Command Prompt console window to gracefully terminate the Uvicorn daemon.

## Offline Containerized Deployment

To deploy AEGIS inside Docker containers in an air-gapped environment without active internet access:

### 1. Preloading Docker Images (Connected Environment)
Before deploying on the air-gapped machine, build the image and export it to a tar archive on a machine with internet access:
```bash
# Build the backend container image
docker build -t aegis-backend:latest -f backend/Dockerfile .

# Save the image to a tarball archive
docker save -o aegis-backend-latest.tar aegis-backend:latest
```
Copy `aegis-backend-latest.tar` to the air-gapped server machine via physical media (e.g. USB drive).

### 2. Loading and Starting the Stack (Air-Gapped Environment)
On the air-gapped server, load the archived image:
```bash
# Load the prebuilt image from the tar archive
docker load -i aegis-backend-latest.tar

# Run the stack using Docker Compose
cd deployment/docker
docker compose up -d
```

### 3. Persistent Volumes
The `docker-compose.yml` mounts host directories using bind mounts to survive container recreation. The following directories are mapped:
* `data/private` -> `/app/data/private` (authentication & audit log SQLite database)
* `vectorstore` -> `/app/vectorstore` (local ChromaDB indices)
* `outputs` -> `/app/outputs` (generated docx/xlsx/pdf files)

### 4. Connecting to local Ollama on the GPU host
If the local Ollama daemon is running directly on the GPU host machine (rather than inside a docker container), update `.env` to route requests to the docker gateway:
```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### 5. Verify Health and Shutdown
* **Health Check**: Run `docker ps` to verify that the container is healthy (using the `/health` endpoint check).
* **Terminate Stack**: Run `docker compose down` in the `deployment/docker` directory.




