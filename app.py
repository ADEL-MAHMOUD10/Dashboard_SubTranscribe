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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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
REDIS_URI = os.getenv("REDIS_URI")
REDIS_TOKEN = os.getenv("REDIS_TOKEN")
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

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per hour"],
    storage_uri= REDIS_URI
)

CORS(app, 
     supports_credentials=True, 
     origins=['https://subtranscribe.koyeb.app'],
     expose_headers=['Content-Type', 'X-CSRFToken', 'Cache-Control', 'X-Requested-With'],
     allow_headers=['Content-Type', 'X-CSRFToken', 'Authorization', 'Cache-Control', 'X-Requested-With'],
     methods=['GET', 'POST', 'OPTIONS'])
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['DEBUG'] = False  


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

# Set up Firebase connection
cred = credentials.Certificate(firebase_credentials)
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://subtranscribe-default-rtdb.europe-west1.firebasedatabase.app/"
})

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Get the current time

@app.route('/upload_id', methods=['GET'])
@cross_origin(supports_credentials=True)  # Allow CORS for this route
def progress_id():
    """Create a new upload ID."""
    try:
        # Generate a new upload ID if one doesn't exist in the session
        if 'upload_id' not in session or not session['upload_id']:
            session['upload_id'] = str(uuid.uuid4())
            session.modified = True
        
        upload_id = session.get('upload_id')
        
        # Set cache control headers
        response = Response(upload_id)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Content-Type'] = 'text/plain'
        return response
    except Exception as e:
        print(f"Error generating upload ID: {e}")
        return "error"

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
def upload_or_link():
    """Handle file uploads or links for transcription."""
    user_id = session.get('user_id')
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = users_collection.find_one({'user_id': user_id})
    upload_id = session.get('upload_id')
    
    # Initialize variables with default values
    file_name = 'Unknown'
    file_size = 'Unknown'
    upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    username = user.get('username', 'Unknown') if user else 'Unknown'
    
    if request.method == 'POST':
        link = request.form.get('link')  # Get the link from the form
        if link: 
            transcript_id = transcribe_from_link(upload_id, link)  # Transcribe from the provided link
            if isinstance(transcript_id, str):  # If it's a valid transcript ID (not an error template)
                try:
                    # Store link information in database
                    files_collection.insert_one({
                        "username": username,
                        "user_id": user_id,
                        "file_name": "Link: " + link[:50] + ("..." if len(link) > 50 else ""),
                        "file_size": 0,
                        "transcript_id": transcript_id,
                        "upload_time": upload_time,
                        "link": link
                    })
                except Exception as e:
                    print(f"Error storing link data: {str(e)}")
                
                return redirect(url_for('download_subtitle', user_id=user_id, transcript_id=transcript_id))
            return render_template('error.html', error='Link could not be processed')
        
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
                    
                    return redirect(url_for('download_subtitle', user_id=user_id, transcript_id=transcript_id))
                else:
                    return render_template("error.html", error="Processing failed. Please try again.")
            except Exception as e:
                print(f"Upload error: {str(e)}")
                return render_template("error.html", error=f"Upload error: {str(e)[:100]}")
        else:
            return render_template("error.html", error="Invalid file type or no file provided")
    else:
        return redirect(url_for('login', user_id=session['user_id']))


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
        return render_template('error.html', error=f"Could not process link: {str(e)}")
    
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
            return None
        
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
                    return None
                    
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
        return None
        
    except Exception as e:
        error_message = str(e)
        print(f"Link processing error: {error_message}")
        return None

