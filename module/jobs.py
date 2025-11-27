"""
Background job handlers for transcription processing using RQ (Redis Queue).
These jobs handle uploading media to AssemblyAI and polling for transcription completion.
"""
import requests
import yt_dlp
import uuid
import os
import time
import gc
import tempfile
from datetime import datetime, timezone
from loguru import logger
from module.config import files_collection, users_collection, TOKEN_THREE


def get_model():
    """Get the speech model for transcription (default: universal)."""
    return 'universal'


def upload_audio_to_assemblyai(job, upload_id, audio_file_path, file_size, username, user_id, upload_time):
    """
    Upload audio file to AssemblyAI and poll for transcription completion.
    
    Args:
        job: RQ job object for status updates
        upload_id: Unique upload identifier
        audio_file_path: Path to the audio file
        file_size: Size of the audio file in bytes
        username: Username of the uploader
        user_id: User ID of the uploader
        upload_time: Upload timestamp (as ISO string)
        
    Returns:
        str: Transcript ID on success
        dict: Error dict on failure
    """
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    
    # Parse upload_time if it's a string
    if isinstance(upload_time, str):
        try:
            upload_time = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
        except:
            upload_time = datetime.now(timezone.utc)
    
    logger.info(f"[Job {job.id}] Starting file upload: {audio_file_path}")
    try:
        job.meta['status'] = 'uploading'
        job.save_meta()
        
        # Upload file to AssemblyAI
        with open(audio_file_path, 'rb') as f:
            response = requests.post(
                f"{base_url}/upload",
                headers=headers,
                data=f.read(),
                timeout=120
            )
        
        if response.status_code != 200:
            error_msg = f"Upload failed with status code {response.status_code}"
            logger.error(error_msg)
            return {'error': error_msg}
        
        upload_url = response.json().get("upload_url")
        if not upload_url:
            error_msg = "No upload URL received from AssemblyAI"
            logger.error(error_msg)
            return {'error': error_msg}
        
        logger.info(f"✅ File uploaded to AssemblyAI: {upload_url}")
        
        # Start transcription
        job.meta['status'] = 'transcribing'
        job.save_meta()
        
        data = {"audio_url": upload_url, "speech_model": get_model()}
        response = requests.post(
            f"{base_url}/transcript",
            json=data,
            headers=headers,
            timeout=60
        )
        
        if response.status_code != 200:
            error_msg = "Failed to start transcription"
            logger.error(error_msg)
            return {'error': error_msg}
        
        transcript_id = response.json()["id"]
        logger.info(f"Transcript ID: {transcript_id}")
        
        # Store initial file record with transcript_id
        files_collection.insert_one({
            "username": username,
            "user_id": user_id,
            "file_name": os.path.basename(audio_file_path),
            "file_size": file_size,
            "transcript_id": transcript_id,
            "upload_time": upload_time,
            "job_id": job.id,
            "status": "processing"
        })
        
        # Poll for completion
        polling_endpoint = f"{base_url}/transcript/{transcript_id}"
        
        for i in range(120):  # Poll for up to 10 minutes (30 sec × 120)
            try:
                job.meta['status'] = 'processing'
                job.meta['progress'] = f"Transcribing... ({i}/120)"
                job.save_meta()
                
                resp = requests.get(polling_endpoint, headers=headers, timeout=30)
                result = resp.json()
                
                if result["status"] == "completed":
                    logger.info("🎉 Transcription completed")
                    
                    # Update file record with completion status
                    files_collection.update_one(
                        {'transcript_id': transcript_id},
                        {'$set': {'status': 'completed'}}
                    )
                    
                    gc.collect()
                    return transcript_id
                
                if result["status"] == "error":
                    error_msg = result.get('error', 'Unknown transcription error')
                    logger.error(f"Transcription error: {error_msg}")
                    
                    # Update file record with error status
                    files_collection.update_one(
                        {'transcript_id': transcript_id},
                        {'$set': {'status': 'error', 'error_message': error_msg}}
                    )
                    
                    return {'error': f"Transcription failed: {error_msg}"}
                
                # Exponential backoff: start with 5 sec, cap at 30 sec
                wait_time = min(5 * (2 ** (i // 20)), 30)
                time.sleep(wait_time)
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"Polling request failed (attempt {i+1}): {e}")
                time.sleep(5)
                continue
        
        error_msg = "Transcription timed out after 10 minutes"
        logger.error(error_msg)
        files_collection.update_one(
            {'transcript_id': transcript_id},
            {'$set': {'status': 'timeout'}}
        )
        return {'error': error_msg}
    
    except Exception as e:
        logger.error(f"[Job {job.id}] Upload/transcription error: {e}", exc_info=True)
        return {'error': f"An error occurred: {str(e)[:100]}"}
    
    finally:
        # Clean up temp file if it exists
        if os.path.exists(audio_file_path):
            try:
                os.remove(audio_file_path)
                logger.info(f"[Job {job.id}] ✅ Temp file cleaned: {audio_file_path}")
            except Exception as e:
                logger.warning(f"[Job {job.id}] Could not remove temp file {audio_file_path}: {e}")


def transcribe_from_link(job, upload_id, link, username, user_id, upload_time):
    """
    Download media from link and transcribe using AssemblyAI.
    
    Args:
        job: RQ job object for status updates
        upload_id: Unique upload identifier
        link: Media link (YouTube, etc.)
        username: Username of the uploader
        user_id: User ID of the uploader
        upload_time: Upload timestamp (as ISO string)
        
    Returns:
        str: Transcript ID on success
        dict: Error dict on failure
    """
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    downloaded_file = None
    
    # Parse upload_time if it's a string
    if isinstance(upload_time, str):
        try:
            upload_time = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
        except:
            upload_time = datetime.now(timezone.utc)
    
    logger.info(f"[Job {job.id}] Starting link transcription: {link}")
    try:
        job.meta['status'] = 'downloading'
        job.meta['progress'] = 'Downloading media...'
        job.save_meta()
        
        # Download media using yt-dlp
        temp_dir = tempfile.gettempdir()
        temp_base = f"ytdl_{uuid.uuid4().hex[:8]}"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, temp_base + '.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
        
        logger.info(f"[Job {job.id}] Downloading media from: {link}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            downloaded_file = ydl.prepare_filename(info)
        
        logger.info(f"[Job {job.id}] Downloaded to: {downloaded_file}")
        
        total_size = os.path.getsize(downloaded_file)
        if total_size == 0:
            raise ValueError("Downloaded file is empty")
        
        logger.info(f"📦 Downloaded file: {downloaded_file} ({total_size} bytes)")
        
        # Upload to AssemblyAI
        job.meta['status'] = 'uploading'
        job.meta['progress'] = 'Uploading to transcription service...'
        job.save_meta()
        
        with open(downloaded_file, 'rb') as f:
            upload_res = requests.post(
                f"{base_url}/upload",
                headers=headers,
                data=f.read(),
                timeout=600
            )
        
        upload_res.raise_for_status()
        upload_url = upload_res.json().get('upload_url')
        
        if not upload_url:
            raise ValueError("No upload URL received from AssemblyAI")
        
        logger.info("✅ Link file uploaded to AssemblyAI")
        
        # Start transcription
        job.meta['status'] = 'transcribing'
        job.meta['progress'] = 'Starting transcription...'
        job.save_meta()
        
        data = {"audio_url": upload_url, "speech_model": get_model()}
        response = requests.post(
            f"{base_url}/transcript",
            json=data,
            headers=headers,
            timeout=300
        )
        
        if response.status_code != 200:
            return {'error': f"Transcription failed with code {response.status_code}"}
        
        transcript_id = response.json()["id"]
        logger.info(f"Transcript ID: {transcript_id}")
        
        # Store initial file record with transcript_id
        files_collection.insert_one({
            "username": username,
            "user_id": user_id,
            "file_name": link,
            "file_size": total_size,
            "transcript_id": transcript_id,
            "upload_time": upload_time,
            "link": link,
            "job_id": job.id,
            "status": "processing"
        })
        
        # Poll for completion
        polling_endpoint = f"{base_url}/transcript/{transcript_id}"
        
        for i in range(120):  # Poll for up to 10 minutes
            try:
                job.meta['status'] = 'processing'
                job.meta['progress'] = f"Transcribing... ({i}/120)"
                job.save_meta()
                
                resp = requests.get(polling_endpoint, headers=headers, timeout=30)
                result = resp.json()
                
                if result["status"] == "completed":
                    logger.info("🎉 Link transcription completed")
                    
                    # Update file record with completion status
                    files_collection.update_one(
                        {'transcript_id': transcript_id},
                        {'$set': {'status': 'completed'}}
                    )
                    
                    gc.collect()
                    return transcript_id
                
                if result["status"] == "error":
                    error_msg = result.get('error', 'Unknown transcription error')
                    logger.error(f"Transcription error: {error_msg}")
                    
                    # Update file record with error status
                    files_collection.update_one(
                        {'transcript_id': transcript_id},
                        {'$set': {'status': 'error', 'error_message': error_msg}}
                    )
                    
                    return {'error': "Transcription failed. Please try a different media file."}
                
                # Exponential backoff
                wait_time = min(5 * (2 ** (i // 20)), 60)
                time.sleep(wait_time)
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"Polling request failed (attempt {i+1}): {e}")
                time.sleep(5)
                continue
        
        error_msg = "Transcription timed out after 10 minutes"
        logger.error(error_msg)
        files_collection.update_one(
            {'transcript_id': transcript_id},
            {'$set': {'status': 'timeout'}}
        )
        return {'error': error_msg}
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"[Job {job.id}] AssemblyAI upload error: {e.response.status_code} - {e.response.text}")
        return {'error': f"Failed to upload to transcription service: {e.response.status_code}"}
    
    except Exception as e:
        logger.error(f"[Job {job.id}] Link processing error: {e}", exc_info=True)
        return {'error': f"An error occurred: {str(e)[:100]}"}
    
    finally:
        # Clean up temp file
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                os.remove(downloaded_file)
                logger.info(f"[Job {job.id}] ✅ Temp file cleaned: {downloaded_file}")
            except OSError as e:
                logger.warning(f"[Job {job.id}] Could not remove temp file: {e}")
