from flask import Blueprint , render_template, redirect, url_for, request, session, flash, Response
from werkzeug.security import check_password_hash, generate_password_hash
from module.config import users_collection ,files_collection, limiter, cache, is_session_valid
from bson import ObjectId
from datetime import datetime
import uuid
import json
import re
from loguru import logger
setting_bp = Blueprint('setting', __name__)


EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$') # powerful 
PASS_REGEX = r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$'

# User Settings Routes
@setting_bp.route('/settings')
def settings():
    """Render the settings page."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    user = users_collection.find_one({'user_id': user_id})
    
    if not user:
        return redirect(url_for('auth.login'))
    
    return render_template('settings.html', user=user)

@setting_bp.route('/update_profile', methods=['POST'])
def update_profile():
    """Update user profile information."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    username = request.form.get('username','').strip()
    email = request.form.get('email','').strip().lower()
    
    # Validate username
    if not username or len(username) < 3:
        flash('Username must be at least 3 characters long', 'warning')
        return redirect(url_for('setting.settings'))    
    
    # Validate email
    if not email or not EMAIL_REGEX.match(email):
        flash('Please enter a valid email address', 'warning')
        return redirect(url_for('setting.settings'))
    

    # Check if username is already exists by another user
    existing_user = users_collection.find_one({
        '$and': [
            {'user_id': {'$ne': user_id}},
            {'$or': [{'username': username}, {'Email': email}]}
        ]
    })
    if existing_user:
        flash('Username or email is already exists by another user', 'warning')
        return redirect(url_for('setting.settings'))
    
    # Update user profile
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {'username': username, 'Email': email}}
    )
    
    # Clear user cache after profile update
    cache.delete(f"user_{user_id}")
    
    flash('Profile updated successfully', 'success')
    return redirect(url_for('setting.settings'))

@setting_bp.route('/update_appearance', methods=['POST'])
@limiter.limit("5 per minute")
def update_appearance():
    """Update user appearance settings."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    theme = request.form.get('theme')
    session['theme'] = theme
    accent_color = request.form.get('accent_color')
    session['accent_color'] = accent_color

    # Update user settings
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {
            'settings.theme': theme,
            'settings.accent_color': accent_color
        }}
    )
    
    flash('Appearance settings updated successfully', 'success')
    return redirect(url_for('setting.settings'))

@setting_bp.route('/update_notifications', methods=['POST'])
@limiter.limit("5 per minute")
def update_notifications():
    """Update user notification preferences."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    email_notifications = 'email_notifications' in request.form
    processing_updates = 'processing_updates' in request.form
    marketing_emails = 'marketing_emails' in request.form
    session['email_notifications'] = email_notifications
    session['processing_updates'] = processing_updates
    session['marketing_emails'] = marketing_emails 
    # Update user settings
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {
            'settings.notifications.email': email_notifications,
            'settings.notifications.processing': processing_updates,
            'settings.notifications.marketing': marketing_emails
        }}
    )
    
    flash('Notification preferences updated successfully', 'success')
    return redirect(url_for('setting.settings'))

@setting_bp.route('/update_password', methods=['POST'])
@limiter.limit("5 per minute")
def update_password():
    """Update user password."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    current_password = request.form.get('current_password','').strip()
    new_password = request.form.get('new_password','').strip()
    confirm_password = request.form.get('confirm_password','').strip()
    
    # Get user from database
    user = users_collection.find_one({'user_id': user_id})
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Verify current password
    if not check_password_hash(user['password'], current_password):
        flash('Current password is incorrect', 'danger')
        return redirect(url_for('setting.settings'))
    
    if check_password_hash(user['password'], new_password):
        flash('New password cannot be the same as the current password', 'danger')
        return redirect(url_for('setting.settings'))

    if not re.match(PASS_REGEX, new_password):
        flash('Password must be at least 8 characters long and include uppercase, lowercase, number, and special character.', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Validate new password
    if new_password != confirm_password:
        flash('New passwords do not match', 'danger')
        return redirect(url_for('setting.settings'))
    
    
    # Update password
    changed_password = generate_password_hash(new_password, method='scrypt', salt_length=16)
    session.clear()
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {'password': changed_password}}
    )

    flash('Password updated successfully', 'success')
    return redirect(url_for('setting.settings'))

@setting_bp.route('/update_advanced_settings', methods=['POST'])
def update_advanced_settings():
    """Update advanced user settings."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    default_format = request.form.get('default_subtitle_format')
    session['default_format'] = default_format
    # Update user settings
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {
            'settings.default_format': default_format,
        }}
    )
    
    flash('Advanced settings updated successfully', 'success')
    return redirect(url_for('setting.settings'))

@setting_bp.route('/logout_all_devices', methods=['POST'])
@limiter.limit("6 per hour")
def logout_all_devices():
    """Logout from all devices by invalidating the user's session."""
    if 'user_id' not in session or not is_session_valid():
        return redirect(url_for('auth.login'))
    try:
        user_id = session.get('user_id')
        username = session.get('username')
        current_token = session.get('session_token')
        if user_id and current_token:
            users_collection.update_one({'user_id': user_id}, {'$set': {'session_token': None, 'session_tokens': []}})
            session.clear()
            flash('Successfully logged out!', 'success')
            return redirect(url_for('home'))
        else:
            flash('No user found', 'danger')
            return redirect(url_for('home'))
    except Exception as e:
        logger.error(f"Error logging out user {username}({user_id}): {e}")
        flash('An error occurred, please try again later', 'danger')
        return redirect(url_for('home'))

@setting_bp.route('/delete_account', methods=['POST'])
@limiter.limit("1 per hour")
def delete_account():
    """Delete user account and all associated data."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    delete_confirmation = request.form.get('delete_confirmation')
    
    if delete_confirmation != 'DELETE':
        flash('Account deletion canceled', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Delete user's files from files collection
    files_collection.delete_many({'user_id': user_id})
    
    # Delete user from users collection
    users_collection.delete_one({'user_id': user_id})
    
    # Clear session
    session.clear()
    
    flash('Your account has been permanently deleted', 'success')
    return redirect(url_for('home'))

def custom_serializer(obj):
    """Convert non-serializable types (like datetime) to string."""
    if isinstance(obj, datetime):
        return obj.isoformat()  # e.g. 2025-03-17T03:59:59
    return str(obj) 

@setting_bp.route('/export_user_data', methods=['POST'])
@limiter.limit("3 per hour")
def export_user_data():
    """Export all user data as JSON."""
    if 'user_id' not in session:
        if is_session_valid():
            return redirect(url_for('main_user', user_id=session['user_id']))
        else:
            session.clear()
            flash('Session expired, please log in again', 'warning')
    
    user_id = session.get('user_id')
    
    # Get user data
    user = users_collection.find_one({'user_id': user_id})
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Remove sensitive information
    for k in ['_id','password','session_tokens','session_token','last_login_req']:
        user.pop(k, None)
    # Get user's files
    user_files = list(files_collection.find({'user_id': user_id}))
    for file in user_files:
        if "_id" in file:
            del file["_id"] 
        if "user_id" in file:
            del file["user_id"]
        if "username" in file:
            del file["username"]
    # Combine data
    user_data = {
        "user": user,
        "files": user_files
    }

    username = user["username"]
    dfile_name = f"{username}_data.json"

    # Serialize with pretty format
    json_data = json.dumps(user_data, indent=4, ensure_ascii=False,default=custom_serializer)

    # Create response
    response = Response(
        json_data,
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename={dfile_name}',
            'Cache-Control': 'no-store'
        }
    )

    return response