@app.route('/v1/<user_id>')
def main_user(user_id):
    if 'user_id' in session:
        upload_id = str(uuid.uuid4())
        session['upload_id'] = upload_id
        return render_template('index.html',upload_id=upload_id)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """register new user in db"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        Email = request.form['email']
        confirm_password = request.form['c_password']
        user_id = str(uuid.uuid4())

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))

        existing_user = users_collection.find_one({'username': username})
        existing_email = users_collection.find_one({'Email': Email})
        
        if existing_user or existing_email:
            flash('User already exists', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({'Email': Email,'username': username, 'password': hashed_password ,"user_id":user_id})
        session['user_id'] = user_id
        session['username'] = username  # Store username in session
        flash('Successfully registered! Welcome to Subtranscribe', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/')
def home():
    """Render the intro page."""
    if 'user_id' in session:
        user = users_collection.find_one({'user_id': session['user_id']})
        if user and 'username' not in session:
            session['username'] = user['username']
    return render_template('intro.html')

@app.route('/privacy')
def privacy():
    """Render the privacy policy page."""
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    """Render the terms of service page."""
    return render_template('terms.html')
    
@app.route('/cookies')
def cookies():
    """Render the cookie policy page."""
    return render_template('cookies.html')

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("100 per hour")
def login():
    session.permanent = True
    if 'user_id' in session:
        user = users_collection.find_one({'user_id': session['user_id']})
        if user:
            return redirect(url_for('main_user', user_id=session['user_id']))
        else:
            session.clear()
    if request.method == 'POST':
    
        identifier = request.form['email']
        password = request.form['password']

        user = users_collection.find_one({'$or':[{'username':identifier},{'Email':identifier}]})
        if user and check_password_hash(user['password'], password):
            if 'user_id' in session:
                flash('Successfully logged in!', 'success')
            session['user_id'] = user['user_id']  # Store user_id in session
            session['username'] = user['username']  # Store username in session
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
        session.clear()
        flash('Successfully logged out!', 'success')
    return redirect(url_for('login'))


@app.route('/check_user', methods=['GET', 'POST'])
@limiter.limit("50 per hour")
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
@limiter.limit("50 per hour")
def reset_password():
    email = request.form['email']
    user_otp = request.form['OTP']
    password = request.form['password']
    confirm_password = request.form['c_password']
    
    # Check if passwords match
    if password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return render_template('reset.html', email=email)
    
    # Find OTP in database
    try:
        saved_otp = otp_collection.find_one({'User': email, 'OTP': int(user_otp)})
        
        # Check if OTP exists
        if saved_otp:
            # Check if OTP has expired (60 seconds)
            created_at = saved_otp['created_at']
            if datetime.now() - created_at > timedelta(seconds=60):
                otp_collection.delete_one({'User': email, 'OTP': int(user_otp)})
                flash('OTP has expired.', 'danger')
                return render_template('check_user.html')
            
            # Update password
            hashed_password = generate_password_hash(password)
            result = users_collection.update_one({'Email': email}, {'$set': {'password': hashed_password}})
            
            # Remove used OTP
            otp_collection.delete_one({'User': email, 'OTP': int(user_otp)})
            
            if result.modified_count > 0:
                flash('Password updated successfully.', 'success')
                return redirect(url_for('login'))
            else:
                flash('User not found.', 'danger')
                return render_template('check_user.html')
        else:
            flash('Invalid OTP.', 'danger')
            return redirect(url_for('check_user'))
            
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return render_template('reset.html', email=email)
    
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
        if 'upload_time' in file and file['upload_time']:
            try:
                file['upload_time'] = datetime.strptime(file['upload_time'], '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                file['upload_time'] = None
        else:
            file['upload_time'] = None

    months, uploads = calculate_monthly_activity(files)

    return render_template('dashboard.html', username=user['username'], files=files, months=months, uploads=uploads)

def calculate_monthly_activity(files):
    """calculates monthly activity"""
    monthly_activity = defaultdict(int)
    for file in files:
        if 'upload_time' in file and file['upload_time'] is not None:
            month = file['upload_time'].strftime('%B')
            monthly_activity[month] += 1
        else:
            monthly_activity['Unknown'] += 1
    ordered_months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    monthly_data = {month: monthly_activity.get(month, 0) for month in ordered_months}
    
    # Add 'Unknown' category if it exists
    if monthly_activity['Unknown'] > 0:
        monthly_data['Unknown'] = monthly_activity['Unknown']

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

@app.route('/delete_file', methods=['DELETE'])
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

@app.route('/share/<transcript_id>', methods=['GET', 'POST'])
def share_subtitle(transcript_id):
    """Share the subtitle with others using the transcript ID."""
    # Initialize variables with default values
    file_name = 'Unknown'
    file_size = 'Unknown'
    upload_time = 'Unknown'
    username = 'Unknown'

    user_id = session.get('user_id')
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
        
    # Get file info for GET request
    get_filename = files_collection.find_one({'transcript_id': transcript_id})
    if get_filename:
        file_name = get_filename.get('file_name') 
        file_size = f"{(get_filename.get('file_size')/1000000):.2f} MB"  # convert to MB
        upload_time = get_filename.get('upload_time')
        username = get_filename.get('username')
    return render_template('subtitle.html',transcript_id=transcript_id,filename=file_name,file_size=file_size,upload_time=upload_time,username=username,user_id=user_id) 

@app.route('/v1/<user_id>/download/<transcript_id>', methods=['GET', 'POST'])
def download_subtitle(user_id, transcript_id):
    """Handle subtitle download based on the transcript ID."""
    # Initialize variables with default values
    file_name = 'Unknown'
    file_size = 'Unknown'
    upload_time = 'Unknown'
    username = 'Unknown'

    user_id = session.get('user_id')
    
    if request.method == 'POST':
        try:
            file_format = request.form['format']  # Get the requested file format
            headers = {"authorization": TOKEN_THREE}
            url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}/{file_format}"

            # Add debug logging
            print(f"Requesting subtitle from: {url}")
            
            response = requests.get(url, headers=headers)  # Request the subtitle file
            
            # Debug response
            print(f"Response status: {response.status_code}")
            if response.status_code != 200:
                print(f"Error response: {response.text}")

            if response.status_code == 200:
                timesub = datetime.now().strftime("%Y%m%d_%H%M%S")  # Generate a timestamp for the subtitle file
                subtitle_file = f"subtitle_{timesub}.{file_format}"  # Create the subtitle filename
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(os.path.join(os.getcwd(), subtitle_file)), exist_ok=True)
                
                # Write the file with proper encoding
                with open(subtitle_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)  # Write the subtitle text to the file
                
                # Store in database
                subtitle_path = Create_subtitle_to_db(subtitle_file)
                
                # Check if file was created successfully
                if os.path.exists(os.path.join(os.getcwd(), subtitle_file)):
                    return redirect(url_for('serve_file', filename=subtitle_file))  # Redirect to serve the file
                else:
                    print("File was not created successfully")
                    return render_template("error.html", error="File creation failed")
            elif response.status_code == 400:
                # Check if transcript exists or is still processing
                check_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
                check_response = requests.get(check_url, headers=headers)
                
                if check_response.status_code == 200:
                    transcript_data = check_response.json()
                    status = transcript_data.get('status')
                    
                    if status == 'processing':
                        return render_template("error.html", error="Transcript is still processing. Please try again later.")
                    elif status == 'error':
                        return render_template("error.html", error="There was an error processing your transcript.")
                    else:
                        return render_template("error.html", error=f"Transcript status: {status}. Cannot download at this time.")
                        
                return render_template("error.html", error="Bad request. The transcript might not be ready yet.")
            else:
                print(f"Error response: {response.status_code}")
                return render_template("error.html", error=f"Error {response.status_code}: Could not retrieve subtitle file.")
        except Exception as e:
            print(f"Exception during download: {str(e)}")
            return render_template("error.html", error=f"An error occurred: {str(e)}")
    
    # Get file info for GET request
    get_filename = files_collection.find_one({'transcript_id': transcript_id})
    if get_filename:
        file_name = get_filename.get('file_name')
        file_size = f"{(get_filename.get('file_size')/1000000):.2f} MB" # convert to MB
        upload_time = get_filename.get('upload_time')
        username = get_filename.get('username')
    
    return render_template('subtitle.html', transcript_id=transcript_id, filename=file_name, file_size=file_size, upload_time=upload_time, username=username, user_id=user_id)  # Render the download page with the updated template

@app.route('/serve/<filename>')
def serve_file(filename):
    """Serve the subtitle file for download."""
    try:
        file_path = os.path.join(os.getcwd(), filename)  # Use a full path for the file
        
        if os.path.exists(file_path):  # Check if the file exists
            response = send_file(file_path, as_attachment=True)  # Send the file as an attachment
            
            # Clean up the file after sending (optional)
            # Uncomment if you want to delete files after they're served
            # @after_this_request
            # def remove_file(response):
            #     try:
            #         os.remove(file_path)
            #     except Exception as e:
            #         print(f"Error removing file: {str(e)}")
            #     return response
                
            return response  # Return the file response
        else:
            print(f"File not found: {file_path}")
            return render_template("error.html", error="File not found on server.")
    except Exception as e:
        print(f"Error serving file: {str(e)}")
        return render_template("error.html", error=f"Error serving file: {str(e)}")

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    firebase_status = check_firebase_connection()
    return jsonify({"status": "ok", "firebase": firebase_status})

def check_firebase_connection():
    """Check if Firebase connection is working."""
    try:
        ref = db.reference('/health')
        ref.set({"last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        return "connected"
    except Exception as e:
        return f"error: {str(e)}"

@app.route('/sitemap.xml')
def sitemap():
    """Serve the sitemap.xml file."""
    return send_file('sitemap.xml', mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    """Serve the robots.txt file."""
    return send_file('robots.txt', mimetype='text/plain')

# Main entry point
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5000,debug=True,threaded=True)
