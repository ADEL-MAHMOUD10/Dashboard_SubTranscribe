""" this module contains
    - functions for managing users, including registration, login, logout, and password reset
    - functions for managing user sessions and tokens
    - functions for managing user roles and permissions
    - functions for managing user activity logs and auditing
    - functions for managing user-specific data and settings
"""

from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, session,flash, Response
from firebase_admin import db , credentials
from flask_cors import CORS, cross_origin
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
from tqdm import tqdm
from bson import ObjectId
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import os
import requests
import warnings
import ffmpeg
import gridfs
import yt_dlp
import uuid
import firebase_admin 
import threading
import random
import smtplib
import asyncio
import json
import time

# Suppress specific warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

# set token 
load_dotenv()

TOKEN_ONE = os.getenv("M_api_key")
TOKEN_THREE = os.getenv("A_api_key")
SESSION_USERS = os.getenv('SESSION_ID')
EMAIL_USER = os.getenv("STMP_USER")
EMAIL_PASSWORD = os.getenv("STMP_PASSWORD")

firebase_credentials = {
    "type": os.getenv("FIREBASE_TYPE"),
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
    "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
    "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
}

# Create a Flask application instance
app = Flask(__name__)
CORS(app, supports_credentials=True, origins=['https://subtranscribe.koyeb.app'])
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_PERMANENT'] = True

app.secret_key = SESSION_USERS

# Set up MongoDB connection
cluster = MongoClient(TOKEN_ONE)
dbase = cluster["Datedb"]  # Specify the database name
fs = gridfs.GridFS(dbase)  # Create a GridFS instance for file storage
progress_collection = dbase['progress']  #(Collection)

dbs = cluster["User_DB"]  # Database name
users_collection = dbs["users"]  # Users collection
files_collection = dbs["files"]  # Files collection
otp_collection = dbs["otp"] # OTP collection

# Set up Flask session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

upload_progress = {}

upload_progress_lock = threading.Lock()

# Set up Firebase connection
cred = credentials.Certificate(firebase_credentials)
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://subtranscribe-default-rtdb.europe-west1.firebasedatabase.app/"
})

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Get the current time

# Create an async function for Firebase updates
async def async_update_firebase(upload_id, progress_percentage, message):
    ref = db.reference(f'/UID/{upload_id}')
    await ref.update_async({
        "status": progress_percentage,
        "message": message
    })

def update_progress_bar(upload_id, progress_percentage, message):
    """Update the progress bar in the Firebase database."""
    # First update local dictionary
    with upload_progress_lock:
        upload_progress[upload_id] = {"status": progress_percentage, "message": message}
    
    try:
        # Direct Firebase update - use update(), not set() with merge
        ref = db.reference(f'/UID/{upload_id}')
        ref.update({
            "status": progress_percentage,
            "message": message,
            "timestamp": int(time.time())
        })
        print(f"Firebase update: {progress_percentage}% - {message}")
    except Exception as e:
        print(f"Firebase update error: {e}")

@app.route('/progress/<upload_id>', methods=['GET'])
@cross_origin()  # Allow CORS for this route
def progress_status(upload_id):
    """Return the current progress status as JSON."""
    # Use the provided upload_id parameter if it exists
    if not upload_id or upload_id == 'undefined' or upload_id == 'null':
        upload_id = session.get('upload_id')
    
    # If we still don't have a valid upload_id, return default progress
    if not upload_id:
        return jsonify({"status": 0, "message": " "})
    
    progress = upload_progress.get(upload_id, {"status": 0, "message": " "})
    return jsonify(progress)


@app.route('/upload_id', methods=['GET'])
def progress_id():
    """Create a new upload ID."""
    # Generate a new upload ID if one doesn't exist in the session
    if 'upload_id' not in session or not session['upload_id']:
        session['upload_id'] = str(uuid.uuid4())
    
    upload_id = session.get('upload_id')
    return upload_id  # Return as plain text, not JSON

def Update_progress(transcript_id, status, message, Section, file_name=None, link=None):
    """Update the progress status in the MongoDB database."""
    collection = dbase["Main"]  # Specify the collection name
    # Prepare the post data
    post = {
        "_id": transcript_id,
        "status": status,
        "message": message,
        "Section": Section,
        "file_name": file_name if file_name else "NULL",  
        "link": link if link else "NULL",
        "DATE": current_time
    }

    # Insert the progress data into the collection
    collection.insert_one(post)  

