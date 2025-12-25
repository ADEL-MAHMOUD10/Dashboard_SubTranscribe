import sys
import os
import requests
import time
from bson import ObjectId

# Add current directory to path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from module.config import files_collection, TOKEN_THREE
except ImportError:
    print("Error: Could not import from module.config. Make sure you are running this script from the project root.")
    sys.exit(1)

BASE_URL = "https://api.assemblyai.com/v2"
HEADERS = {"authorization": TOKEN_THREE}

def update_user_duration(user_id):
    """
    Fetches and updates missing audio_duration for a specific user's completed files.
    """
    print(f"\n--- Starting Duration Backfill for User: {user_id} ---")
    
    # Find completed files that are missing duration or have it as 0
    query = {
        'user_id': user_id, 
        'status': 'completed',
        '$or': [
            {'duration': {'$exists': False}},
            {'duration': 0},
            {'duration': None}
        ]
    }
    
    try:
        files = list(files_collection.find(query))
    except Exception as e:
        print(f"Database Error: {e}")
        return

    total = len(files)
    print(f"Found {total} files needing duration update.")
    
    if total == 0:
        print("No files to update.")
        return

    updated_count = 0
    errors = 0

    for i, file in enumerate(files):
        transcript_id = file.get('transcript_id')
        file_name = file.get('file_name', 'Unknown')
        
        if not transcript_id:
            print(f"[{i+1}/{total}] Skipping '{file_name}' (No transcript_id)")
            continue
            
        print(f"[{i+1}/{total}] Fetching duration for '{file_name}' ({transcript_id})... ", end='', flush=True)
        
        duration = 0
        try:
            # 1. Try Main Transcript Endpoint
            try:
                resp = requests.get(f"{BASE_URL}/transcript/{transcript_id}", headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    duration = data.get('audio_duration', 0)
            except requests.exceptions.RequestException:
                pass # Try fallback
            
            # 2. Fallback to Sentences Endpoint
            if not duration:
                try:
                    resp_s = requests.get(f"{BASE_URL}/transcript/{transcript_id}/sentences", headers=HEADERS, timeout=10)
                    if resp_s.status_code == 200:
                        data_s = resp_s.json()
                        duration = data_s.get('audio_duration', 0)
                except requests.exceptions.RequestException:
                    pass

            # Update if found
            if duration:
                files_collection.update_one(
                    {'_id': file['_id']},
                    {'$set': {'duration': duration}}
                )
                print(f"✅ Updated: {duration}s")
                updated_count += 1
            else:
                print("❌ Failed (API returned 0 or error)")
                errors += 1
                
        except Exception as e:
            print(f"❌ Error: {e}")
            errors += 1
            
        # Be polite to the API
        time.sleep(0.2)

    print(f"\n--- Completed ---")
    print(f"Successfully updated: {updated_count}")
    print(f"Failed/Missing: {errors}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        u_id = sys.argv[1]
    else:
        u_id = input("Enter User ID to update: ").strip()
    
    if u_id:
        update_user_duration(u_id)
    else:
        print("No User ID provided.")
