""" this module contains
    - functions for managing users, including registration, login, logout, and password reset
    - functions for managing user sessions and tokens
    - functions for managing user roles and permissions
    - functions for managing user activity logs and auditing
    - functions for managing user-specific data and settings
"""
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, session,flash, Response
from flask_cors import cross_origin
from datetime import datetime
from bson import ObjectId
from collections import defaultdict
from module.setting import *
from module.auth import *
from module.subtitle import *
from module.config import *
from module.transcribe import *
from module.reset_pass import *
import os
import warnings
import uuid

# Register all blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(setting_bp)
app.register_blueprint(subtitle_bp)
app.register_blueprint(transcribe_bp)
app.register_blueprint(reset_pass_bp)

# Suppress specific warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

# firebase_credentials = {
#     "type": os.getenv("FIREBASE_TYPE"),
#     "project_id": os.getenv("FIREBASE_PROJECT_ID"),
#     "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
#     "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
#     "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
#     "client_id": os.getenv("FIREBASE_CLIENT_ID"),
#     "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
#     "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
#     "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL"),
#     "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
# }



# Set up Firebase connection
# cred = credentials.Certificate(firebase_credentials)
# firebase_admin.initialize_app(cred, {
#     "databaseURL": "https://subtranscribe-default-rtdb.europe-west1.firebasedatabase.app/"
# })

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Get the current time

@app.route('/upload_id', methods=['GET'])
@cross_origin(supports_credentials=True)  # Allow CORS for this route
@limiter.limit("30 per minute")
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

# def Update_progress(transcript_id, status, message, Section, file_name=None, link=None):
#     """Update the progress status in the MongoDB database."""
#     collection = dbase["Main"]  # Specify the collection name
#     # Prepare the post data
#     post = {
#         "_id": transcript_id,
#         "status": status,
#         "message": message,
#         "Section": Section,
#         "file_name": file_name if file_name else "NULL",  
#         "link": link if link else "NULL",
#         "DATE": current_time
#     }

#     # Insert the progress data into the collection
#     collection.insert_one(post)  

@app.route('/about')
@cache.cached(timeout=3600)  # Cache for 1 hour
def about():
    """Render the about page."""
    return render_template('about.html')

# def Create_subtitle_to_db(subtitle_path):
#     """Create subtitle file to MongoDB."""
#     with open(subtitle_path, "rb") as subtitle_file:
#         # Store the file in GridFS and return the file ID
#         subtitle_id = fs.put(subtitle_file, filename=os.path.basename(subtitle_path), content_type='SRT/VTT')
#     return subtitle_id

# def delete_audio_from_gridfs(audio_id):
#     """Delete audio file document from GridFS using audio ID."""
#     fs.delete(audio_id)  # Delete the file from GridFS
#     print(f"Audio file with ID {audio_id} deleted successfully.")

# @app.route('/v1/', methods=['GET', 'POST'])
# def upload_or_link_no_user():
#     """if user is not logged in"""
#     if 'user_id' in session:
#         return redirect(url_for('main_user', user_id=session['user_id']))
#     return redirect(url_for('login'))

@app.route('/v1/<user_id>')
def main_user(user_id):
    if 'user_id' in session:
        upload_id = str(uuid.uuid4())
        session['upload_id'] = upload_id
        return redirect(url_for('transcribe.transcribe_page', user_id=user_id))
    return redirect(url_for('auth.login'))

@app.route('/')
@cache.cached(timeout=1800)  # Cache for 30 minutes
def home():
    """Render the intro page."""
    if 'user_id' in session:
        user = users_collection.find_one({'user_id': session['user_id']})
        if user and 'username' not in session:
            session['username'] = user['username']
    return render_template('intro.html')

@app.route('/privacy')
@cache.cached(timeout=3600)  # Cache for 1 hour
def privacy():
    """Render the privacy policy page."""
    return render_template('privacy.html')

@app.route('/terms')
@cache.cached(timeout=3600)  # Cache for 1 hour
def terms():
    """Render the terms of service page."""
    return render_template('terms.html')
    
@app.route('/cookies')
@cache.cached(timeout=3600)  # Cache for 1 hour
def cookies():
    """Render the cookie policy page."""
    return render_template('cookies.html')

@app.route('/delete_file', methods=['DELETE'])
@limiter.limit("10 per minute")
def delete_file():
    """delete a file from the dashboard"""
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "User not authenticated"}), 401
    
    try:
        data = request.get_json()
        if not data or 'file_id' not in data:
            return jsonify({"success": False, "message": "file_id is required"}), 400
            
        delete_file_id = data.get('file_id')
        
        # Convert file_id to ObjectId
        try:
            object_id = ObjectId(delete_file_id)
        except Exception:
            return jsonify({"success": False, "message": "Invalid file ID format"}), 400
        
        # Find the file and verify ownership
        file_doc = files_collection.find_one({'_id': object_id, 'user_id': user_id})
        
        if not file_doc:
            return jsonify({"success": False, "message": "File not found or access denied"}), 404
        
        # Delete the file
        delete_result = files_collection.delete_one({'_id': object_id, 'user_id': user_id})
        
        # Clear cache for this user's dashboard
        cache.delete(f"dashboard_{user_id}")
        
        if delete_result.deleted_count > 0:
            return jsonify({"success": True, "message": "File deleted successfully"}), 200
        else:
            return jsonify({"success": False, "message": "Error deleting file"}), 500
            
    except Exception as e:
        # Log the error for debugging
        print(f"Error deleting file: {str(e)}")
        return jsonify({"success": False, "message": "Internal server error"}), 500


# @app.route('/health')
# def health_check():
#     """Health check endpoint for monitoring."""
#     firebase_status = check_firebase_connection()
#     return jsonify({"status": "ok", "firebase": firebase_status})

# def check_firebase_connection():
#     """Check if Firebase connection is working."""
            #     try:
#         ref = db.reference('/health')
#         ref.set({"last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
#         return "connected"
            #     except Exception as e:
#         return f"error: {str(e)}"

@app.route("/health")
def health_check():
    return jsonify({"status": "ok", "service": "SubTranscribe", "version": "1.0.0"}), 200

@app.route("/healthserver")
def health_check_legacy():
    return jsonify({"status": "ok"}), 200

@app.route('/sitemap.xml')
def sitemap():
    """Serve the sitemap.xml file."""
    return send_file(os.path.join(os.path.dirname(__file__), 'sitemap.xml'), mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    """Serve the robots.txt file."""
    return send_file(os.path.join(os.path.dirname(__file__), 'robots.txt'), mimetype='text/plain')

# Add a dedicated error route to help with debugging
@app.route('/error/<error_id>')
def show_error(error_id):
    """Debug route to show errors"""
    error = session.get('error')
    user_id = session.get('user_id')
    return render_template('error.html', error=error, user_id=user_id)

# Test route for error page
@app.route('/test_error')
def test_error():
    """Test route to verify error template works"""
    user_id = session.get('user_id', 'test_user')
    return render_template('error.html', 
                          error="This is a test error message", 
                          user_id=user_id)

# Main entry point
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=8000,debug=False,threaded=True)
