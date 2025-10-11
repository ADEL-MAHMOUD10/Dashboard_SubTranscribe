# Multi-stage build for optimized production image

# -------------------------
# Builder stage
# -------------------------
FROM python:3.13-slim as builder

# Set build arguments
ARG DEBIAN_FRONTEND=noninteractive
ARG PIP_NO_CACHE_DIR=1
ARG PIP_DISABLE_PIP_VERSION_CHECK=1
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION

# Add labels for better image management
LABEL maintainer="SubTranscribe Team" \
      version="${VERSION}" \
      description="SubTranscribe AI Transcription Service" \
      build-date="${BUILD_DATE}" \
      vcs-ref="${VCS_REF}"

# Install system dependencies for building
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        libjpeg-dev \
        libpng-dev \
        libfreetype6-dev \
        liblcms2-dev \
        libwebp-dev \
        libharfbuzz-dev \
        libfribidi-dev \
        libxcb1-dev \
        pkg-config \
        && rm -rf /var/lib/apt/lists/* \
        && apt-get clean

# Create virtual environment with specific Python version
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python dependencies with security updates
COPY requirements.txt .

RUN sed -i '/^DateTime$/d;/^Python-IO$/d' requirements.txt
RUN pip install --upgrade pip==23.3.1 setuptools==68.2.2 wheel==0.41.2 && \
    pip install --no-cache-dir --upgrade -r requirements.txt && \
    pip check

# -------------------------
# Production stage
# -------------------------
FROM python:3.13-slim as production

# Set build arguments for production
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION
ARG FLASK_ENV=production

# Set production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONMALLOC=malloc \
    PYTHONHASHSEED=random \
    PYTHONGC=aggressive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    FLASK_ENV=${FLASK_ENV} \
    PYTHONPATH=/app \
    TZ=UTC

# Install runtime dependencies with security updates
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
        libgcc-s1 \
        libstdc++6 \
        ca-certificates \
        curl \
        dumb-init \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/* \
        && apt-get autoremove -y \
        && apt-get autoclean

# Create non-root user with specific UID/GID for security
RUN groupadd -r -g 1001 appuser && \
    useradd -r -g appuser -u 1001 -d /app -s /bin/bash appuser

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code with proper ownership and permissions
COPY --chown=appuser:appuser . .

# Create necessary directories with secure permissions
RUN mkdir -p /app/temp /app/logs /app/uploads /app/cache && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app/temp /app/logs /app/uploads /app/cache && \
    chmod 644 /app/*.py /app/*.txt /app/*.md 2>/dev/null || true

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5000

# Add comprehensive health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Use dumb-init for proper signal handling
ENTRYPOINT ["dumb-init", "--"]

# Production-optimized gunicorn configuration
CMD ["gunicorn", \
     "--workers=1", \
     "--threads=1", \
     "--worker-class=sync", \
     "--worker-connections=1000", \
     "--max-requests=1000", \
     "--max-requests-jitter=100", \
     "--timeout=300", \
     "--graceful-timeout=60", \
     "--keep-alive=60", \
     "--log-level=info", \
     "--access-logfile=-", \
     "--error-logfile=-", \
     "--bind=0.0.0.0:5000", \
     "--preload", \
     "--worker-tmp-dir=/dev/shm", \
     "--forwarded-allow-ips=*", \
     "--proxy-allow-from=*", \
     "app:app"]
