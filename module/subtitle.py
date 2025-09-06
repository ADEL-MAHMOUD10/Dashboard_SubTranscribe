from collections import defaultdict
from flask import Blueprint , session , request  ,render_template ,url_for ,redirect ,flash ,send_file
from module.config import TOKEN_THREE ,files_collection ,users_collection 
from datetime import datetime, timezone
from bson import ObjectId
import requests
import os 

subtitle_bp = Blueprint('subtitle', __name__)

# @limiter.exempt
@subtitle_bp.route('/user_dashboard')
def user_dashboard():
    # Retrieve the user_id from the session
    """check user_id"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # Redirect to the dashboard route
    user_id = session.get('user_id')
    return redirect(url_for('subtitle.dashboard', user_id=user_id))

# @limiter.exempt
# @subtitle_bp.route('/test-cache')
# def test_cache():
#     cache.set('mykey', 'hello cache', timeout=60)
#     value = cache.get('mykey')
#     return f"Cached value is: {value}"

# @limiter.exempt
# def make_cache_key():
#     user_id = session.get('user_id')
#     if user_id:
#         return f"dashboard_{user_id}"
#     return None 

# @limiter.exempt
@subtitle_bp.route('/v1/dashboard/<user_id>')
# @cache.cached(timeout=60, key_prefix=make_cache_key)
def dashboard(user_id):
    # Retrieve the user from the database by user_id
    user = users_collection.find_one({'user_id': user_id})
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('subtitle.user_dashboard'))

    # Retrieve files for the user using the user_id
    files = list(files_collection.find({'user_id': user_id}))
    # files_id = files['transcript_id']
    # Convert the '_id' field to string before passing to template
    for file in files:
        file['_id'] = str(file['_id'])  # Convert ObjectId to string
        
        # Handle upload_time properly
        if 'upload_time' in file and file['upload_time']:
            # If it's not a datetime object, try to convert it
            if not isinstance(file['upload_time'], datetime):
                try:
                    # Try to convert from string if needed
                    file['upload_time'] = datetime.strptime(str(file['upload_time']), '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    # If conversion fails, set to None
                    file['upload_time'] = None
        else:
            file['upload_time'] = None

        
    months, uploads = calculate_monthly_activity(files)

    return render_template('dashboard.html', username=user['username'], files=files, months=months, uploads=uploads)

# @limiter.exempt
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

# @limiter.exempt
@subtitle_bp.route('/share/<transcript_id>', methods=['GET', 'POST'])
def share_subtitle(transcript_id):
    """Share the subtitle with others using the transcript ID."""
    # Initialize variables with default values
    file_name = 'Unknown'
    file_size = 'Unknown'
    upload_time = 'Unknown'
    file_user = 'Unknown' 

    if request.method == 'GET':
        # Get file info for GET request
        get_filename = files_collection.find_one({'transcript_id': transcript_id})
        if get_filename:
            file_name = get_filename.get('file_name') 
            file_user = get_filename.get('username') 
            file_size = f"{(get_filename.get('file_size')/1000000):.2f} MB"  # convert to MB
            upload_time = get_filename.get('upload_time')
            # Try to convert upload_time to datetime if it's a string
            if upload_time and isinstance(upload_time, str):
                try:
                    upload_time = datetime.strptime(upload_time, '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    # Keep it as a string if conversion fails
                    pass
        return render_template('subtitle.html',transcript_id=transcript_id,filename=file_name,file_size=file_size,upload_time=upload_time,username=file_user) 

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
            # subtitle_path = Create_subtitle_to_db(subtitle_file)
            return redirect(url_for('subtitle.serve_file', filename=subtitle_file))  # Redirect to serve the file
        else:
            return render_template("error.html")  # Render error page if request fails
        
# @limiter.exempt
@subtitle_bp.route('/v1/<user_id>/download/<transcript_id>', methods=['GET', 'POST'])
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
            # print(f"Requesting subtitle from: {url}")
            
            response = requests.get(url, headers=headers)  # Request the subtitle file
            
            # Debug response
            # print(f"Response status: {response.status_code}")

            if response.status_code != 200:
                return render_template("error.html", error="Error downloading subtitle file.")

            if response.status_code == 200:
                timesub = datetime.now().strftime("%Y%m%d_%H%M%S")  # Generate a timestamp for the subtitle file
                subtitle_file = f"subtitle_{timesub}.{file_format}"  # Create the subtitle filename
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(os.path.join(os.getcwd(), subtitle_file)), exist_ok=True)
                
                # Write the file with proper encoding
                with open(subtitle_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)  # Write the subtitle text to the file
                
                # # Store in database
                # subtitle_path = Create_subtitle_to_db(subtitle_file)
                
                # Check if file was created successfully
                if os.path.exists(os.path.join(os.getcwd(), subtitle_file)):
                    return redirect(url_for('subtitle.serve_file', filename=subtitle_file))  # Redirect to serve the file
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
                        return render_template("error.html")
                    else:
                        return render_template("error.html")
                        
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
        # Try to convert upload_time to datetime if it's a string
        if upload_time and isinstance(upload_time, str):
            try:
                upload_time = datetime.strptime(upload_time, '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                # Keep it as a string if conversion fails
                pass
        username = get_filename.get('username')
    
    return render_template('subtitle.html', transcript_id=transcript_id, filename=file_name, file_size=file_size, upload_time=upload_time, username=username, user_id=user_id)  # Render the download page with the updated template

# @limiter.exempt
@subtitle_bp.route('/serve/<filename>')
def serve_file(filename):
    """Serve the subtitle file for download."""
    try:
        file_path = os.path.join(os.getcwd(), filename)  # Use a full path for the file
        
        if os.path.exists(file_path):  # Check if the file exists
            response = send_file(file_path, as_attachment=True)  # Send the file as an attachment
            
            # Clean up the file after sending (optional)
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

# @limiter.exempt
@subtitle_bp.route('/redirect/<file_id>')
def redirect_to_transcript(file_id):
    """Redirect to the subtitle download page based on the transcript ID."""
    try:
        file = files_collection.find_one({'_id': ObjectId(file_id)})
        user_id = session.get('user_id')
        if file:
            transcript_id = file.get('transcript_id')
            if transcript_id:
                
                return redirect(url_for('subtitle.download_subtitle',user_id=user_id, transcript_id=transcript_id))
            else:
                print("Transcript ID not found for this file.")
                flash("Transcript ID not found for this file.")
        else:
            flash("File not found.")
    except Exception as e:
        flash(f"An error occurred: {str(e)}")
    
    return redirect(url_for('subtitle.dashboard',user_id=user_id))
