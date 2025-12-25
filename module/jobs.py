"""
Improved background job handlers with better error handling and streaming uploads.
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
from typing import Dict, Union
from requests.exceptions import RequestException, Timeout, HTTPError


class TranscriptionError(Exception):
    """Custom exception for transcription errors."""
    pass


class UploadError(Exception):
    """Custom exception for upload errors."""
    pass


def get_model():
    """Get the speech model for transcription (default: universal)."""
    return 'universal'


def upload_file_streaming(file_path: str, headers: dict, base_url: str, chunk_size: int = 8192) -> str:
    """
    Upload file to AssemblyAI using streaming to avoid memory issues.
    
    Args:
        file_path: Path to file
        headers: Authorization headers
        base_url: API base URL
        chunk_size: Size of chunks to stream (default 8KB)
        
    Returns:
        str: Upload URL from AssemblyAI
        
    Raises:
        UploadError: If upload fails
    """
    try:
        file_size = os.path.getsize(file_path)
        logger.info(f"Starting streaming upload: {file_size} bytes")
        
        # Stream upload in chunks to avoid loading entire file into memory
        def file_generator():
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        
        response = requests.post(
            f"{base_url}/upload",
            headers=headers,
            data=file_generator(),
            timeout=300  # 5 minutes timeout
        )
        
        if response.status_code != 200:
            raise UploadError(f"Upload failed with status {response.status_code}: {response.text}")
        
        upload_url = response.json().get("upload_url")
        if not upload_url:
            raise UploadError("No upload URL received from AssemblyAI")
        
        logger.info(f"✅ File uploaded successfully: {upload_url}")
        return upload_url
        
    except FileNotFoundError:
        raise UploadError(f"File not found: {file_path}")
    except Timeout:
        raise UploadError("Upload timed out after 5 minutes")
    except HTTPError as e:
        raise UploadError(f"HTTP error during upload: {e}")
    except Exception as e:
        raise UploadError(f"Unexpected upload error: {str(e)}")


def poll_transcription(transcript_id: str, headers: dict, base_url: str, 
                       max_attempts: int = 130) -> Dict:
    """
    Poll for transcription completion with exponential backoff.
    
    Args:
        transcript_id: Transcript ID to poll
        headers: Authorization headers
        base_url: API base URL
        max_attempts: Max polling attempts (default 130, approx 20 mins)
        
    Returns:
        dict: Transcription result
        
    Raises:
        TranscriptionError: If transcription fails or times out
    """
    from rq import get_current_job
    job = get_current_job()
    
    polling_endpoint = f"{base_url}/transcript/{transcript_id}"
    
    for attempt in range(max_attempts):
        try:
            # Update job progress
            if job:
                job.meta['status'] = 'processing'
                job.meta['progress'] = f"Transcribing... ({attempt + 1}/{max_attempts})"
                job.save_meta()
            
            # Poll transcription status
            response = requests.get(polling_endpoint, headers=headers, timeout=30)
            result = response.json()
            
            status = result.get("status")
            logger.debug(f"Poll #{attempt + 1}: status={status}")
            
            if status == "completed":
                logger.info(f"🎉 Transcription completed: {transcript_id}")
                return result
            
            if status == "error":
                error_msg = result.get('error', 'Unknown transcription error')
                raise TranscriptionError(f"Transcription failed: {error_msg}")
            
            # Exponential backoff: 5s, 10s , 10s is max
            wait_time = min(5 * (2 ** (attempt // 20)), 10)
            time.sleep(wait_time)
            
        except Timeout:
            logger.warning(f"Polling timeout (attempt {attempt + 1})")
            if attempt < max_attempts - 1:
                time.sleep(5)
                continue
            raise TranscriptionError("Polling timed out repeatedly")
        
        except RequestException as e:
            logger.warning(f"Polling request failed (attempt {attempt + 1}): {e}")
            if attempt < max_attempts - 1:
                time.sleep(5)
                continue
            raise TranscriptionError(f"Network error during polling: {str(e)}")
    
    raise TranscriptionError("Transcription timed out after repeated attempts")


def upload_audio_to_assemblyai(upload_id: str, audio_file_path: str, file_size: int,
                               username: str, user_id: str, upload_time: str) -> Union[str, Dict]:
    """
    Upload audio file to AssemblyAI and poll for transcription completion.
    Improved version with better error handling and streaming upload.
    
    Args:
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
    from rq import get_current_job
    
    job = get_current_job()
    if job is None:
        logger.error("CRITICAL: Job context not available")
        return {'error': 'Job context not available'}
    
    job_id = job.id
    logger.info(f"[Job {job_id}] ========== JOB START ==========")
    logger.info(f"[Job {job_id}] upload_id={upload_id}, file={audio_file_path}, size={file_size}")
    
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    
    # Parse upload_time
    if isinstance(upload_time, str):
        try:
            upload_time = str(datetime.fromisoformat(upload_time.replace('Z', '+00:00')))
        except:
            upload_time = str(datetime.now(timezone.utc))
    
    try:
        # Verify file exists
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")
        
        # Update job status
        job.meta['status'] = 'uploading'
        job.meta['progress'] = 'Uploading file...'
        job.save_meta()
        
        # Upload file using streaming
        upload_url = upload_file_streaming(audio_file_path, headers, base_url)
        
        # Start transcription
        job.meta['status'] = 'transcribing'
        job.meta['progress'] = 'Starting transcription...'
        job.save_meta()
        
        data = {"audio_url": upload_url, "speech_model": get_model()}
        response = requests.post(
            f"{base_url}/transcript",
            json=data,
            headers=headers,
            timeout=60
        )
        
        if response.status_code != 200:
            raise TranscriptionError(f"Failed to start transcription: {response.status_code}")
        
        transcript_id = response.json()["id"]
        logger.info(f"[Job {job_id}] Transcript ID: {transcript_id}")
        
        # Store initial file record
        files_collection.update_one(
            {'job_id': job.id},
            {'$set': {
                "transcript_id": transcript_id,
                "status": "processing"
            }}
        )
        
        # Poll for completion
        result = poll_transcription(transcript_id, headers, base_url)
        
        if result.get('status') == 'error':
            raise TranscriptionError(result.get('error', 'Unknown transcription error'))
            
        if result.get('status') == 'completed':
            # Update job meta to completion
            job.meta['status'] = 'completed'
            job.meta['progress'] = 'Finalizing...'
            job.save_meta()
            
            duration = result.get('audio_duration') or 0
            # Update file record
            files_collection.update_one(
                {'transcript_id': transcript_id},
                {'$set': {'status': 'completed', 'duration': duration}}
            )
        
        logger.info(f"[Job {job_id}] ✅ Returning transcript_id: {transcript_id}")
        gc.collect()
        return transcript_id
    
    except FileNotFoundError as e:
        error_msg = str(e)
        logger.error(f"[Job {job_id}] File error: {error_msg}")
        return {'error': 'File not found or was deleted'}
    
    except UploadError as e:
        error_msg = str(e)
        logger.error(f"[Job {job_id}] Upload error: {error_msg}")
        return {'error': 'Failed to upload file. Please try again.'}
    
    except TranscriptionError as e:
        error_msg = str(e)
        logger.error(f"[Job {job_id}] Transcription error: {error_msg}")
        
        # Update file record with error
        if 'transcript_id' in locals():
            files_collection.update_one(
                {'transcript_id': transcript_id},
                {'$set': {'status': 'error', 'error_message': error_msg}}
            )
        
        return {'error': 'Transcription failed. Please try again with a different file.'}
    
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"[Job {job_id}] {error_msg}", exc_info=True)
        return {'error': 'An unexpected error occurred. Please contact support.'}
    
    finally:
        # Clean up temp file
        if os.path.exists(audio_file_path):
            try:
                os.remove(audio_file_path)
                logger.info(f"[Job {job_id}] ✅ Temp file cleaned: {audio_file_path}")
            except Exception as e:
                logger.warning(f"[Job {job_id}] Could not remove temp file: {e}")


