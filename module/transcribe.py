from flask import Blueprint , session, redirect, url_for , request, render_template
from module.config import users_collection, files_collection, TOKEN_THREE
from datetime import datetime 
import requests
import time
import yt_dlp 
import uuid 
import os 

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
    upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            print("Unexpected result from transcribe_from_link:", result)
            return redirect(url_for('show_error', error_id=err_id, error='Link could not be processed. Please try a different link.'))
        
        file = request.files['file']  # Get the uploaded file
        if file and allowed_file(file.filename):
            try:
                file_name = file.filename
                audio_stream = file
                file_size = request.content_length  # Get file size in bytes
                
                transcript_id = upload_audio_to_assemblyai(upload_id, audio_stream, file_size)  # Upload directly using stream
                
                if transcript_id:
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
                        print(f"Error storing file data: {str(e)}")
                    
                    return redirect(url_for('subtitle.download_subtitle', user_id=user_id, transcript_id=transcript_id))
                else:
                    return redirect(url_for('show_error', error_id = err_id,error="Processing failed. Please try again."))
            except Exception as e:
                return redirect(url_for('show_error',error_id = err_id, error=f"Upload error: {str(e)[:100]}"))
        else:
            return redirect(url_for('show_error', error_id= err_id , error="Invalid file type or no file provided"))
    else:
        return redirect(url_for('auth.login', user_id=session['user_id']))


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
        def upload_chunks():
            """Generator function to upload file in smaller chunks."""
            total_uploaded = 0
            
            # Use small enough chunks for regular progress updates but large enough for efficiency
            # 150KB is a good balance for most connections
            chunk_size = 150000  
            
            while True:
                chunk = audio_file.read(chunk_size)
                if not chunk:
                    break
                
                yield chunk
                total_uploaded += len(chunk)
        
        # Upload the file to AssemblyAI and get the URL
        try:
            # Upload the audio file to AssemblyAI
            response = requests.post(f"{base_url}/upload", 
                                    headers=headers, 
                                    data=upload_chunks(), 
                                    stream=True,
                                    timeout=300)  # 5 minute timeout
            
            if response.status_code != 200:
                raise RuntimeError(f"File upload failed with status code: {response.status_code}")
        except Exception as e:
            print(f"Upload error: {str(e)}")
            return None
        
        # Continue with transcription request
        upload_url = response.json()["upload_url"]
        
        # Request transcription from AssemblyAI using the uploaded file URL
        data = {
            "audio_url": upload_url
        }
        response = requests.post(f"{base_url}/transcript", 
                                json=data, 
                                headers=headers,
                                timeout=60)  # Add timeout
        
        if response.status_code != 200:
            return None
        # cache.delete(f"dashboard_{session['user_id']}")
        
        transcript_id = response.json()["id"]
        polling_endpoint = f"{base_url}/transcript/{transcript_id}"
        
        # Poll for the transcription result with exponential backoff
        poll_count = 0
        
        while poll_count < 30:  # Limit polling attempts
            try:
                transcription_result = requests.get(polling_endpoint, 
                                                  headers=headers, 
                                                  timeout=30).json()
                
                if transcription_result['status'] == 'completed':
                    # Success path
                    return transcript_id
                    
                elif transcription_result['status'] == 'error':
                    error_msg = transcription_result.get('error', 'Unknown error')
                    raise RuntimeError(f"Transcription failed: {error_msg}")
                    
                else:
                    # Exponential backoff with 30s max
                    wait_time = min(5 * (2 ** (poll_count // 5)), 30)
                    time.sleep(wait_time)
                    poll_count += 1
                    
            except Exception as e:
                print(f"Error polling transcription status: {e}")
                time.sleep(5)
                poll_count += 1
        
        # If we get here, we've exceeded poll attempts
        raise RuntimeError("Transcription status check timed out")
        
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return None

# def convert_video_to_audio(video_path):
#     """Convert video file to audio using ffmpeg."""
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     audio_file_path = f'audio_{timestamp}.mp3'
    
#     try:
#         ffmpeg.input(video_path).output(audio_file_path).run(overwrite_output=True)
#         return audio_file_path
#     except Exception as e:
#         print(f"Error converting video to audio: {e}")
#         return None

def transcribe_from_link(upload_id, link):
    """Process a video/audio link for transcription with optimized progress tracking."""
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_audio': True,
        'skip_download': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(link, download=False)
            audio_url = info_dict.get('url', None)
            try:
                response = requests.head(audio_url)
                total_size = int(response.headers.get('content-length', 0))
            except:
                total_size = 0
    except Exception as e:
        print(f"Error extracting audio URL: {str(e)}")
        return {'error': "Unable to process this media link. Please ensure it's from a supported platform and is publicly accessible."}
    
    try:
        # Request transcription from AssemblyAI using the link
        data = {
            "audio_url": audio_url
        }
        
        response = requests.post(f"{base_url}/transcript", 
                                json=data, 
                                headers=headers,
                                timeout=60)  # Add timeout
        
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
        upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        # cache.delete(f"dashboard_{session['user_id']}")yyy
        # Poll for the transcription result
        poll_count = 0
        
        while poll_count < 30:  # Limit polling attempts
            try:
                transcription_result = requests.get(polling_endpoint, 
                                                headers=headers, 
                                                timeout=30).json()
                
                if transcription_result['status'] == 'completed':
                    # Success path
                    return transcript_id
                    
                elif transcription_result['status'] == 'error':
                    error_msg = transcription_result.get('error', 'Unknown error')
                    return {'error': f"Transcription failed: {error_msg}. Please try a different media file or format."}
                    
                else:
                    # Exponential backoff
                    wait_time = min(5 * (2 ** (poll_count // 5)), 30)
                    time.sleep(wait_time)
                    poll_count += 1
                    
            except Exception as e:
                print(f"Error polling transcription status: {e}")
                time.sleep(5)
                poll_count += 1
        
        # If we get here, we've exceeded poll attempts
        return {'error': "Transcription is taking longer than expected. Please try again or use a shorter media file."}
        
    except Exception as e:
        error_message = str(e)
        print(f"Link processing error: {error_message}")
        return {'error': "An error occurred while processing your media. Please check the link and try again."}
