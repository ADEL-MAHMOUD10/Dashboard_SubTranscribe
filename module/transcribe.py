from flask import Blueprint, session, redirect, url_for, request, render_template, flash, jsonify
from module.config import users_collection, files_collection, TOKEN_THREE, is_session_valid, q
from module.jobs import upload_audio_to_assemblyai, transcribe_from_link as transcribe_from_link_job
from datetime import datetime, timezone
from module.send_mail import send_email_transcript
from loguru import logger
import uuid
import os
import tempfile
import io
import requests
import time

transcribe_bp = Blueprint('transcribe', __name__)


# ------------------- Helper Functions -------------------

def allowed_file(filename):
    EXTENSIONS = {'.mp4', '.wmv', '.mov', '.mkv', '.h.264', '.mp3', '.wav'}
    return '.' in filename and os.path.splitext(filename)[1].lower() in EXTENSIONS


def generate_error_id():
    return str(uuid.uuid4())


def get_model():
    model = request.form.get('model', 'universal')
    valid_models = {'slam-1', 'universal', 'voxtral-mini-2507', 'whisper-large-v3'}
    return model if model in valid_models else 'universal'


# ------------------- Fallback Synchronous Transcription (if RQ unavailable) -------------------

def sync_upload_audio_to_assemblyai(audio_file_path, file_size):
    """Synchronous file upload to AssemblyAI (fallback when RQ unavailable)."""
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    
    try:
        # Upload file
        with open(audio_file_path, 'rb') as f:
            response = requests.post(
                f"{base_url}/upload",
                headers=headers,
                data=f.read(),
                timeout=120
            )
        
        if response.status_code != 200:
            return {'error': f"Upload failed: {response.status_code}"}
        
        upload_url = response.json().get("upload_url")
        data = {"audio_url": upload_url, "speech_model": get_model()}
        
        response = requests.post(f"{base_url}/transcript", json=data, headers=headers, timeout=60)
        if response.status_code != 200:
            return {'error': "Failed to start transcription"}
        
        transcript_id = response.json()["id"]
        logger.info(f"Transcript ID: {transcript_id}")
        
        # Poll for completion (blocking)
        polling_endpoint = f"{base_url}/transcript/{transcript_id}"
        for i in range(120):
            resp = requests.get(polling_endpoint, headers=headers, timeout=30)
            result = resp.json()
            
            if result["status"] == "completed":
                logger.info("🎉 Transcription completed")
                return transcript_id
            
            if result["status"] == "error":
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Transcription error: {error_msg}")
                return {'error': f"Transcription failed: {error_msg}"}
            
            time.sleep(min(5 * (2 ** (i // 20)), 30))
        
        return {'error': "Transcription timed out"}
    
    except Exception as e:
        logger.error(f"Sync upload error: {e}")
        return {'error': f"An error occurred: {str(e)[:100]}"}


# ------------------- Routes -------------------

@transcribe_bp.route('/transcribe/<user_id>')
def transcribe_page(user_id):
    if 'user_id' not in session or not is_session_valid():
        return redirect(url_for('auth.login'))
    upload_id = str(uuid.uuid4())
    session['upload_id'] = upload_id
    return render_template('transcribe.html', upload_id=upload_id, user_id=session['user_id'])


@transcribe_bp.route('/v1', methods=['POST'])
def upload_or_link():
    """Handle file upload or media link submission for transcription."""
    if 'user_id' not in session or not is_session_valid():
        return redirect(url_for('auth.login'))

    user_id = session.get('user_id')
    user = users_collection.find_one({'user_id': user_id})
    upload_id = session.get('upload_id')
    username = user.get('username', 'Unknown') if user else 'Unknown'
    upload_time = datetime.now(timezone.utc)
    err_id = generate_error_id()

    link = request.form.get('link')
    if link:
        # Handle media link transcription (download then transcribe)
        try:
            logger.info(f"Processing link: {link}")

            # If background queue available, enqueue a job that will download+transcribe
            if q:
                flash("Your link has been queued for processing. You can monitor progress.", "info")
                # Convert datetime to ISO string for RQ serialization (datetime objects don't pickle well across processes)
                upload_time_str = upload_time.isoformat() if hasattr(upload_time, 'isoformat') else str(upload_time)
                job = q.enqueue(transcribe_from_link_job, upload_id, link, username, user_id, upload_time_str, job_timeout=3600)

                # Insert a placeholder record so users can see the queued job
                files_collection.insert_one({
                    "username": username,
                    "user_id": user_id,
                    "file_name": link,
                    "file_size": 0,
                    "transcript_id": None,
                    "upload_time": upload_time,
                    "link": link,
                    "job_id": job.id,
                    "status": "queued",
                    "source": "link"
                })

                return redirect(url_for('transcribe.job_status_page', job_id=job.id))

            # No queue: perform synchronous download + transcription (existing behavior)
            flash("Downloading media... This may take a few minutes.", "info")
            import yt_dlp
            from pathlib import Path

            temp_dir = tempfile.gettempdir()
            output_template = os.path.join(temp_dir, "download_%(id)s.%(ext)s")

            # Configure yt-dlp options
            ydl_opts = {
                'format': 'best[ext=mp4]/best[ext=mkv]/best',
                'outtmpl': output_template,
                'quiet': False,
                'no_warnings': True,
            }

            # Download the media
            download_path = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=True)
                download_path = ydl.prepare_filename(info)

            if not download_path or not os.path.exists(download_path):
                session['error'] = "Failed to download media from link"
                return redirect(url_for('show_error', error_id=err_id))

            try:
                file_size = os.path.getsize(download_path)
                logger.info(f"Downloaded: {download_path}, size: {file_size}")

                # Transcribe the downloaded file
                flash("Processing your media... This may take 5-15 minutes. Please wait.", "warning")
                result = sync_upload_audio_to_assemblyai(download_path, file_size)

                if isinstance(result, dict) and 'error' in result:
                    session['error'] = result['error']
                    return redirect(url_for('show_error', error_id=err_id))

                # Save file record
                files_collection.insert_one({
                    "username": username,
                    "user_id": user_id,
                    "file_name": link.split('/')[-1][:100],  # Use last part of URL
                    "file_size": file_size,
                    "transcript_id": result,
                    "upload_time": upload_time,
                    "source": "link"
                })

                return redirect(url_for('subtitle.download_subtitle', user_id=user_id, transcript_id=result))
            finally:
                # Clean up downloaded file
                if download_path and os.path.exists(download_path):
                    try:
                        os.remove(download_path)
                        logger.info(f"Cleaned up: {download_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete temp file {download_path}: {e}")

        except Exception as e:
            logger.error(f"Link download error: {e}")
            session['error'] = f"Failed to process link: {str(e)[:150]}"
            return redirect(url_for('show_error', error_id=err_id))
    
    file = request.files.get('file')
    if file and allowed_file(file.filename):
        try:
            logger.info(f"[Upload] Starting file upload process for: {file.filename}")
            file_size = request.content_length or 0
            
            # If RQ queue is available, enqueue the upload job and return job status page
            if q:
                logger.info("[Upload] RQ Queue available, enqueuing job")
                temp_dir = tempfile.gettempdir()
                ext = os.path.splitext(file.filename or 'audio')[1] if file.filename else ''
                temp_filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
                temp_path = os.path.join(temp_dir, temp_filename)
                
                logger.info(f"[Upload] Saving file to: {temp_path}")
                file.save(temp_path)
                
                # Verify file was saved
                if not os.path.exists(temp_path):
                    error_msg = f"Failed to save file to {temp_path}"
                    logger.error(f"[Upload] {error_msg}")
                    session['error'] = error_msg
                    return redirect(url_for('show_error', error_id=err_id))

                # Convert datetime to ISO string for RQ serialization
                upload_time_str = upload_time.isoformat() if hasattr(upload_time, 'isoformat') else str(upload_time)
                
                logger.info(f"[Upload] Enqueueing job with transcript ID: {upload_id}")
                # Enqueue job; the worker will upload and clean up the temp file
                job = q.enqueue(upload_audio_to_assemblyai, upload_id, temp_path, file_size, username, user_id, upload_time_str, job_timeout=3600)
                logger.info(f"[Upload] Job enqueued successfully with ID: {job.id}")

                files_collection.insert_one({
                    "username": username,
                    "user_id": user_id,
                    "file_name": file.filename,
                    "file_size": file_size,
                    "transcript_id": None,
                    "upload_time": upload_time,
                    "job_id": job.id,
                    "status": "queued"
                })
                logger.info(f"[Upload] File record inserted into database with job_id: {job.id}")

                flash("Your file has been queued for processing. You can monitor progress.", "info")
                
                redirect_url = url_for('transcribe.job_status_page', job_id=job.id)
                logger.info(f"[Upload] Redirecting to: {redirect_url}")
                return redirect(redirect_url)

            # Fallback synchronous processing when no queue is available
            logger.info("Using synchronous file transcription")
            flash("Processing your file... This may take 5-15 minutes. Please don't close this page.", "warning")

            # Save temp file and process synchronously
            temp_dir = tempfile.gettempdir()
            ext = os.path.splitext(file.filename or 'audio')[1] if file.filename else ''
            temp_filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
            temp_path = os.path.join(temp_dir, temp_filename)
            file.save(temp_path)

            try:
                result = sync_upload_audio_to_assemblyai(temp_path, file_size)

                if isinstance(result, dict) and 'error' in result:
                    session['error'] = result['error']
                    return redirect(url_for('show_error', error_id=err_id))

                # Save file record
                files_collection.insert_one({
                    "username": username,
                    "user_id": user_id,
                    "file_name": file.filename,
                    "file_size": file_size,
                    "transcript_id": result,
                    "upload_time": upload_time
                })

                return redirect(url_for('subtitle.download_subtitle', user_id=user_id, transcript_id=result))
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
        
        except Exception as e:
            logger.error(f"Upload error: {e}")
            session['error'] = f"Upload error: {str(e)[:100]}"
            return redirect(url_for('show_error', error_id=err_id))
    else:
        session['error'] = "Invalid file type or no file provided"
        return redirect(url_for('show_error', error_id=err_id))
    
@transcribe_bp.route('/job_status_page/<job_id>')
def job_status_page(job_id):
    """Display a page that polls for job completion."""
    logger.info(f"[job_status_page] Accessing job_status_page for job_id: {job_id}")
    logger.info(f"[job_status_page] user_id in session: {'user_id' in session}")
    
    token = session.get('session_token')
    token_preview = token[:20] + "..." if token else None
    logger.info(f"[job_status_page] session: user_id={session.get('user_id')}, token={token_preview}")
    
    if 'user_id' not in session:
        logger.warning(f"[job_status_page] No user_id in session, redirecting to login")
        return redirect(url_for('auth.login'))
    
    is_valid = is_session_valid()
    logger.info(f"[job_status_page] is_session_valid() returned: {is_valid}")
    
    if not is_valid:
        logger.warning(f"[job_status_page] Session validation failed, redirecting to login")
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    logger.info(f"[job_status_page] Rendering job_status.html for user_id={user_id}, job_id={job_id}")
    download_url_template = url_for('subtitle.download_subtitle', user_id=user_id, transcript_id='__transcript_id__')
    return render_template('job_status.html', 
                           job_id=job_id, 
                           user_id=user_id, 
                           download_url_template=download_url_template)

@transcribe_bp.route('/job_status/<job_id>')
def job_status(job_id):
    """Get the status of a background transcription job (JSON API)."""
    if not q:
        return jsonify({'status': 'unavailable', 'error': 'Background processing not available'}), 503
    
    try:
        from rq.job import Job
        job = Job.fetch(job_id, connection=q.connection)
        
        # Get the basic job status from RQ
        rq_status = job.get_status()  # Returns: 'queued', 'started', 'finished', 'failed'
        
        # Build basic response
        response_data = {
            'job_id': job.id,
            'status': rq_status,
            'progress': job.meta.get('progress', ''),
            'meta': job.meta,
        }
        
        logger.info(f"[job_status API] Job {job_id}: rq_status={rq_status}, is_finished={job.is_finished}, is_failed={job.is_failed}")
        
        # If job is finished (completed successfully)
        if job.is_finished and not job.is_failed:
            result = job.result
            logger.info(f"[job_status API] Job {job_id} finished, result type: {type(result)}, value: {repr(result)[:100]}")
            
            # Check if result is an error dict
            if isinstance(result, dict) and 'error' in result:
                response_data['error'] = result['error']
                response_data['status'] = 'failed'
                logger.warning(f"[job_status API] Job {job_id} returned error dict: {result['error']}")
            elif result is None:
                # Job finished but returned None
                meta_status = job.meta.get('status', 'unknown')
                response_data['error'] = f'Job completed but returned no result. Meta status: {meta_status}'
                response_data['status'] = 'failed'
                logger.error(f"[job_status API] Job {job_id} finished with None result")
            else:
                # Success! Return the transcript ID
                response_data['result'] = result
                response_data['status'] = 'finished'  # Explicitly set to 'finished'
                logger.info(f"[job_status API] Job {job_id} succeeded with transcript_id: {result}")
        
        # If job failed
        elif job.is_failed:
            response_data['error'] = job.exc_info or 'Job failed without error message'
            response_data['status'] = 'failed'
            logger.error(f"[job_status API] Job {job_id} is_failed=True, exc_info: {job.exc_info}")
        
        # For queued/started/processing jobs, keep the RQ status
        else:
            logger.debug(f"[job_status API] Job {job_id} still in progress: {rq_status}")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"[job_status API] Error fetching job status for {job_id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 400