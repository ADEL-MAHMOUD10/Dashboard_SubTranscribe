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

# Copy application code
COPY . .

# Expose the port
EXPOSE 8000

# Use gunicorn as the entry point
CMD ["gunicorn", "--workers=2", "--threads=4", "--worker-class=gthread", "--max-requests=100", "--max-requests-jitter=10", "--timeout=600", "--bind=0.0.0.0:8000", "app:app"]