# ─── Stage 1: Build dependencies ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies for psycopg2-binary & kaleido
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─── Stage 2: Production image ────────────────────────────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Create a non-root user for security
RUN useradd -m -u 1001 queryiq && \
    mkdir -p /app/data && \
    chown -R queryiq:queryiq /app

# Copy application source code
COPY --chown=queryiq:queryiq . .

# Switch to non-root user
USER queryiq

# ─── Health check ─────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${BACKEND_PORT:-8000}/api/health || exit 1

# ─── Runtime ──────────────────────────────────────────────────────────────────
EXPOSE ${BACKEND_PORT:-8000}

# Use exec form to receive OS signals correctly (graceful shutdown)
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8000} --workers 2 --no-access-log"]