@app.route('/about')
def about():
    """Render the about page."""
    return render_template('about.html')

def Create_subtitle_to_db(subtitle_path):
    """Create subtitle file to MongoDB."""
    with open(subtitle_path, "rb") as subtitle_file:
        # Store the file in GridFS and return the file ID
        subtitle_id = fs.put(subtitle_file, filename=os.path.basename(subtitle_path), content_type='SRT/VTT')
    return subtitle_id

def delete_audio_from_gridfs(audio_id):
    """Delete audio file document from GridFS using audio ID."""
    fs.delete(audio_id)  # Delete the file from GridFS
    print(f"Audio file with ID {audio_id} deleted successfully.")

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    EXTENSIONS = {'.mp4', '.wmv', '.mov', '.mkv', '.h.264', '.mp3', '.wav'}
    return '.' in filename and os.path.splitext(filename)[1].lower() in EXTENSIONS

@app.route('/v1/', methods=['GET', 'POST'])
def upload_or_link_no_user():
    """if user is not logged in"""
    if 'user_id' in session:
        return redirect(url_for('main_user', user_id=session['user_id']))
    return redirect(url_for('login'))


@app.route('/v1', methods=['POST'])
async def upload_or_link():
    """Handle file uploads or links for transcription."""
    user_id = session.get('user_id')
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = users_collection.find_one({'user_id': user_id})

    upload_id = session.get('upload_id')
    if request.method == 'POST':
        link = request.form.get('link')  # Get the link from the form
        if link:
            # Ensure we have an upload ID for progress tracking
            if not upload_id:
                upload_id = str(uuid.uuid4())
                session['upload_id'] = upload_id
            
            transcript_id = await transcribe_from_link(upload_id, link)  # Transcribe from the provided link
            if isinstance(transcript_id, str):  # If it's a valid transcript ID (not an error template)
                return redirect(url_for('download_subtitle', user_id=user_id, transcript_id=transcript_id))
            return transcript_id  # This would be the error template
        
        file = request.files['file']  # Get the uploaded file
        if file and allowed_file(file.filename):
            # Ensure we have an upload ID for progress tracking
            if not upload_id:
                upload_id = str(uuid.uuid4())
                session['upload_id'] = upload_id
                
            audio_stream = file
            file_size = request.content_length  # Get file size in bytes
            try:
                transcript_id = await upload_audio_to_assemblyai(upload_id, audio_stream, file_size)  # Upload directly using stream
                                
                username = user.get('username')  
                if username:
                    files_collection.insert_one({
                        "username": username,
                        "user_id": user_id,
                        "file_name": file.filename,
                        "file_size": file_size,
                        "transcript_id": transcript_id,
                        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })

                response = redirect(url_for('download_subtitle', user_id=user_id, transcript_id=transcript_id))
                return response
            except Exception:
                return render_template("error.html")  # Display error page
        else:
            return render_template("error.html")  # Render error page if file type is not allowed
    else:
        return redirect(url_for('login', user_id=session['user_id']))


# Add this near the top of your upload functions to detect timeouts
timeout_counter = {"count": 0}

def reset_timeout_counter():
    timeout_counter["count"] = 0

def increment_timeout_counter():
    timeout_counter["count"] += 1
    # If we see many timeouts, log it
    if timeout_counter["count"] > 5:
        print(f"WARNING: Multiple timeouts detected ({timeout_counter['count']}). Connection may be unstable.")

