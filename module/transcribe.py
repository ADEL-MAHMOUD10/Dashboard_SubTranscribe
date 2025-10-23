from flask import Blueprint, session, redirect, url_for, request, render_template, flash
from module.config import users_collection, files_collection, TOKEN_THREE, is_session_valid
from datetime import datetime, timezone
from module.send_mail import send_email_transcript
from loguru import logger
import requests
import yt_dlp
import uuid
import os
import time
import gc
import tempfile
import threading

transcribe_bp = Blueprint('transcribe', __name__)

# Thread-safe upload lock
upload_semaphore = threading.Semaphore(value=1)


# ------------------- Helper Functions -------------------

def allowed_file(filename):
    EXTENSIONS = {'.mp4', '.wmv', '.mov', '.mkv', '.h.264', '.mp3', '.wav'}
    return '.' in filename and os.path.splitext(filename)[1].lower() in EXTENSIONS


def generate_error_id():
    return str(uuid.uuid4())


def cleanup_upload_memory(file_content=None):
    """Clean up memory - Flask manages file streams automatically."""
    try:
        if file_content:
            del file_content
        gc.collect()
        logger.info("✅ Memory cleaned up")
    except Exception as e:
        logger.error(f"⚠️ Cleanup error: {e}")


def get_model():
    model = request.form.get('model', 'universal')
    valid_models = {'slam-1', 'universal', 'voxtral-mini-2507', 'whisper-large-v3'}
    return model if model in valid_models else 'universal'


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
        result = transcribe_from_link(upload_id, link, username, user_id, upload_time)
        if isinstance(result, dict) and 'error' in result:
            session['error'] = result['error']
            return redirect(url_for('show_error', error_id=err_id))
        if isinstance(result, str):
            return redirect(url_for('subtitle.download_subtitle', user_id=user_id, transcript_id=result))
        session['error'] = 'Link could not be processed.'
        return redirect(url_for('show_error', error_id=err_id))
    
    file = request.files.get('file')
    if file and allowed_file(file.filename):
        try:
            file_size = request.content_length or 0
            transcript_id = upload_audio_to_assemblyai(upload_id, file, file_size)
            
            if isinstance(transcript_id, dict) and 'error' in transcript_id:
                session['error'] = transcript_id['error']
                return redirect(url_for('show_error', error_id=err_id))

            files_collection.insert_one({
                "username": username,
                "user_id": user_id,
                "file_name": file.filename,
                "file_size": file_size,
                "transcript_id": transcript_id,
                "upload_time": upload_time
            })

            return redirect(url_for('subtitle.download_subtitle', user_id=user_id, transcript_id=transcript_id))

        except Exception as e:
            logger.error(f"Upload error: {e}")
            session['error'] = f"Upload error: {str(e)[:100]}"
            return redirect(url_for('show_error', error_id=err_id))
    else:
        session['error'] = "Invalid file type or no file provided"
        return redirect(url_for('show_error', error_id=err_id))


# ------------------- Core Logic -------------------

