# Use official lightweight Python runtime as base
FROM python:3.12-slim

# Install system dependencies (curl is needed for health-checks)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy python requirements list
COPY backend/requirements.txt .

# Install dependencies using pip cache restrictions
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code files into container
COPY backend/ /app/backend/

# Copy workspace default configuration values
COPY .env.example .env

# Expose FastAPI listening port
EXPOSE 8000

# Ensure PYTHONPATH points to root to load backend packages correctly
ENV PYTHONPATH=/app

# Run uvicorn server in non-interactive background mode
CMD ["python", "backend/app/main.py"]
