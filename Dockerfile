# ── Stage 1: Build dependencies ─────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build-time system dependencies for asyncpg (C extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime image ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid 1001 --no-create-home appuser

WORKDIR /app

# Runtime system deps only (libpq for asyncpg SSL connections)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appgroup . .

# Ensure cogs package is importable
RUN touch cogs/__init__.py

USER appuser

# Expose health check port
EXPOSE 8080

# Health check — Docker will restart the container if /health 500s for 3 mins
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:8080/health || exit 1

# Use exec form so SIGTERM reaches Python directly (not wrapped in shell)
ENTRYPOINT ["python", "-u", "bot.py"]