def transcribe_from_link(upload_id: str, link: str, username: str, 
                        user_id: str, upload_time: str) -> Union[str, Dict]:
    """
    Download media from link and transcribe using AssemblyAI.
    Improved version with better error handling.
    
    Args:
        upload_id: Unique upload identifier
        link: Media link (YouTube, etc.)
        username: Username of the uploader
        user_id: User ID of the uploader
        upload_time: Upload timestamp (as ISO string)
        
    Returns:
        str: Transcript ID on success
        dict: Error dict on failure
    """
    from rq import get_current_job
    
    job = get_current_job()
    if job is None:
        logger.error("CRITICAL: Job context not available")
        return {'error': 'Job context not available'}
    
    job_id = job.id
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    downloaded_file = None
    
    logger.info(f"[Job {job_id}] Starting link transcription: {link}")
    
    # Parse upload_time
    if isinstance(upload_time, str):
        try:
            upload_time = str(datetime.fromisoformat(upload_time.replace('Z', '+00:00')))
        except:
            upload_time = str(datetime.now(timezone.utc))
    
    try:
        # Update status
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
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            downloaded_file = ydl.prepare_filename(info)
        
        if not os.path.exists(downloaded_file):
            raise FileNotFoundError(f"Downloaded file not found: {downloaded_file}")
        
        total_size = os.path.getsize(downloaded_file)
        if total_size == 0:
            raise ValueError("Downloaded file is empty")
        
        logger.info(f"[Job {job_id}] ✅ Downloaded: {total_size} bytes")
        
        # Upload to AssemblyAI using streaming
        job.meta['status'] = 'uploading'
        job.meta['progress'] = 'Uploading to transcription service...'
        job.save_meta()
        
        upload_url = upload_file_streaming(downloaded_file, headers, base_url)
        
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
            raise TranscriptionError(f"Failed to start transcription: {response.status_code}")
        
        transcript_id = response.json()["id"]
        logger.info(f"[Job {job_id}] Transcript ID: {transcript_id}")
        
        # Store initial file record
        files_collection.update_one(
            {'job_id': job.id},
            {'$set': {
                "transcript_id": transcript_id,
                "file_size": total_size,
                "file_name": info.get('title', link),
                "status": "processing"
            }}
        )
        
        # Poll for completion
        result = poll_transcription(transcript_id, headers, base_url)
        
        # Update job meta
        job.meta['status'] = 'completed'
        job.meta['progress'] = 'Finalizing...'
        job.save_meta()
        
        duration = result.get('audio_duration') or 0
        # Update file record
        files_collection.update_one(
            {'transcript_id': transcript_id},
            {'$set': {'status': 'completed', 'duration': duration}}
        )
        
        logger.info(f"[Job {job_id}] ✅ Returning transcript_id: {transcript_id}")
        gc.collect()
        return transcript_id
    
    except yt_dlp.utils.DownloadError as e:
        error_msg = f"Failed to download media: {str(e)}"
        logger.error(f"[Job {job_id}] {error_msg}")
        return {'error': 'Failed to download media. Please check the link and try again.'}
    
    except FileNotFoundError as e:
        logger.error(f"[Job {job_id}] File error: {e}")
        return {'error': 'Downloaded file not found'}
    
    except UploadError as e:
        logger.error(f"[Job {job_id}] Upload error: {e}")
        return {'error': 'Failed to upload file. Please try again.'}
    
    except TranscriptionError as e:
        logger.error(f"[Job {job_id}] Transcription error: {e}")
        if 'transcript_id' in locals():
            files_collection.update_one(
                {'transcript_id': transcript_id},
                {'$set': {'status': 'error', 'error_message': str(e)}}
            )
        return {'error': 'Transcription failed. Please try a different media file.'}
    
    except Exception as e:
        logger.error(f"[Job {job_id}] Unexpected error: {e}", exc_info=True)
        return {'error': f"An unexpected error occurred: {str(e)[:100]}"}
    
    finally:
        # Clean up temp file
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                os.remove(downloaded_file)
                logger.info(f"[Job {job_id}] ✅ Temp file cleaned: {downloaded_file}")
            except OSError as e:
                logger.warning(f"[Job {job_id}] Could not remove temp file: {e}")