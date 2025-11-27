#!/usr/bin/env python
"""
RQ Worker process for SubTranscribe.
Starts a worker that processes transcription jobs from the Redis queue.

Usage:
    python worker.py
    
Environment variables required:
    - REDIS_URI: Redis connection string (e.g., redis://localhost:6379/0)
    - M_api_key: MongoDB connection string
    - A_api_key: AssemblyAI API key
"""
import sys
import os
from dotenv import load_dotenv
from rq import Worker, Queue
import redis

# Load environment variables
load_dotenv()

# Get Redis URI from environment
REDIS_URI = os.getenv("REDIS_URI")

if not REDIS_URI:
    print("❌ Error: REDIS_URI environment variable not set")
    print("Please add REDIS_URI to your .env file")
    sys.exit(1)

try:
    # Create Redis connection (don't decode responses - RQ needs binary data)
    redis_conn = redis.from_url(REDIS_URI, socket_connect_timeout=2, socket_timeout=2)
    redis_conn.ping()
    print(f"✅ Connected to Redis: {REDIS_URI}")
except Exception as e:
    print(f"❌ Failed to connect to Redis: {e}")
    sys.exit(1)

# Create queue
queue = Queue('transcription', connection=redis_conn)

print(f"🚀 Starting RQ Worker...")
print(f"   Listening on queue: {queue.name}")
print(f"   Press Ctrl+C to stop")
print()

# Start worker
try:
    worker = Worker([queue], connection=redis_conn)
    worker.work(with_scheduler=False)
except KeyboardInterrupt:
    print("\n⛔ Worker stopped by user")
    sys.exit(0)
except Exception as e:
    print(f"❌ Worker error: {e}")
    sys.exit(1)
