from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, session,flash, Response
from firebase_admin import db , credentials
from werkzeug.utils import secure_filename
from flask_cors import CORS, cross_origin
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
from tqdm import tqdm
from bson import ObjectId
from datetime import datetime
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
CORS(app)

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
firebase_admin.initialize_app(cred,{
    "databaseURL":"https://subtranscribe-default-rtdb.europe-west1.firebasedatabase.app/"
    })

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Get the current time

# Create an async function for Firebase updates
async def async_update_firebase(upload_id, progress_percentage, message):
    ref = db.reference(f'/UID/{upload_id}')
    await ref.update_async({
        "status": progress_percentage,
        "message": message
    })

# Use this function in your update_progress_bar
def update_progress_bar(upload_id, progress_percentage, message):
    """Update the progress bar in the Firebase database."""
    # First update local dictionary for immediate API responses
    with upload_progress_lock:
        upload_progress[upload_id] = {"status": progress_percentage, "message": message}
    
    # Start a thread to update Firebase without blocking
    def update_firebase():
        try:
            # Create a Firebase reference
            ref = db.reference(f'/UID/{upload_id}')
            # Use the synchronous update method
            ref.update({
                "status": progress_percentage,
                "message": message
            })
            print(f"Firebase updated: {progress_percentage}% - {message}")
        except Exception as e:
            print(f"Firebase update error: {e}")
    
    # Use daemon thread so it doesn't block process exit
    thread = threading.Thread(target=update_firebase, daemon=True)
    thread.start()
    
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
    if 'upload_id' not in session:
        session['upload_id'] = str(uuid.uuid4())
    
    upload_id = session.get('upload_id')
    return upload_id  # Return as plain text, not JSON


def Update_progress_db(transcript_id, status, message, Section, file_name=None, link=None):
    """Update the progress status in the MongoDB database."""
    collection = dbase["Main"]  # Specify the collection name
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Get the current time

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
    ALLOWED_EXTENSIONS = {'.mp4', '.wmv', '.mov', '.mkv', '.h.264', '.mp3', '.wav'}
    return '.' in filename and os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/v1/', methods=['GET', 'POST'])
def upload_or_link_no_user():
    if 'user_id' in session:
        return redirect(url_for('login', user_id=session['user_id']))
    return redirect(url_for('login'))


@app.route('/v1', methods=['POST'])
def upload_or_link():
    """Handle file uploads or links for transcription."""
    user_id = session.get('user_id')
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = users_collection.find_one({'user_id': user_id})

    upload_id = session.get('upload_id')
    if request.method == 'POST':
        link = request.form.get('link')  # Get the link from the form
        if link:
            transcript_id = transcribe_from_link(upload_id,link)  # Transcribe from the provided link
            return transcript_id  
        
        file = request.files['file']  # Get the uploaded file
        if file and allowed_file(file.filename):
            audio_stream = file
            file_size = request.content_length  # Get file size in bytes
            try:
                transcript_id = upload_audio_to_assemblyai(upload_id,audio_stream, file_size)  # Upload directly using stream
                                
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

