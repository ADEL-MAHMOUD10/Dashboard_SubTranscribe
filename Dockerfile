FROM python:3.11-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies in a single RUN command to reduce layers
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg gcc && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get remove -y gcc && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Optimize Python memory usage for containerized environments
ENV PYTHONMALLOC=malloc
ENV PYTHONHASHSEED=random

# Add GC optimization
ENV PYTHONGC=aggressive

# Copy application code
COPY . .

# Expose the port
EXPOSE 8000

# Use gunicorn with gevent worker for better async handling (optimized for limited resources)
CMD ["gunicorn", "--workers=2", "--threads=2", "--worker-class=sync", "--max-requests=1000", "--max-requests-jitter=50", "--timeout=900", "--graceful-timeout=300", "--keep-alive=120", "--log-level=info", "--bind=0.0.0.0:5000", "app:app"]
