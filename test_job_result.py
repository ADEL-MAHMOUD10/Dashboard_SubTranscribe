#!/usr/bin/env python
"""
Debug script to check RQ job results.
Usage: python test_job_result.py <job_id>
"""
import sys
from rq import Queue
from rq.job import Job
from module.config import redis_connection

if len(sys.argv) < 2:
    print("Usage: python test_job_result.py <job_id>")
    sys.exit(1)

job_id = sys.argv[1]

try:
    job = Job.fetch(job_id, connection=redis_connection)
    
    print(f"Job ID: {job.id}")
    print(f"Status: {job.get_status()}")
    print(f"Is Failed: {job.is_failed}")
    print(f"Is Finished: {job.is_finished}")
    print(f"Meta: {job.meta}")
    print(f"Result: {job.result}")
    print(f"Exception: {job.exc_info}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