def upload_audio_to_assemblyai(upload_id, audio_file, file_size):
    """Upload audio file to AssemblyAI in chunks with progress tracking."""
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    
    # Initial progress update
    update_progress_bar(upload_id, 0, "Initializing audio processing...")
    
    try:
        # Create a persistent progress record
        ref = db.reference(f'/UID/{upload_id}')
        ref.set({
            "status": 0,
            "message": "Preparing audio file...",
            "timestamp": int(time.time()),
            "file_size": file_size,
            "uploaded_bytes": 0,
            "completed": False
        })
        
        # Update progress after initialization
        update_progress_bar(upload_id, 10, "Audio file prepared for processing")
        
        # Create a separate thread for progress updates
        progress_data = {"uploaded_size": 0, "running": True}
        
        def progress_updater():
            """Dedicated thread for progress updates optimized for Koyeb"""
            last_percentage = 10  # Start at 10%
            last_update_time = time.time()
            update_interval = 1.0  # Increase interval to reduce Firebase load
            
            while progress_data["running"]:
                # Check if thread should exit
                if not progress_data["running"]:
                    break
            
                uploaded_size = progress_data["uploaded_size"]
                # Scale progress from 10-90% for upload phase
                progress_percentage = 10 + (uploaded_size / file_size) * 80
                
                # Only update if percentage has changed significantly or time interval passed
                current_percentage = int(progress_percentage)
                current_time = time.time()
                
                if (current_percentage > last_percentage or 
                    (current_time - last_update_time >= update_interval)):
                    
                    # More professional messages based on progress stages
                    if current_percentage < 25:
                        prog_message = f"Transferring audio data: {current_percentage}% complete"
                    elif current_percentage < 50:
                        prog_message = f"Processing audio file: {current_percentage}% complete"
                    elif current_percentage < 75:
                        prog_message = f"Uploading audio content: {current_percentage}% complete"
                    else:
                        prog_message = f"Finalizing upload: {current_percentage}% complete"
                    
                    # Direct update to Firebase
                    try:
                        ref = db.reference(f'/UID/{upload_id}')
                        ref.update({
                            "status": progress_percentage,
                            "message": prog_message,
                            "timestamp": int(current_time),
                            "uploaded_bytes": uploaded_size
                        })
                        
                        with upload_progress_lock:
                            upload_progress[upload_id] = {"status": progress_percentage, "message": prog_message}
                        
                        last_percentage = current_percentage
                        last_update_time = current_time
                        print(f"File progress updated: {progress_percentage:.1f}%")
                    except Exception as e:
                        print(f"Firebase update failed: {e}")
                
                # Sleep to avoid excessive updates, but use a pattern that allows quicker exits
                for _ in range(5):  # Break the sleep into smaller chunks
                    if not progress_data["running"]:
                        break
                    time.sleep(0.1)  # 5 * 0.1 = 0.5 seconds total, but more responsive
        
        # Start the dedicated progress update thread
        progress_thread = threading.Thread(target=progress_updater, daemon=True)
        progress_thread.start()
        
        def upload_chunks():
            """Generator function to upload file in smaller chunks."""
            total_uploaded = 0
            
            while True:
                # Use smaller chunks for more frequent progress updates (120KB)
                chunk = audio_file.read(120000)
                if not chunk:
                    break
                
                yield chunk
                total_uploaded += len(chunk)
                progress_data["uploaded_size"] = total_uploaded
        
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
        finally:
            # Stop the progress updater thread
            progress_data["running"] = False
            # Give the thread a moment to send the final update
            time.sleep(0.5)
        
        # Update progress after upload completes
        update_progress_bar(upload_id, 90, "Upload complete. Initiating transcription process...")
        
        # Continue with transcription request
        upload_url = response.json()["upload_url"]
        
        # Request transcription from AssemblyAI using the uploaded file URL
        data = {"audio_url": upload_url}
        response = requests.post(f"{base_url}/transcript", 
                                json=data, 
                                headers=headers,
                                timeout=60)  # Add timeout
        
        if response.status_code != 200:
            update_progress_bar(upload_id, 0, "Transcription request could not be processed")
            return None
        
        transcript_id = response.json()["id"]
        polling_endpoint = f"{base_url}/transcript/{transcript_id}"
        
        # Poll for the transcription result with exponential backoff
        update_progress_bar(upload_id, 95, "Transcription in progress...")
        poll_count = 0
        
        while poll_count < 30:  # Limit polling attempts
            try:
                transcription_result = requests.get(polling_endpoint, 
                                                  headers=headers, 
                                                  timeout=30).json()
                
                if transcription_result['status'] == 'completed':
                    # Success path
                    update_progress_bar(upload_id, 100, "Transcription successfully completed")
                    return transcript_id
                    
                elif transcription_result['status'] == 'error':
                    error_msg = transcription_result.get('error', 'Unknown error')
                    update_progress_bar(upload_id, 0, f"Transcription error: {error_msg}")
                    raise RuntimeError(f"Transcription failed: {error_msg}")
                    
                else:
                    # Update message to show it's still processing
                    status = transcription_result['status']
                    status_msg = f"Transcription in progress - Current status: {status.replace('_', ' ').title()}"
                    update_progress_bar(upload_id, 98, status_msg)
                    
                    # Exponential backoff with 30s max
                    wait_time = min(5 * (2 ** (poll_count // 5)), 30)
                    time.sleep(wait_time)
                    poll_count += 1
                    
            except Exception as e:
                print(f"Error polling transcription status: {e}")
                update_progress_bar(upload_id, 98, "Verifying transcription status...")
                time.sleep(5)
                poll_count += 1
        
        # If we get here, we've exceeded poll attempts
        update_progress_bar(upload_id, 0, "Transcription process timed out. Please try again.")
        raise RuntimeError("Transcription status check timed out")
        
    except Exception as e:
        error_message = str(e)
        print(f"Upload error: {error_message}")
        
        # Check if we have significant progress before giving up
        if progress_data.get("uploaded_size", 0) / file_size > 0.85:
            # We're close to done, try to mark as high progress
            update_progress_bar(upload_id, 95, f"Upload almost complete, finalizing process...")
        else:
            # Show proper error
            update_progress_bar(upload_id, 0, f"Process error: {error_message[:50]}...")
        
        return None

def convert_video_to_audio(video_path):
    """Convert video file to audio using ffmpeg."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_file_path = f'audio_{timestamp}.mp3'
    
    try:
        ffmpeg.input(video_path).output(audio_file_path).run(overwrite_output=True)
        return audio_file_path
    except Exception as e:
        print(f"Error converting video to audio: {e}")
        return None

def transcribe_from_link(upload_id, link):
    """Transcribe audio from a provided link with optimized performance."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_audio': True,
        'skip_download': True,
    }
    
    # Initial progress update
    update_progress_bar(upload_id, 0, "Initializing link extraction...")
    
    try:
        # Extract audio URL
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)  # Add download=False for speed
            audio_url = info.get('url', None)
            
            if not audio_url:
                update_progress_bar(upload_id, 0, "Failed to extract audio URL")
                return render_template("error.html")
        
        # Update progress after extracting URL
        update_progress_bar(upload_id, 10, "Audio source successfully identified")
        
        # Get file size
        response = requests.head(audio_url)
        total_size = int(response.headers.get('content-length', 0))
        
        if total_size == 0:
            update_progress_bar(upload_id, 0, "Could not determine file size")
            return render_template("error.html")
            
        update_progress_bar(upload_id, 15, "Initiating transfer to transcription service...")
        
        # Create a separate thread for progress updates
        progress_data = {"uploaded_size": 0, "running": True}
        
        def progress_updater():
            """Dedicated thread for progress updates optimized for Koyeb"""
            last_percentage = 15  # Start at 15%
            last_update_time = time.time()
            update_interval = 1.0  # Increase interval to reduce Firebase load
            
            while progress_data["running"]:
                # Check if thread should exit
                if not progress_data["running"]:
                    break
            
                uploaded_size = progress_data["uploaded_size"]
                # Scale progress from 15-90% for upload phase
                progress_percentage = 15 + (uploaded_size / total_size) * 75
                
                # Only update if percentage has changed significantly or time interval passed
                current_percentage = int(progress_percentage)
                current_time = time.time()
                
                if (current_percentage > last_percentage or 
                    (current_time - last_update_time >= update_interval)):
                    
                    prog_message = f"Retrieving audio data: {current_percentage}% complete"
                    
                    # Direct update to Firebase with merge=true
                    try:
                        ref = db.reference(f'/UID/{upload_id}')
                        ref.update({
                            "status": progress_percentage,
                            "message": prog_message,
                            "timestamp": current_time
                        })
                        
                        with upload_progress_lock:
                            upload_progress[upload_id] = {"status": progress_percentage, "message": prog_message}
                        
                        last_percentage = current_percentage
                        last_update_time = current_time
                        print(f"Link progress updated: {progress_percentage:.1f}%")
                    except Exception as e:
                        print(f"Firebase update failed: {e}")
                
                # Sleep to avoid excessive updates, but use a pattern that allows quicker exits
                for _ in range(5):  # Break the sleep into smaller chunks
                    if not progress_data["running"]:
                        break
                    time.sleep(0.1)  # 5 * 0.1 = 0.5 seconds total, but more responsive
        
        # Start the dedicated progress update thread
        progress_thread = threading.Thread(target=progress_updater, daemon=True)
        progress_thread.start()
        
        # Upload in chunks with progress tracking
        def upload_chunks():
            with requests.get(audio_url, stream=True) as f:
                # Use smaller chunk size for more responsive updates
                for chunk in f.iter_content(chunk_size=200000):  # 200KB chunks
                    if not chunk:
                        break
                    
                    yield chunk
                    progress_data["uploaded_size"] += len(chunk)
        
        # Upload to AssemblyAI
        base_url = "https://api.assemblyai.com/v2"
        headers = {"authorization": TOKEN_THREE}
        
        try:
            # Stream upload
            response = requests.post(f"{base_url}/upload", 
                                    headers=headers, 
                                    data=upload_chunks(),
                                    stream=True,
                                    timeout=300)  # Add timeout
            
            # Stop the progress updater thread
            progress_data["running"] = False
            time.sleep(0.5)  # Give time for thread to finish
            
            if response.status_code != 200:
                update_progress_bar(upload_id, 0, "Audio retrieval unsuccessful")
                return render_template("error.html")
            
            # Start transcription
            update_progress_bar(upload_id, 90, "Upload complete. Initiating transcription process...")
            data = {"audio_url": response.json()["upload_url"]}
            response = requests.post(f"{base_url}/transcript", 
                                    json=data, 
                                    headers=headers,
                                    timeout=60)  # Add timeout
            
            if response.status_code != 200:
                update_progress_bar(upload_id, 0, "Transcription request could not be processed")
                return render_template("error.html")
            
            transcript_id = response.json()['id']
            
            # Poll for status
            update_progress_bar(upload_id, 95, "Transcription analysis in progress...")
            polling_url = f"{base_url}/transcript/{transcript_id}"
            
            # Create a polling function with exponential backoff
            poll_count = 0
            while poll_count < 30:  # Limit to 30 polls to prevent infinite loops
                transcript_response = requests.get(polling_url, headers=headers, timeout=30)
                
                if transcript_response.status_code == 200:
                    transcript_data = transcript_response.json()
                    status = transcript_data.get('status')
                    
                    if status == 'completed':
                        # Success path
                        user_id = session.get('user_id')
                        user = users_collection.find_one({'user_id': user_id})
                        username = user.get('username') if user else None
                        
                        if username:
                            files_collection.insert_one({
                                "username": username,
                                "user_id": user_id,
                                "file_name": f'From Link: {link}',
                                "file_size": total_size,
                                "transcript_id": transcript_id,
                                "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                        
                        Update_progress(transcript_id, status=100, message="Completed", 
                                      Section="Download page", link=audio_url)
                        
                        update_progress_bar(upload_id, 100, "Transcription successfully completed")
                        return transcript_id
                    
                    elif status == 'error':
                        update_progress_bar(upload_id, 0, f"Transcription error: {transcript_data.get('error', 'Unknown error')}")
                        Update_progress(transcript_id, status=0, message="Transcription failed", 
                                      Section="Link", link=audio_url)
                        return render_template("error.html")
                    
                    else:
                        # Still processing - update with percentage if available
                        progress_msg = f"Transcription in progress..."
                        update_progress_bar(upload_id, 99, progress_msg)
                        
                        wait_time = min(5 * (2 ** (poll_count // 5)), 30)  # Exponential backoff with 30s max
                        time.sleep(wait_time)
                        poll_count += 1
                else:
                    # API error
                    update_progress_bar(upload_id, 0, "API communication error during transcription process")
                    return render_template("error.html")
            
            # If we get here, we've polled too many times
            update_progress_bar(upload_id, 0, "Transcription process timed out. Please try again.")
            return render_template("error.html")
            
        except requests.exceptions.Timeout:
            update_progress_bar(upload_id, 0, "Request timed out")
            return render_template("error.html")
        finally:
            # Ensure the progress thread is stopped
            progress_data["running"] = False
            
    except Exception as e:
        # Catch any errors and report them
        error_message = str(e)
        print(f"Error in transcribe_from_link: {error_message}")
        if upload_progress.get(upload_id, {}).get("status", 0) >= 90:
            # If we're far along, keep high progress but show error
            update_progress_bar(upload_id, 95, f"Error: {error_message[:50]}...")
        else:
            # Otherwise start over
            update_progress_bar(upload_id, 0, f"Error: {error_message[:50]}...")
        return render_template("error.html")

# def upload_audio_to_gridfs(file_path):
#     """Upload audio file to MongoDB using GridFS."""
#     with open(file_path, "rb") as f:
#         # Store the file in GridFS and return the file ID
#         audio_id = fs.put(f, filename=os.path.basename(file_path), content_type='audio/video')

#     return audio_id

@app.route('/v1/<user_id>')
def main_user(user_id):
    if 'user_id' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """register new user in db"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        Email = request.form['email']
        confirm_password = request.form['confirm_password']
        user_id = str(uuid.uuid4())

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))

        existing_user = users_collection.find_one({'username': username})
        existing_email = users_collection.find_one({'Email': Email})
        
        if existing_user and existing_email:
            flash('Username and Email already exists', 'danger')
            return redirect(url_for('login'))
        
        if existing_user:
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        if existing_email:
            flash('Email already exists', 'danger')
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({'Email': Email,'username': username, 'password': hashed_password ,"user_id":user_id})
        session['user_id'] = user_id
        flash('Successfully log in! You can now download all your subtitles files', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/', methods=['GET', 'POST'])
def login():
    session.permanent = True
    if 'user_id' in session:
        upload_id = str(uuid.uuid4())
        session['upload_id'] = upload_id
        return redirect(url_for('main_user', user_id=session['user_id']))
    if request.method == 'POST':
    
        identifier = request.form['email_username']
        password = request.form['password']

        user = users_collection.find_one({'$or':[{'username':identifier},{'Email':identifier}]})
        if user and check_password_hash(user['password'], password):
            if 'user_id' in session:
                flash('Successfully logged in!', 'success')
            session['user_id'] = user['user_id']  # Store user_id in session
            return redirect(url_for('main_user', user_id=user['user_id']))
        flash('Incorrect username or password', 'danger')
        return redirect(url_for('login'))
        
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    if request.method == 'GET':
        session.pop('user_id',None)
        session.pop('username',None)
        session.pop('password',None)
        flash('Successfully logged out!', 'success')
    return redirect(url_for('login'))


@app.route('/check_user', methods=['GET', 'POST'])
def check_user():
    if request.method == 'POST':
        Email = request.form['email']
        user = users_collection.find_one({'$or': [{'username': Email}, {'Email': Email}]})
        if user:
            otp = random.randint(100000, 999999)
            otp_collection.insert_one({'User': Email, 'OTP': otp,'created_at': datetime.now()})
            
            send_email(Email, otp)
            
            flash(f'OTP has been sent to {Email}', 'success')
            return render_template('reset.html', email=Email)
        flash('User not found.', 'danger')
        return redirect(url_for('check_user'))
    return render_template('check_user.html')
        
@app.route('/reset_password', methods=['POST'])
def reset_password():
    email = request.form['email']
    user_otp = request.form['OTP']
    new_password = request.form['c_password']
    
    saved_otp = otp_collection.find_one({'User': email, 'OTP': int(user_otp)})
    if saved_otp:
        created_at = saved_otp['created_at']
        if datetime.now() - created_at > timedelta(seconds=60):
            otp_collection.delete_one({'User': email, 'OTP': int(user_otp)})
            flash('OTP has expired.', 'danger')
            return render_template('check_user.html')
        hashed_password = generate_password_hash(new_password)
        users_collection.update_one({'Email': email}, {'$set': {'password': hashed_password}})
        flash('Password updated successfully.', 'success')
        return redirect(url_for('login'))
    else:
        flash('Invalid OTP.', 'danger')
        return redirect(url_for('check_user'))
    
def send_email(to_address, otp):
    smtp_server = 'smtp.gmail.com'
    port = 587
    from_address = EMAIL_USER
    password = EMAIL_PASSWORD

    message = MIMEMultipart()
    message['From'] = from_address
    message['To'] = to_address
    message['Subject'] = 'Reset Your Password'
    
    html_content = f"""
                <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                            <div style="text-align: center; margin-bottom: 20px;">
                                <img src="cid:logo_image" alt="Logo" style="max-width: 80px;">
                            </div>
                            <h2 style="text-align: center; color: #555;">Reset Your Password</h2>
                            <p>Hi {to_address},</p>
                            <p>You requested to reset your password. Please use the code below to complete the process:</p>
                            <div style="text-align: center; font-size: 18px; font-weight: bold; color: #000; background: #f7f7f7; padding: 10px; border-radius: 8px;">
                                <span style="color: #FF6F61;">{otp}</span>
                            </div>
                            <p>If you did not request this action, please ignore this email. Your account is safe.</p>
                            <p>Best Regards,<br>Team subtranscribe</p>
                            <div style="margin-top: 20px; text-align: center; font-size: 12px; color: #999;">
                                <p>© 2024 subtranscribe. All rights reserved.</p>
                            </div>
                        </div>
                    </body>
                </html>
            """
    message.attach(MIMEText(html_content, 'html'))
    image_path = "subtitle.png"

    try:
        with open(image_path, 'rb') as img:
            mime_image = MIMEImage(img.read())
            mime_image.add_header('Content-ID', '<logo_image>') 
            mime_image.add_header('Content-Disposition', 'inline', filename=image_path)
            message.attach(mime_image)
    except FileNotFoundError:
        print("Image file not found. Email will be sent without the image.")
            
    try:
        smtpObj = smtplib.SMTP(smtp_server, port)
        smtpObj.ehlo()
        smtpObj.starttls()
        smtpObj.login(from_address, password)
        smtpObj.sendmail(from_address, to_address, message.as_string())
        print("Email sent successfully.")
    except Exception as e:
                print(f"Failed to send email: {e}")
    finally:
        smtpObj.quit()

@app.route('/v1/dashboard/<user_id>')
def dashboard(user_id):
    # Retrieve the user from the database by user_id
    user = users_collection.find_one({'user_id': user_id})
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('user_dashboard'))

    # Retrieve files for the user using the user_id
    files = list(files_collection.find({'user_id': user_id}))
    # Convert the '_id' field to string before passing to template
    for file in files:
        file['_id'] = str(file['_id'])  # Convert ObjectId to string
        
        # convert upload_time to datetime
        file['upload_time'] = datetime.strptime(file['upload_time'], '%Y-%m-%d %H:%M:%S')

    months, uploads = calculate_monthly_activity(files)

    return render_template('dashboard.html', username=user['username'], files=files, months=months, uploads=uploads)

def calculate_monthly_activity(files):
    """calculates monthly activity"""
    monthly_activity = defaultdict(int)
    for file in files:        
        month = file['upload_time'].strftime('%B')
        monthly_activity[month] += 1
    ordered_months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    monthly_data = {month: monthly_activity.get(month, 0) for month in ordered_months}

    return list(monthly_data.keys()), list(monthly_data.values())

@app.route('/user_dashboard')
def user_dashboard():
    # Retrieve the user_id from the session
    """check user_id"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Redirect to the dashboard route
    user_id = session.get('user_id')
    return redirect(url_for('dashboard', user_id=user_id))

@app.route('/delete_file', methods=['POST'])
def delete_file():
    """delete a file from the dashboard"""
    user_id = session.get('user_id')
    
    user_file = files_collection.find_one({'user_id': user_id})
    if user_file:
        data = request.get_json()
        delete_file_id = data.get('file_id')
        try:
            object_id = ObjectId(delete_file_id)
            files = list(files_collection.find({'_id': object_id}))

            for file in files:
                file['transcript_id'] = str(file['transcript_id'])
            if file:
                file_id = file['transcript_id']
                delete_result = files_collection.delete_one({'transcript_id': file_id})
                
                if delete_result.deleted_count > 0:
                    return jsonify({"success": True, "message": "File deleted successfully"})
                else:
                    return jsonify({"success": False, "message": "Error deleting file"})
            else:
                return jsonify({"success": False, "message": "File not found"})
        except Exception as e:
            return jsonify({"success": False, "message": "Invalid file ID format"})
    else:
        return jsonify({"success": False, "message": "User not found"})

@app.route('/redirect/<file_id>')
def redirect_to_transcript(file_id):
    """Redirect to the subtitle download page based on the transcript ID."""
    try:
        file = files_collection.find_one({'_id': ObjectId(file_id)})
        user_id = session.get('user_id')
        if file:
            transcript_id = file.get('transcript_id')
            if transcript_id:
                
                return redirect(url_for('download_subtitle',user_id=user_id, transcript_id=transcript_id))
            else:
                flash("Transcript ID not found for this file.")
        else:
            flash("File not found.")
    except Exception as e:
        flash(f"An error occurred: {str(e)}")
    
    return redirect(url_for('dashboard'))


@app.route('/v1/<user_id>/download/<transcript_id>', methods=['GET', 'POST'])
def download_subtitle(user_id,transcript_id):
    """Handle subtitle download based on the transcript ID."""

    if request.method == 'POST':
        file_format = request.form['format']  # Get the requested file format
        headers = {"authorization": TOKEN_THREE}
        url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}/{file_format}"

        response = requests.get(url, headers=headers)  # Request the subtitle file
        if response.status_code == 200:
            timesub = datetime.now().strftime("%Y%m%d_%H%M%S")  # Generate a timestamp for the subtitle file
            subtitle_file = f"subtitle_{timesub}.{file_format}"  # Create the subtitle filename
            with open(subtitle_file, 'w') as f:
                f.write(response.text)  # Write the subtitle text to the file
            
            subtitle_path = Create_subtitle_to_db(subtitle_file)
            return redirect(url_for('serve_file', filename=subtitle_file))  # Redirect to serve the file
        else:
            return render_template("error.html")  # Render error page if request fails
    return render_template('subtitle.html')  # Render the download page with the updated template

@app.route('/serve/<filename>')
def serve_file(filename):
    """Serve the subtitle file for download."""
    file_path = os.path.join(os.getcwd(), filename)  # Use a full path for the file

    if os.path.exists(file_path):  # Check if the file exists
        response = send_file(file_path, as_attachment=True)  # Send the file as an attachment

    return response  # Return the file response

@app.route('/progress_stream/<upload_id>')
def progress_stream(upload_id):
    """Create a server-sent events stream for progress updates."""
    def generate():
        last_status = None
        iteration_count = 0
        max_iterations = 600  # Limit the connection to 5 minutes (600 * 0.5s)
        recovery_attempts = 0
        
        # Initial message
        initial_data = {
            "status": 0, 
            "message": "Preparing...",
            "keep_visible": True,  # Special flag for our client
            "nonce": int(time.time() * 1000)
        }
        yield f"data: {json.dumps(initial_data)}\n\n"
        
        while iteration_count < max_iterations:
            try:
                # First try the in-memory cache for faster responses
                with upload_progress_lock:
                    progress = upload_progress.get(upload_id, None)
                
                # If not in memory, try Firebase
                if progress is None:
                    try:
                        ref = db.reference(f'/UID/{upload_id}')
                        firebase_data = ref.get()
                        if firebase_data:
                            progress = {
                                "status": firebase_data.get("status", 0),
                                "message": firebase_data.get("message", "Processing...")
                            }
                            
                            # Update local cache with Firebase data
                            with upload_progress_lock:
                                upload_progress[upload_id] = progress
                    except Exception as e:
                        print(f"Firebase read error in SSE: {e}")
                        # If both in-memory and Firebase fail, use last known status
                        if last_status:
                            progress = last_status
                        else:
                            progress = {"status": 0, "message": "Connecting..."}
                
                # Default if still None
                if progress is None:
                    progress = {"status": 0, "message": "Processing..."}
                
                # Only send updates when there's a change or periodically for keepalive
                if progress != last_status or iteration_count % 20 == 0:
                    last_status = progress.copy()
                    
                    # Add a nonce to prevent browser caching
                    progress['nonce'] = int(time.time() * 1000)
                    yield f"data: {json.dumps(progress)}\n\n"
                    
                    # If completed, exit early
                    if progress.get("status", 0) >= 100 and "complete" in progress.get("message", "").lower():
                        break
                
            except Exception as e:
                print(f"Error in SSE stream: {e}")
                recovery_attempts += 1
                if recovery_attempts > 3:
                    # After 3 failures, send an update to let client know there's an issue
                    yield f"data: {json.dumps({'status': -1, 'message': 'Connection error, retrying...', 'nonce': int(time.time() * 1000)})}\n\n"
            
            time.sleep(0.5)  # Check for updates every 500ms
            iteration_count += 1
        
        # Final message indicating stream completion
        yield f"data: {json.dumps({'status': last_status.get('status', 0), 'message': 'Stream ended', 'nonce': int(time.time() * 1000)})}\n\n"
    
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache, no-transform'
    response.headers['Connection'] = 'keep-alive'
    response.headers['X-Accel-Buffering'] = 'no'  # Important for Nginx
    return response

@app.route('/health')
def health_check():
    """Simple health check endpoint for Koyeb."""
    return jsonify({"status": "healthy", "timestamp": int(time.time())})

def check_firebase_connection():
    """Check if Firebase connection is working properly."""
    try:
        ref = db.reference('/.info/connected')
        connected = ref.get()
        return connected
    except Exception as e:
        print(f"Firebase connection check failed: {e}")
        return False

# Main entry point
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=8000,debug=False,threaded=True)
    