def upload_audio_to_assemblyai(upload_id, audio_file, file_size):
    """Upload audio file to AssemblyAI in chunks with progress tracking."""
    headers = {"authorization": TOKEN_THREE}
    base_url = "https://api.assemblyai.com/v2"
    
    # Pre-update to show the upload is starting
    update_progress_bar(upload_id, 0, "Starting upload...")
    
    def upload_chunks():
        """Generator function to upload file in chunks and track progress."""
        uploaded_size = 0
        last_update_time = time.time()
        last_percent = 0
        update_interval = 0.3  # Update every 300ms
        
        while True:
            # Use a balanced chunk size
            chunk = audio_file.read(300000)  # 300KB chunks
            if not chunk:
                break
                
            yield chunk
            uploaded_size += len(chunk)
            progress_percentage = (uploaded_size / file_size) * 100
            
            # Update progress at regular intervals or when percentage changes significantly
            current_time = time.time()
            current_percent = int(progress_percentage)
            
            if (current_time - last_update_time >= update_interval) or (current_percent != last_percent):
                prog_message = f"Processing... {progress_percentage:.1f}%"
                
                # Update the local progress dictionary first
                with upload_progress_lock:
                    upload_progress[upload_id] = {"status": progress_percentage, "message": prog_message}
                
                # Then update Firebase - but use our existing function to maintain compatibility
                update_progress_bar(upload_id, progress_percentage, prog_message)
                
                last_update_time = current_time
                last_percent = current_percent
        
        # Final update at 100%
        update_progress_bar(upload_id, 100, "Upload complete, starting transcription...")
    
    # Upload the file to AssemblyAI and get the URL
    try:
        # Upload the audio file to AssemblyAI
        response = requests.post(f"{base_url}/upload", headers=headers, data=upload_chunks(), stream=True)
        if response.status_code != 200:
            raise RuntimeError("File upload failed.")
    except Exception as e:
        update_progress_bar(upload_id, 0, f"Error uploading audio: {e}")
        return None
    
    upload_url = response.json()["upload_url"]

    # Request transcription from AssemblyAI using the uploaded file URL
    data = {"audio_url": upload_url}
    response = requests.post(f"{base_url}/transcript", json=data, headers=headers)

    transcript_id = response.json()["id"]
    polling_endpoint = f"{base_url}/transcript/{transcript_id}"

    # Poll for the transcription result until completion
    poll_count = 0
    while poll_count < 30:  # Limit polling attempts
        try:
            transcription_result = requests.get(polling_endpoint, headers=headers, timeout=30).json()
            if transcription_result['status'] == 'completed':
                return transcript_id
            elif transcription_result['status'] == 'error':
                raise RuntimeError(f"Transcription failed: {transcription_result['error']}")
            else:
                # Update message to show it's still processing
                update_progress_bar(upload_id, 100, f"Transcription in progress... ({transcription_result['status']})")
                wait_time = min(5, 2 + poll_count // 5)  # Gradually increase wait time
                time.sleep(wait_time)
                poll_count += 1
        except Exception as e:
            print(f"Error polling transcription status: {e}")
            update_progress_bar(upload_id, 100, "Checking transcription status...")
            time.sleep(5)
            poll_count += 1
    
    # If we get here, we've exceeded poll attempts
    raise RuntimeError("Transcription status check timed out")

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
    update_progress_bar(upload_id, 0, "Extracting audio information...")
    
    try:
        # Extract audio URL
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)  # Add download=False for speed
            audio_url = info.get('url', None)
            
            if not audio_url:
                update_progress_bar(upload_id, 0, "Failed to extract audio URL")
                return render_template("error.html")
        
        # Get file size
        response = requests.head(audio_url)
        total_size = int(response.headers.get('content-length', 0))
        
        if total_size == 0:
            update_progress_bar(upload_id, 0, "Could not determine file size")
            return render_template("error.html")
            
        update_progress_bar(upload_id, 5, "Starting upload to transcription service...")
        
        # Upload in chunks with less frequent progress updates
        def upload_chunks():
            uploaded_size = 0
            last_percent = 0
            
            with requests.get(audio_url, stream=True) as f:
                # Use smaller chunk size for more responsive updates
                for chunk in f.iter_content(chunk_size=500000):  # 500KB chunks
                    if not chunk:
                        break
                    
                    yield chunk
                    uploaded_size += len(chunk)
                    
                    # Calculate percentage
                    current_percent = int((uploaded_size / total_size) * 100)
                    
                    # Update only when percentage changes by at least 5%
                    if current_percent >= last_percent + 5:
                        prog_message = f"Uploading... {current_percent}%"
                        update_progress_bar(upload_id, current_percent, prog_message)
                        last_percent = current_percent
            
            # Final update
            update_progress_bar(upload_id, 100, "Upload complete, starting transcription...")
        
        # Upload to AssemblyAI
        base_url = "https://api.assemblyai.com/v2"
        headers = {"authorization": TOKEN_THREE}
        
        # Stream upload
        response = requests.post(f"{base_url}/upload", 
                                headers=headers, 
                                data=upload_chunks(),
                                stream=True,
                                timeout=300)  # Add timeout
        
        if response.status_code != 200:
            update_progress_bar(upload_id, 0, "Upload failed")
            return render_template("error.html")
        
        # Start transcription
        update_progress_bar(upload_id, 100, "Starting transcription...")
        data = {"audio_url": audio_url}
        response = requests.post(f"{base_url}/transcript", 
                                json=data, 
                                headers=headers,
                                timeout=60)  # Add timeout
        
        if response.status_code != 200:
            update_progress_bar(upload_id, 0, "Transcription request failed")
            return render_template("error.html")
        
        transcript_id = response.json()['id']
        
        # Poll for status
        update_progress_bar(upload_id, 100, "Processing transcription...")
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
                    
                    update_progress_bar(upload_id, 100, "Transcription complete!")
                    return redirect(url_for('download_subtitle', user_id=user_id, transcript_id=transcript_id))
                
                elif status == 'error':
                    update_progress_bar(upload_id, 0, f"Transcription error: {transcript_data.get('error', 'Unknown error')}")
                    Update_progress(transcript_id, status=0, message="Transcription failed", 
                                  Section="Link", link=audio_url)
                    return render_template("error.html")
                
                else:
                    # Still processing
                    wait_time = min(5 * (2 ** (poll_count // 5)), 30)  # Exponential backoff with 30s max
                    time.sleep(wait_time)
                    poll_count += 1
            else:
                # API error
                update_progress_bar(upload_id, 0, "API Error checking transcription status")
                return render_template("error.html")
        
        # If we get here, we've polled too many times
        update_progress_bar(upload_id, 0, "Transcription timed out")
        return render_template("error.html")
        
    except Exception as e:
        # Catch any errors and report them
        error_message = str(e)
        print(f"Error in transcribe_from_link: {error_message}")
        update_progress_bar(upload_id, 0, f"Error: {error_message[:50]}...")
        return render_template("error.html")

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
        else:
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
        else:
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
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Redirect to the dashboard route
    user_id = session.get('user_id')
    return redirect(url_for('dashboard', user_id=user_id))

@app.route('/delete_file', methods=['POST'])
def delete_file():
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
    return render_template('subtitle.html')  # Render the subtitle download page

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
        while True:
            with upload_progress_lock:
                progress = upload_progress.get(upload_id, {"status": 0, "message": " "})
            
            # Only send updates when there's a change
            if progress != last_status:
                last_status = progress.copy()
                yield f"data: {json.dumps(progress)}\n\n"
            
            time.sleep(0.5)  # Check for updates every 500ms
    
    return Response(generate(), mimetype='text/event-stream')

# Main entry point
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=8000,debug=False,threaded=True)
