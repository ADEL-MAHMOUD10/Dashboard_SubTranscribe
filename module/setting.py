from flask import Blueprint , render_template, redirect, url_for, request, session, flash, Response
from werkzeug.security import check_password_hash, generate_password_hash
from module.config import users_collection ,files_collection, limiter, cache
from bson import ObjectId
from datetime import datetime
import uuid
import json

setting_bp = Blueprint('setting', __name__)

# User Settings Routes
@setting_bp.route('/settings')
@cache.cached(timeout=300)  # Cache for 5 minutes
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
    username = request.form.get('username')
    email = request.form.get('email')
    
    # Validate username
    if not username or len(username) < 3:
        flash('Username must be at least 3 characters long', 'danger')
        return redirect(url_for('setting.settings'))    
    
    # Validate email
    if not email or '@' not in email:
        flash('Please enter a valid email address', 'danger')
        return redirect(url_for('setting.settings'))
    

    # Check if username is already exists by another user
    existing_user = users_collection.find_one({'$or': [{'username': username}, {'email': email}], 'user_id': {'$ne': user_id}})
    if existing_user:
        flash('Username or email is already exists by another user', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Update user profile
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {'username': username, 'email': email}}
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
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # Get user from database
    user = users_collection.find_one({'user_id': user_id})
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Verify current password
    if not check_password_hash(user['password'], current_password):
        flash('Current password is incorrect', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Validate new password
    if new_password != confirm_password:
        flash('New passwords do not match', 'danger')
        return redirect(url_for('setting.settings'))
    
    if len(new_password) < 8:
        flash('Password must be at least 8 characters long', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Update password
    changed_password = generate_password_hash(new_password)
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
@limiter.limit("3 per hour")
def logout_all_devices():
    """Logout from all devices by invalidating the user's session."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    
    # Generate a new session token
    new_session_token = str(uuid.uuid4())
    
    # Update user's session token in database
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {'session_token': new_session_token}}
    )
    
    # Clear current session
    session.clear()
    
    flash('You have been logged out from all devices', 'success')
    return redirect(url_for('auth.login'))

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
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    
    # Get user data
    user = users_collection.find_one({'user_id': user_id})
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('setting.settings'))
    
    # Remove sensitive information
    if '_id' in user:
        del user['_id']
    if 'password' in user:
        del user['password']
    
    # Get user's files
    user_files = list(files_collection.find({'user_id': user_id}))
    for file in user_files:
        if '_id' in file:
            file['_id'] = str(file['_id'])
            del file['_id'] 
    
    # Remove user_id from user object (privacy)
    if 'user_id' in user:
        del user['user_id']
    
    # Combine data
    user_data = {
        'user': user,
        'files': user_files
    }

    username = user['username']
    dfile_name = f"{username}_data.json"

    # Serialize with pretty format
    json_data = json.dumps(user_data, indent=4, ensure_ascii=False,default=custom_serializer)

    # Create response
    response = Response(
        json_data,
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename={dfile_name}'
        }
    )

    return response