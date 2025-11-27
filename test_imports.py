#!/usr/bin/env python
"""
Test the job functions directly without RQ.
"""
import os
import sys

# Add the project root to path
sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.dirname(os.path.abspath(__file__)))

try:
    print("Importing modules...")
    from module.jobs import upload_audio_to_assemblyai, transcribe_from_link
    print("✅ Successfully imported job functions")
    
    print(f"upload_audio_to_assemblyai: {upload_audio_to_assemblyai}")
    print(f"transcribe_from_link: {transcribe_from_link}")
    print(f"Function signatures:")
    import inspect
    print(f"  upload_audio_to_assemblyai: {inspect.signature(upload_audio_to_assemblyai)}")
    print(f"  transcribe_from_link: {inspect.signature(transcribe_from_link)}")
    
except Exception as e:
    print(f"❌ Error importing job functions: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ All imports successful")