def upload_audio_to_assemblyai(upload_id, audio_file, file_size):
    """Upload file directly to AssemblyAI - Flask manages file stream."""
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"

    with upload_semaphore:
        try:
            def upload_chunks(chunk_size=5242880):
                while True:
                    chunk = audio_file.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

            response = requests.post(f"{base_url}/upload", headers=headers, data=upload_chunks(), timeout=120)
            if response.status_code != 200:
                return {'error': f"Upload failed with status code {response.status_code}"}

            upload_url = response.json().get("upload_url")
            data = {"audio_url": upload_url, "speech_model": get_model()}

            response = requests.post(f"{base_url}/transcript", json=data, headers=headers, timeout=60)
            if response.status_code != 200:
                return {'error': "Failed to start transcription"}

            transcript_id = response.json()["id"]
            logger.info(f"Transcript ID: {transcript_id}")
            polling_endpoint = f"{base_url}/transcript/{transcript_id}"

            for i in range(30):
                resp = requests.get(polling_endpoint, headers=headers, timeout=30)
                result = resp.json()

                if result["status"] == "completed":
                    logger.info("🎉 Transcription completed")
                    gc.collect()
                    return transcript_id
                    
                if result["status"] == "error":
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"Transcription error: {error_msg}")
                    return {'error': f"Transcription failed: {error_msg}"}

                time.sleep(min(5 * (2 ** (i // 5)), 30))

            return {'error': "Transcription timed out. Try a shorter file."}

        except Exception as e:
            logger.error(f"Upload error: {e}")
            return {'error': f"An error occurred: {str(e)[:100]}"}


def transcribe_from_link(upload_id, link, username, user_id, upload_time):
    """Process video/audio link for transcription."""
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"

    with upload_semaphore:
        file_path_mp3 = None
        downloaded_file = None
        try:
            # Create temp file with dynamic extension
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
            
            # Verify file exists and has content
            if not os.path.exists(downloaded_file):
                raise FileNotFoundError(f"Downloaded file not found: {downloaded_file}")
            
            total_size = os.path.getsize(downloaded_file)
            if total_size == 0:
                raise ValueError("Downloaded file is empty")
            
            logger.info(f"📦 Downloaded file: {downloaded_file} ({total_size} bytes)")
            
            # Detect proper content type
            ext = os.path.splitext(downloaded_file)[1].lower()
            content_type_map = {
                '.mp3': 'audio/mpeg',
                '.mp4': 'audio/mp4',
                '.m4a': 'audio/mp4',
                '.wav': 'audio/wav',
                '.webm': 'audio/webm',
                '.ogg': 'audio/ogg',
                '.opus': 'audio/opus',
            }
            content_type = content_type_map.get(ext, 'audio/mpeg')
            
            # Upload to AssemblyAI
            with open(downloaded_file, 'rb') as f:
                upload_res = requests.post(
                    f"{base_url}/upload", 
                    headers=headers,
                    data=f.read(),  # Send as raw data, not multipart
                    timeout=600
                )

            upload_res.raise_for_status()
            upload_url = upload_res.json().get('upload_url')
            
            if not upload_url:
                raise ValueError("No upload URL received from AssemblyAI")
            
            logger.info("✅ Link file uploaded to AssemblyAI")

        except requests.exceptions.HTTPError as e:
            logger.error(f"AssemblyAI upload error: {e.response.status_code} - {e.response.text}")
            return {'error': f"Failed to upload to transcription service: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Link download error: {e}")
            return {'error': "Unable to process this media link. Please ensure it's from a supported platform."}
        finally:
            if downloaded_file and os.path.exists(downloaded_file):
                try:
                    os.remove(downloaded_file)
                    logger.info(f"✅ Temp file cleaned: {downloaded_file}")
                except OSError as e:
                    logger.warning(f"⚠️ Could not remove temp file: {e}")

        try:
            data = {"audio_url": upload_url, "speech_model": get_model()}
            response = requests.post(f"{base_url}/transcript", json=data, headers=headers, timeout=300)
            
            if response.status_code != 200:
                return {'error': f"Transcription failed with code {response.status_code}"}

            transcript_id = response.json()["id"]
            logger.info(f"Transcript ID: {transcript_id}")
            
            # Store link info in database
            files_collection.insert_one({
                "username": username,
                "user_id": user_id,
                "file_name": link,
                "file_size": total_size,
                "transcript_id": transcript_id,
                "upload_time": upload_time,
                "link": link
            })
            
            polling_endpoint = f"{base_url}/transcript/{transcript_id}"

            for i in range(30):
                resp = requests.get(polling_endpoint, headers=headers, timeout=30)
                result = resp.json()
                
                if result["status"] == "completed":
                    logger.info("🎉 Link transcription completed")
                    gc.collect()
                    return transcript_id
                    
                if result["status"] == "error":
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"Transcription error: {error_msg}")
                    return {'error': "Transcription failed. Please try a different media file."}
                
                time.sleep(min(5 * (2 ** (i // 5)), 60))

            return {'error': "Transcription timed out. Try a shorter file."}

        except Exception as e:
            logger.error(f"Link transcription error: {e}")
            return {'error': f"An error occurred while processing your media: {str(e)[:100]}"}