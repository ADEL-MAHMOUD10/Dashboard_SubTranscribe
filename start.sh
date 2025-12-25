#!/bin/bash
set -e

# Start the RQ worker in the background
echo "Starting RQ Worker..."
python worker.py &

# Start Gunicorn (Web Server)
# Using exec to replace the shell with gunicorn process
echo "Starting Gunicorn..."
exec gunicorn \
    --workers=1 \
    --threads=1 \
    --worker-class=sync \
    --worker-connections=1000 \
    --max-requests=1000 \
    --max-requests-jitter=100 \
    --timeout=300 \
    --graceful-timeout=60 \
    --keep-alive=60 \
    --log-level=info \
    --access-logfile=- \
    --error-logfile=- \
    --bind=0.0.0.0:5000 \
    --preload \
    --worker-tmp-dir=/dev/shm \
    --forwarded-allow-ips=* \
    --proxy-allow-from=* \
    app:app
