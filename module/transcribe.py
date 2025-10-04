from flask import Blueprint , session, redirect, url_for , request, render_template, flash
from module.config import users_collection, files_collection, TOKEN_THREE
from module.send_mail import send_email_transcript
from datetime import datetime, timezone 
import requests
import time
import yt_dlp 
import uuid 
import os 
import gc  # Added for explicit garbage collection
from loguru import logger
transcribe_bp = Blueprint('transcribe', __name__)

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
    """Upload audio file to AssemblyAI with enhanced memory cleanup."""
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2" 
    
    file_content = None  # Initialize to track memory cleanup
    
    try:
        audio_file.seek(0)
        
        # For files smaller than 100MB, read entirely
        # For larger files, use streaming approach
        if file_size and file_size > 100 * 1024 * 1024:  # 100MB threshold
            logger.info(f"Large file detected: {file_size} bytes - using streaming upload")
            # print(f"Large file detected: {file_size} bytes - using streaming upload")
            
            # Stream large files using requests-toolbelt MultipartEncoder
            try:
                from requests_toolbelt.multipart.encoder import MultipartEncoder
                
                multipart_data = MultipartEncoder(
                    fields={
                        'file': (audio_file.filename, audio_file, audio_file.mimetype or 'audio/mpeg')
                    }
                )
                
                headers_copy = headers.copy()
                headers_copy['Content-Type'] = multipart_data.content_type
                
                response = requests.post(
                    f"{base_url}/upload",
                    headers=headers_copy,
                    data=multipart_data,
                    timeout=600  # 10 minutes for large files
                )
                
                # IMMEDIATE CLEANUP: Clean up streaming data after upload
                logger.info("🧹 Cleaning up streaming upload memory...")
                # print("🧹 Cleaning up streaming upload memory...")
                cleanup_upload_memory(audio_file=audio_file)
                
            except ImportError:
                print("requests-toolbelt not available, falling back to standard upload")
                # Fallback to standard upload
                file_content = audio_file.read()
                files = {'file': (audio_file.filename, file_content, audio_file.mimetype)}
                
                response = requests.post(
                    f"{base_url}/upload", 
                    headers=headers,
                    files=files,
                    timeout=600
                )
        else:
            # Standard upload for smaller files
            file_content = audio_file.read()
            files = {'file': (audio_file.filename, file_content, audio_file.mimetype)}
            
            response = requests.post(
                f"{base_url}/upload", 
                headers=headers,
                files=files,
                timeout=300  # 5 minutes timeout
            )
        
        # ENHANCED CLEANUP: After successful upload to AssemblyAI
        if response.status_code in [200, 201]:
            print("✅ AssemblyAI upload successful - cleaning up server memory")
            cleanup_upload_memory(file_content=file_content, audio_file=audio_file)
            file_content = None  # Reset variable
        
        if response.status_code not in [200, 201]:
            error_msg = f"AssemblyAI Upload failed: {response.status_code}"
            if response.text:
                error_msg += f" - {response.text[:200]}"
            print(error_msg)
            
            # Clean up memory even on upload failure
            cleanup_upload_memory(file_content=file_content, audio_file=audio_file)
            
            # Specific error messages for common AssemblyAI issues
            if response.status_code == 401:
                return {'error': "Invalid API token. Please contact support."}
            elif response.status_code == 413:
                return {'error': "File is too large. Please try a smaller file."}
            else:
                return {'error': f"Upload failed: {response.status_code}"}
        
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
                                timeout=transcription_timeout)
        
        # IMPROVED ERROR HANDLING: Specific error messages
        if response.status_code not in [200, 201]:
            error_msg = f"AssemblyAI Transcription request failed: {response.status_code}"
            if response.text:
                error_msg += f" - {response.text[:200]}"
            print(error_msg)
            
            # Specific error messages based on status code
            if response.status_code == 401:
                return {'error': "Invalid API token. Please contact support."}
            elif response.status_code == 429:
                return {'error': "Service is busy. Please try again with a smaller file or wait a few minutes."}
            elif response.status_code == 413:
                return {'error': "File is too large for transcription. AssemblyAI has limits on file sizes."}
            elif response.status_code == 400:
                return {'error': "Invalid audio format. Please ensure your file is a valid audio/video format."}
            else:
                return {'error': f"Transcription request failed: {response.status_code}"}
        
        transcript_id = response.json()["id"]
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
        print(f"File processing error: {error_message}")
        
        # CLEANUP ON ERROR: Ensure memory is freed even if something fails
        cleanup_upload_memory(file_content=file_content, audio_file=audio_file)
        
        return {'error': f"An error occurred while processing your media: {error_message}"}

def transcribe_from_link(upload_id, link):
    """Process a video/audio link for transcription with enhanced memory cleanup."""
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
        # Clean up on error
        cleanup_upload_memory(file_content=file_content if 'file_content' in locals() else None)
        return {'error': "Failed to upload audio"}
    finally:
        # Clean up both possible file paths
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(file_path_mp3):
            os.remove(file_path_mp3)

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
                    # FIXED: Consistent error handling
                    return {'error': "Transcription failed. Please try a different media file or format."}
                    
                else:
                    # Exponential backoff
                    wait_time = min(5 * (2 ** (poll_count // 5)), 60)
                    time.sleep(wait_time)
                    poll_count += 1
            
            except Exception as e:
                time.sleep(5)
                poll_count += 1
            
            finally:
                if response:
                    response.close()  
        
        return {'error': "Transcription is taking longer than expected. Please try again or use a shorter media file."}
        
    except Exception as e:
        error_message = str(e)
        # print(f"Link processing error: {error_message}")
        return {'error': "An error occurred while processing your media. Please check the link and try again."}
