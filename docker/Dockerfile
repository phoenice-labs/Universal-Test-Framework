# ──────────────────────────────────────────────────────────────────────────────
# Universal Test Framework — Dockerfile
# Builds a minimal, non-root container for the MCP server (HTTP/SSE mode).
# ──────────────────────────────────────────────────────────────────────────────

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency spec first (layer cache optimization)
COPY pyproject.toml ./

# Install deps into a prefix dir
RUN pip install --no-cache-dir --prefix=/install \
    "fastmcp>=3.0.0,<4.0.0" \
    pyyaml==6.0.2 \
    jinja2==3.1.4 \
    pydantic==2.7.1 \
    httpx==0.27.0 \
    uvicorn==0.29.0 \
    starlette==0.37.2 \
    rich==13.7.1 \
    click==8.1.7

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

LABEL maintainer="Universal Test Framework" \
      description="Polyglot test generation MCP server" \
      version="1.0.0"

# Security: non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 utf

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=utf:utf mcp_server/ ./mcp_server/
COPY --chown=utf:utf rules/ ./rules/
COPY --chown=utf:utf templates/ ./templates/

# Create the registry directory so the volume mount can write to it
RUN mkdir -p /app/.utf && chown utf:utf /app/.utf

# Switch to non-root user
USER utf

# Expose HTTP port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

# Default: start in HTTP/SSE mode
CMD ["python", "-m", "mcp_server.server", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
