# Multi-stage Docker build for production-ready Python backend
FROM python:3.12-slim AS builder

# Install system dependencies
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install the exact production dependency graph recorded from the supported
# Linux/Python 3.12 runtime, then install this package without re-resolving it.
COPY pyproject.toml requirements.lock ./
COPY src/ ./src/

# hadolint ignore=DL3013
RUN pip install --no-cache-dir -r requirements.lock && \
    pip install --no-cache-dir --no-deps .

# Production stage
FROM python:3.12-slim AS production

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Install runtime dependencies including CA certificates for SSL/TLS
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/

# Set SSL environment variables
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Change ownership to app user and create .local directory
RUN chown -R app:app /app && \
    mkdir -p /home/app/.local && \
    chown -R app:app /home/app/.local

# Switch to non-root user
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/health')"

# Start application
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
