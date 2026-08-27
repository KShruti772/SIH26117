# AEGIS Backend Environment Setup Documentation

This document describes the environment setup process for the AEGIS Python backend.

## System Target Configuration

### Development Host (Current Host)
* **CPU:** Intel Core i7-13620H
* **System RAM:** 16 GB
* **GPU:** Intel UHD integrated graphics (No discrete NVIDIA GPU)
* **CUDA Support:** None (Runs on CPU only)

### Primary Local Inference Host (Target Runtime Host)
* **GPU:** NVIDIA RTX 4050 (6 GB VRAM)
* **System RAM:** 16 GB
* **Storage:** 512 GB SSD
* **CUDA Support:** Enabled via NVIDIA CUDA drivers

---

## Setup Steps

### 1. Prerequisite Checks
Confirm Python 3.12 is installed and reachable via the terminal:
```bash
python --version
```
*Current host version:* `Python 3.12.8`

### 2. Create the Virtual Environment
Create the virtual environment inside `backend/.venv`:
```bash
python -m venv backend/.venv
```

### 3. Install Backend Dependencies
Upgrade pip and install the base packages listed in `backend/requirements.txt`:
```bash
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
```

Core dependencies installed:
* `fastapi==0.141.1`
* `pydantic==2.13.4`
* `pydantic-settings==2.15.0`
* `python-dotenv==1.2.3`
* `python-multipart==0.0.32`
* `uvicorn==0.52.4`
* `starlette==1.6.0`

### 4. Verification Check
Verify that the virtual environment works and that the core components can be imported without error:
```bash
backend\.venv\Scripts\python.exe -c "import fastapi, pydantic, uvicorn, dotenv; print('All core modules imported successfully')"
```

---

## GPU & CUDA Capabilities Detection

On the **Development Host**, querying video controllers returns only the integrated GPU:
* **GPU Adapter:** `Intel(R) UHD Graphics`
* **CUDA Availability:** FAILED (No NVIDIA GPU hardware present).
* **Inference Mode:** Development runs must fallback to local Ollama CPU inference or interface with a separate local inference workstation.

For the **Primary Local Inference Host**, ensure that `nvidia-smi` is added to the system path and running. The inference configuration will target Ollama running with hardware acceleration.
