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
    with upload_progress_lock:
        upload_progress[upload_id] = {"status": progress_percentage, "message": message}
    
    # Run Firebase update properly
    def run_async_firebase_update():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Create a Firebase reference
            ref = db.reference(f'/UID/{upload_id}')
            # Use the synchronous update method instead
            ref.update({
                "status": progress_percentage,
                "message": message
            })
        finally:
            loop.close()
    
    # Run in a separate thread to avoid blocking
    threading.Thread(target=run_async_firebase_update, daemon=True).start()
    
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
        update_interval = 0.5  # Update progress every 0.5 seconds
        
        while True:
            chunk = audio_file.read(800000)  # Read a 800 KB chunk
            if not chunk:
                break
            yield chunk
            uploaded_size += len(chunk)
            progress_percentage = (uploaded_size / file_size) * 100
            
            # Update progress at regular intervals
            current_time = time.time()
            if current_time - last_update_time >= update_interval:
                prog_message = f"Processing... {progress_percentage:.1f}%"
                update_progress_bar(upload_id, progress_percentage, prog_message)
                last_update_time = current_time
        
        # Final update at 100%
        update_progress_bar(upload_id, 100, "Upload complete, starting transcription...")
    
    # Upload the file to AssemblyAI and get the URL
    try:
        # Upload the audio file to AssemblyAI
        response = requests.post(f"{base_url}/upload", headers=headers, data=upload_chunks(), stream=True)
        if response.status_code!= 200:
            raise RuntimeError("File upload failed.")
        #...
    except Exception as e:
        update_progress_bar(upload_id,0, f"Error uploading audio: {e}")
        return None
    
    upload_url = response.json()["upload_url"]

    # Request transcription from AssemblyAI using the uploaded file URL
    data = {"audio_url": upload_url}
    response = requests.post(f"{base_url}/transcript", json=data, headers=headers)

    transcript_id = response.json()["id"]
    polling_endpoint = f"{base_url}/transcript/{transcript_id}"

    # Poll for the transcription result until completion
    while True:
        transcription_result = requests.get(polling_endpoint, headers=headers).json()
        if transcription_result['status'] == 'completed':
            # Update progress in the database and clean up
            # Update_progress_db(transcript_id, 100, "Transcription completed", "Download page")
            return transcript_id
        elif transcription_result['status'] == 'error':
            raise RuntimeError(f"Transcription failed: {transcription_result['error']}")

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

def transcribe_from_link(upload_id,link):
    """Transcribe audio from a provided link."""
    ydl_opts = {
        'format': 'bestaudio/best',  # Select the best audio format
        'quiet': True,                # Suppress output messages
        'no_warnings': True,          # Suppress warnings
        'extract_audio': True,        # Extract audio from the video
        'skip_download': True,        # Skip downloading the actual file
    }
    upload_id = session.get('upload_id')
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(link)  # Extract information from the provided link
        audio_url = info.get('url', None)  # Get the audio URL

        # Get the size of the audio file using HEAD request
        response = requests.head(audio_url)
        total_size = int(response.headers.get('content-length', 0))  # Get total file size
        # Initialize progress bar
        with tqdm(total=total_size, unit='B', unit_scale=True, desc='Uploading', ncols=100) as bar:
            def upload_chunks():
                # Stream the audio file in chunks

                previous_status = -1  # Track the last updated progress
                with requests.get(audio_url, stream=True) as f:
                    for chunk in f.iter_content(chunk_size=1800000):  # Read 1.8MB chunks
                        if not chunk:
                            break
                        yield chunk
                        bar.update(len(chunk))  # Update progress bar


                        # Update the progress dictionary for frontend
                        prog_status = (bar.n / total_size) * 100

                        # Update every 10% increment
                        if int(prog_status) % 10 == 0 and int(prog_status) != previous_status:
                            prog_message = f"Processing... {prog_status:.2f}%"
                            threading.Thread(target=update_progress_bar, args=(upload_id, prog_status, prog_message)).start()
                            previous_status = int(prog_status)
                            continue
                        if prog_status == 100:
                            prog_message = "Please wait for a few seconds..."
                            threading.Thread(target=update_progress_bar, args=(upload_id, prog_status, prog_message)).start()
                            break

            # Upload the audio file to AssemblyAI in chunks
            base_url = "https://api.assemblyai.com/v2"
            headers = {"authorization": TOKEN_THREE}  # Set authorization header
            response = requests.post(base_url + "/upload", headers=headers, data=upload_chunks(),stream=True)

            # Check upload response
            if response.status_code != 200:
                return f"Error uploading audio: {response.json()}"

    # Send the audio URL to AssemblyAI for transcription
    data = {"audio_url": audio_url}  # Prepare data with audio URL
    response = requests.post(base_url + "/transcript", json=data, headers=headers)  # Make POST request to create a transcript

    if response.status_code != 200:  # Check if the request was successful
        return f"Error creating transcript: {response.json()}"  # Return error message if not successful

    transcript_id = response.json()['id']  # Get the transcript ID from the response

    # Polling to check the status of the transcript
    while True:
        transcript_response = requests.get(f"{base_url}/transcript/{transcript_id}", headers=headers)  # Get the status of the transcript
        if transcript_response.status_code == 200:  # Check if the request was successful
            transcript_data = transcript_response.json()  # Parse the JSON response
            if transcript_data['status'] == 'completed':  # If the transcription is completed
                user_id = session.get('user_id')
                user = users_collection.find_one({'user_id':user_id})
                username = user.get('username')  
                if username:
                    files_collection.insert_one({
                        "username": username,
                        "user_id": user_id,
                        "file_name": f'From Link: {link}',
                        "file_size": total_size,
                        "transcript_id": transcript_id,
                        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                Update_progress_db(transcript_id, status=100, message="Completed", Section="Download page", link=audio_url)  # Update progress in the database
                return redirect(url_for('download_subtitle',user_id=user_id, transcript_id=transcript_id))  # Redirect to download page
            elif transcript_data['status'] == 'error':  # If there was an error during transcription
                Update_progress_db(transcript_id, status=0, message="Invalid Link", Section="Link", link=audio_url)  # Update database with error
                return render_template("error.html")  # Render error page
        else:
            return render_template("error.html")  # Render error page if status request failed

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
