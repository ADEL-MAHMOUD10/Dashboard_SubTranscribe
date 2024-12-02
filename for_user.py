import os
import requests
import time
import warnings
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file
from werkzeug.utils import secure_filename
# import moviepy.editor as mp
from datetime import datetime


app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads" 

progress = {"status": 0, "message": "Initializing"}

@app.route('/about')
def about():
    return render_template('about.html')

def upload_audio_to_assemblyai(audio_path):
    global progress

    headers = {"authorization": "2ba819026c704d648dced28f3f52406f"}
    base_url = "https://api.assemblyai.com/v2"
    
    with open(audio_path, "rb") as f:
        response = requests.post(base_url + "/upload", headers=headers, data=f)

    upload_url = response.json()["upload_url"]

    # Passing the correct webhook URL
    data = {
        "audio_url": upload_url,
        "webhook_url": "https://subtranscribe2.vercel.app"  # Make sure this is correct
    }
    
    response = requests.post(base_url + "/transcript", json=data, headers=headers)
    transcript_id = response.json().get('id')
    
    progress["message"] = "Uploading"
    progress["status"] = 15  # Update the status after starting the upload


    return transcript_id

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    # Check if 'id' is in the payload
    if 'id' in data:
        transcript_id = data['id']
        # Here you can update processing status in the database or log events
        print(f"Transcription {transcript_id} completed.")
        return '', 200
    else:
        print("No transcript ID found in the webhook data.")
        return '', 400  # Return a bad request status if 'id' is not found

@app.route('/progress')
def progress_status():
    return jsonify(progress)

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'.mp4', '.wmv', '.mov', '.mkv', '.h.264', '.mp3', '.wav'}
    return '.' in filename and os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_or_link():
    """Handle file uploads or links for transcription."""
    global progress
    progress = {"status": 0, "message": "Initializing"}  # Reset progress

    if request.method == 'POST':
        link = request.form.get('link')  # Get the link from the form
        progress["status"] = 10  # Update status
        if link:
            progress["status"] = 20  # Update status for link processing
            progress["message"] = "Initializing"
            transcript_id = transcribe_from_link(link)  # Transcribe from the provided link
            return transcribe_from_link(link)  # Redirect to transcribe from the link

        file = request.files.get('file')  # Get the uploaded file
        if file and allowed_file(file.filename):
            time.sleep(1)  # Pause for a moment

            progress["status"] = 10  # Update status
            filename = secure_filename(file.filename)  # Secure the filename
            file_path = f'{filename}' 
            try:
                file.save(file_path)  # Save the uploaded file
                file_extension = os.path.splitext(file_path)[1].lower()  # Get the file extension

                # # Process video files
                # if file_extension in [".mp4", ".wmv", ".mov", ".mkv", ".h.264"]:
                #     # video = mp.VideoFileClip(file_path)  # Load the video file
                #     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # Generate a timestamp
                #     audio_file_path = f'audio_{timestamp}.mp3'  # Use a temporary audio file path
                #     video.audio.write_audiofile(audio_file_path)  # Convert video to audio
                #     video.reader.close()  # Close the video reader
                #     video.audio.reader.close_proc()  # Close the audio reader
                #     progress["status"] = 25  # Update status
                #     progress["message"] = "Converting to Audio file"  # Update message
                #     os.remove(file_path)  # Remove the original video file

                # Process audio files
                if file_extension in [".mp3", ".wav"]:
                    audio_file_path = file_path  # Use the uploaded audio file
                    progress["status"] = 30  # Update status
                    progress["message"] = "Uploading audio file"  # Update message
                else:
                    os.remove(file_path)  # Remove the file if not allowed
                    return render_template("error.html")  # Render error page if file type is not allowed


                progress["status"] = 40  # Update status
                transcript_id = upload_audio_to_assemblyai(audio_file_path)  # Upload audio to AssemblyAI
                return redirect(url_for('download_subtitle', transcript_id=transcript_id))  # Redirect to download subtitle
            except Exception as e:
                progress["status"] = 0  # Reset status on error
                progress["message"] = "Error: " + str(e)  # Update message with error
                return render_template("error.html")  # Render error page

    else:
        return render_template('index.html')  # Render the index page if GET request

def transcribe_from_link(link):
    base_url = "https://api.assemblyai.com/v2"
    headers = {"authorization": "2ba819026c704d648dced28f3f52406f"}

    # Create a payload with the URL
    data = {"audio_url": link}
    response = requests.post(base_url + "/transcript", json=data, headers=headers)
    
    progress["status"] = 40
    progress["message"] = "Processing"
    if response.status_code != 200:
        return f"Error creating transcript: {response.json()}"
    
    transcript_id = response.json()['id']


    # Poll for the transcript status
    while True:
        transcript_response = requests.get(f"{base_url}/transcript/{transcript_id}", headers=headers)
        if transcript_response.status_code == 200:
            transcript_data = transcript_response.json()
            progress["status"] = 80
            if transcript_data['status'] == 'completed':
                progress["status"] = 100
                progress["message"] = "Processing Complete"
                # Now, instead of returning the text, redirect to the download page
                return redirect(url_for('download_subtitle', transcript_id=transcript_id))
            elif transcript_data['status'] == 'error':
                return render_template("error.html")
        else:
            return render_template("error.html")

@app.route('/download/<transcript_id>', methods=['GET', 'POST'])
def download_subtitle(transcript_id):
    if request.method == 'POST':
        file_format = request.form['format']
        headers = {"authorization": "2ba819026c704d648dced28f3f52406f"}
        url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}/{file_format}"

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            progress["message"] = "Downladed"
            progress["status"] = 100
            timesub = datetime.now().strftime("%Y%m%d_%H%M%S")
            subtitle_file = f"subtitle_{timesub}.{file_format}"
            subtitle_path = os.path.join(app.config['UPLOAD_FOLDER'], subtitle_file)
            with open(subtitle_path, 'w') as f:
                f.write(response.text)
            
            return redirect(url_for('serve_file', filename=subtitle_file))
        else:
            return render_template("error.html")
    return render_template('subtitle.html')

@app.route('/serve/<filename>')
def serve_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if os.path.exists(file_path):
        try:
            response = send_file(file_path, as_attachment=True)
            
            try:
                os.remove(file_path)
            except PermissionError:
                time.sleep(1) 
            
            return response
        except Exception:
            return render_template("error.html")
        except FileNotFoundError:
            return render_template("error.html")
        except TypeError:
            return render_template("error.html")
    
if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(host='0.0.0.0',debug=True, port=int(os.environ.get('PORT', 8000)))
