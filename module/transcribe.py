from flask import Blueprint , session, redirect, url_for , request, render_template, flash
from module.config import users_collection, files_collection, TOKEN_THREE
from module.send_mail import send_email_transcript
from datetime import datetime, timezone 
import requests
import time
import yt_dlp 
import uuid 
import os 

transcribe_bp = Blueprint('transcribe', __name__)

# Thread-safe upload lock to prevent concurrent upload conflicts
upload_semaphore = threading.Semaphore(value=1)  # Allow max 1 concurrent uploads

# @limiter.exempt
@transcribe_bp.route('/transcribe/<user_id>')
def transcribe_page(user_id):
    """Render the transcribe page."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    upload_id = str(uuid.uuid4())
    user_id = session.get('user_id')
    session['upload_id'] = upload_id
    return render_template('transcribe.html', upload_id=upload_id, user_id=user_id)

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    EXTENSIONS = {'.mp4', '.wmv', '.mov', '.mkv', '.h.264', '.mp3', '.wav'}
    return '.' in filename and os.path.splitext(filename)[1].lower() in EXTENSIONS

def generate_error_id():
    error_id = str(uuid.uuid4())
    return error_id

# Helper function to clean up memory after upload
def cleanup_upload_memory(file_content=None, audio_file=None):
    """Clean up memory after file upload to AssemblyAI."""
    try:
        # Close file handle if provided
        if audio_file:
            audio_file.close()
        
        # Clear file content from memory
        if file_content:
            del file_content
            file_content = None
        
        # Force garbage collection to free memory immediately
        gc.collect()
        logger.info("✅ Memory cleaned up after upload")
        # print("✅ Memory cleaned up after upload")
        
    except Exception as e:
        logger.error(f"⚠️ Memory cleanup error: {e}")
        # print(f"⚠️ Memory cleanup error: {e}")

# @limiter.exempt
@transcribe_bp.route('/v1', methods=['POST'])
def upload_or_link():
    """Handle file uploads or links for transcription."""
    user_id = session.get('user_id')
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user = users_collection.find_one({'user_id': user_id})
    upload_id = session.get('upload_id')
    
    # Initialize variables with default values
    file_name = 'Unknown'
    file_size = 'Unknown'
    upload_time = datetime.now(timezone.utc)  # Store time in UTC
    username = user.get('username', 'Unknown') if user else 'Unknown'
    
    err_id = generate_error_id()
    if request.method == 'POST':
        link = request.form.get('link')  # Get the link from the form
        if link: 
            result = transcribe_from_link(upload_id, link)  # Transcribe from the provided link
            
            # Check if result is a dictionary containing an error
            if isinstance(result, dict) and 'error' in result:
                error_message = result['error']
                session['error'] = error_message
                # Redirect to error page instead of rendering directly
                return redirect(url_for('show_error', error_id=err_id))
                
            # If it's a string, it's a valid transcript ID
            if isinstance(result, str):
                return redirect(url_for('subtitle.download_subtitle', user_id=user_id, transcript_id=result))
                
            # Fallback error
            # print("Unexpected result from the transcribe_from_link:", result)
            return redirect(url_for('show_error', error_id=err_id, error='Link could not be processed. Please try a different link.'))
        
        file = request.files['file']  # Get the uploaded file
        if file and allowed_file(file.filename):
            try:
                file_name = file.filename
                audio_stream = file
                file_size = request.content_length or 0  # Get file size in bytes
                
                transcript_id = upload_audio_to_assemblyai(upload_id, audio_stream, file_size)  # Upload directly using stream
                
                # Check if transcript_id is a string (success) or dict (error)
                if isinstance(transcript_id, dict) and 'error' in transcript_id:
                    return redirect(url_for('show_error', error_id=err_id, error=transcript_id['error']))
                
                if transcript_id and isinstance(transcript_id, str):
                    try:
                        # Store file information in database
                        files_collection.insert_one({
                            "username": username,
                            "user_id": user_id,
                            "file_name": file_name,
                            "file_size": file_size,
                            "transcript_id": transcript_id,
                            "upload_time": upload_time
                        })
                    except Exception as e:
                        # print(f"Error storing file data: {str(e)}")
                        return redirect(url_for('show_error', error_id=err_id, error=f"Error storing file data: {str(e)}"))
                    
                    return redirect(url_for('subtitle.download_subtitle', user_id=user_id, transcript_id=transcript_id))
                else:
                    return redirect(url_for('show_error', error_id = err_id,error="Processing failed. Please try again."))
            except Exception as e:
                return redirect(url_for('show_error',error_id = err_id, error=f"Upload error: {str(e)[:100]}"))
        else:
            return redirect(url_for('show_error', error_id= err_id , error="Invalid file type or no file provided"))
    else:
        return redirect(url_for('auth.login', user_id=session['user_id']))

def get_model():
    model = request.form['model']
    if model == 'slam-1':
        return 'slam-1'
    elif model == 'universal':
        return 'universal'
    elif model == 'voxtral-mini-2507':
        return 'voxtral-mini-2507'
    elif model == 'whisper-large-v3':
        return 'whisper-large-v3'
    else:
        return 'universal'
    
def upload_audio_to_assemblyai(upload_id, audio_file, file_size):
    """Upload audio file to AssemblyAI in chunks with progress tracking."""
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2" 
    
    # Initialize variables with default values
    file_name = 'Unknown'
    upload_time = 'Unknown'
    username = 'Unknown'
    
    try:
        # Function to upload file in chunks
        def upload_chunks(chunk_size=5242880):  # 5MB chunks
            """Generator function to upload file in smaller chunks."""
            while True:
                chunk = audio_file.read(chunk_size)
                if not chunk:
                    break
                
                yield chunk
        
        # Upload the file to AssemblyAI and get the URL
        try:
            # Upload the audio file to AssemblyAI
            response = requests.post(f"{base_url}/upload", 
                                    headers=headers, 
                                    data=upload_chunks(), 
                                    stream=True,
                                    timeout=120)  # 2 minute timeout

            if response.status_code != 200:
                raise RuntimeError(f"File upload failed with status code: {response.status_code}")
        except Exception as e:
            return None
        
        # Continue with transcription request
        upload_url = response.json()["upload_url"]
        
        # Request transcription from AssemblyAI using the uploaded file URL
        speech_model = get_model()
        data = {
            "audio_url": upload_url,
            "speech_model": speech_model,
        }
        
        # INCREASE TIMEOUT: Better timeout based on file size - longer timeouts for large files
        transcription_timeout = 300 if file_size and file_size > 100 * 1024 * 1024 else 120
        
        response = requests.post(f"{base_url}/transcript", 
                                json=data, 
                                headers=headers,
                                timeout=60)  # Add timeout
        
        if response.status_code != 200:
            return None
        # cache.delete(f"dashboard_{session['user_id']}")
        
        transcript_id = response.json()["id"]
        print(transcript_id)
        print(response.json())
        logger.info(f"Transcript ID: {transcript_id}")
        logger.info(f"Transcription Result: {response.json()}")
        polling_endpoint = f"{base_url}/transcript/{transcript_id}"
        
        # Poll for the transcription result with exponential backoff
        poll_count = 0
        
        while poll_count < 30:  # Limit polling attempts
            response = None
            try:
                response = requests.get(polling_endpoint, headers=headers, timeout=30)
                transcription_result = response.json()
                
                if transcription_result['status'] == 'completed':
                    # FINAL CLEANUP: After successful transcription
                    print("🎉 Transcription completed - final memory cleanup")
                    gc.collect()
                    return transcript_id
                    
                elif transcription_result['status'] == 'error':
                    error_msg = transcription_result.get('error', 'Unknown error')
                    print(f"AssemblyAI Transcription failed: {error_msg}")
                    # FIXED: Return error dict instead of raising exception
                    return {'error': f"Transcription failed: {error_msg}"}
                    
                else:
                    # Exponential backoff with 30s max
                    wait_time = min(5 * (2 ** (poll_count // 5)), 30)
                    time.sleep(wait_time)
                    poll_count += 1
                    
            except Exception as e:
                print(f"Polling error: {str(e)}")
                time.sleep(5)
                poll_count += 1
            
            finally:
                if response:
                    response.close()
        
        # FIXED: Return error dict instead of raising exception
        return {'error': "Transcription timed out. Please try again with a shorter file."}
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"File processing error: {error_message}")
        
        # CLEANUP ON ERROR: Ensure memory is freed even if something fails
        cleanup_upload_memory(file_content=file_content, audio_file=audio_file)
        
        # Force garbage collection for emergency cleanup
        gc.collect()
        
        return {'error': f"An error occurred while processing your media: {error_message}"}
    
    finally:
        # CRITICAL: Always release the semaphore to prevent deadlocks
        upload_semaphore.release()
        logger.info("🔓 Upload semaphore released")

def transcribe_from_link(upload_id, link):
    """Process a video/audio link for transcription with enhanced memory cleanup."""
    # Use semaphore to prevent concurrent upload conflicts
    try:
        if not upload_semaphore.acquire(timeout=300):  # 5 minute timeout to acquire semaphore
            logger.error("❌ Could not acquire upload semaphore for link processing - server too busy")
            return {'error': "Server is currently busy processing other uploads. Please try again in a few minutes."}
    except Exception as e:
        logger.error(f"❌ Semaphore acquisition error for link processing: {e}")
        return {'error': "Unable to process link at this time. Please try again."}
    
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    file_uuid = str(uuid.uuid4())
    filename = f"temp_{file_uuid}"
    
    # Ensure temp directory exists
    temp_dir = os.path.join(os.getcwd(), 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    file_path = os.path.join(temp_dir, filename)
    # The actual file will have .mp3 extension after yt-dlp processing
    file_path_mp3 = f"{file_path}.mp3"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': file_path,
        'quiet': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(link, download=False)
            audio_url = info_dict.get('url', None)
            ydl.download([link])
    except Exception as e:
        return {'error': "Unable to process this media link. Please ensure it's from a supported platform and is publicly accessible."}
    
    # Step 2: Upload to AssemblyAI with enhanced cleanup
    try:
        # Upload in chunks to avoid memory issues with large files
        total_size = os.path.getsize(file_path_mp3)
        file_content = None  # Track file content for cleanup
        
        # Handle large file uploads with streaming
        with open(file_path_mp3, 'rb') as f:
            if total_size > 100 * 1024 * 1024:  # Large file streaming
                try:
                    from requests_toolbelt.multipart.encoder import MultipartEncoder
                    
                    multipart_data = MultipartEncoder(
                        fields={'file': (os.path.basename(file_path_mp3), f, 'audio/mpeg')}
                    )
                    
                    headers_copy = headers.copy()
                    headers_copy['Content-Type'] = multipart_data.content_type
                    
                    upload_res = requests.post(
                        f"{base_url}/upload",
                        headers=headers_copy,
                        data=multipart_data,
                        timeout=600  # 10 minutes for large files
                    )
                except ImportError:
                    # Fallback for small/large files
                    file_content = f.read()
                    upload_res = requests.post(
                        f"{base_url}/upload",
                        headers=headers,
                        files={'file': (os.path.basename(file_path_mp3), file_content, 'audio/mpeg')},
                        timeout=600
                    )
                    # IMMEDIATE CLEANUP: Clean up fallback upload memory
                    cleanup_upload_memory(file_content=file_content)
            else:
                # Standard upload for smaller files  
                file_content = f.read()
                upload_res = requests.post(
                    f"{base_url}/upload",
                    headers=headers,
                    files={'file': (os.path.basename(file_path_mp3), file_content, 'audio/mpeg')},
                    timeout=300
                )
        
        upload_res.raise_for_status()
        upload_url = upload_res.json().get('upload_url')
        
        # CLEANUP: After successful upload to AssemblyAI
        print("✅ Link file uploaded to AssemblyAI - cleaning up server memory")
        cleanup_upload_memory(file_content=file_content)
        
    except Exception as e:
        return flash(f"Failed to upload audio")
    finally:
        # Clean up both possible file paths with error handling
        for temp_file in [file_path, file_path_mp3]:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info(f"✅ Cleaned up temp file: {temp_file}")
            except (OSError, PermissionError) as e:
                logger.warning(f"⚠️ Could not remove temp file {temp_file}: {e}")
                # Force garbage collection to free file handles
                gc.collect()

    try:
        # Request transcription from AssemblyAI using the link
        speech_model = get_model()
        data = {
            "audio_url": upload_url,
            "speech_model": speech_model,
        }
        
        response = requests.post(f"{base_url}/transcript", 
                                json=data, 
                                headers=headers,
                                timeout=300)  # INCREASED: Better timeout for large file transcription
        
        if response.status_code != 200:
            error_message = "Media processing failed. Please ensure your link contains valid audio or video content."
            if response.status_code == 400:
                error_message = "Invalid media format. Please provide a direct link to a supported audio or video file."
            elif response.status_code == 401:
                error_message = "Authorization error. Please try again later."
            elif response.status_code == 429:
                error_message = "Service is currently busy. Please try again in a few minutes."
            elif response.status_code >= 500:
                error_message = "Transcription service is temporarily unavailable. Please try again later."
                
            return {'error': error_message}
        
        transcript_id = response.json()["id"]
        logger.info(f"Transcript ID: {transcript_id}")
        logger.info(f"Transcription Result: {response.json()}")
        polling_endpoint = f"{base_url}/transcript/{transcript_id}"
        
        # Initialize variables with default values
        upload_time = datetime.now(timezone.utc)  # Store time in UTC
        username = session.get('username')
        user_id = session.get('user_id')
        
        # Store link information in database
        files_collection.insert_one({
            "username": username,
            "user_id": user_id,
            "file_name": link,
            "file_size": total_size,
            "transcript_id": transcript_id,
            "upload_time": upload_time,
            "link": link
        })
        
        # Poll for the transcription result
        poll_count = 0
        
        while poll_count < 30:  # Limit polling attempts
            response = None
            try:
                response = requests.get(polling_endpoint, headers=headers, timeout=30)
                transcription_result = response.json()
                
                if transcription_result['status'] == 'completed':
                    # FINAL CLEANUP: After successful transcription
                    print("🎉 Link transcription completed - final cleanup")
                    gc.collect()
                    return transcript_id
                    
                elif transcription_result['status'] == 'error':
                    error_msg = transcription_result.get('error', 'Unknown error')
                    return flash(f"Transcription failed. Please try a different media file or format.")
                    
                else:
                    # Exponential backoff
                    wait_time = min(5 * (2 ** (poll_count // 5)), 60)
                    time.sleep(wait_time)
                    poll_count += 1
            
            except Exception as e:
                time.sleep(5)
                poll_count += 1
        
        # If we get here, we've exceeded poll attempts
        return flash("Transcription is taking longer than expected. Please try again or use a shorter media file.")
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Link processing error: {error_message}")
        
        # Ensure temp files are cleaned up on any error
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(file_path_mp3):
                os.remove(file_path_mp3)
        except OSError:
            pass  # Ignore file cleanup errors
        
        return {'error': "An error occurred while processing your media. Please check the link and try again."}
    
    finally:
        # CRITICAL: Always release the semaphore to prevent deadlocks for link processing
        upload_semaphore.release()
        logger.info("🔓 Upload semaphore released for link processing")
