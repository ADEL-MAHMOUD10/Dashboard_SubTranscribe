from flask import Blueprint , request ,redirect ,flash , render_template, url_for
from module.config import users_collection ,otp_collection  ,EMAIL_PASSWORD ,EMAIL_USER, limiter, cache
from module.send_mail import send_email_reset
from werkzeug.security import generate_password_hash
from datetime import datetime ,timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import smtplib
import random

reset_pass_bp = Blueprint('reset_pass', __name__)

@reset_pass_bp.route('/check_user', methods=['GET', 'POST'])
@limiter.limit("3 per minute")
def check_user():
    if request.method == 'POST':
        Email = request.form['email']
        user = users_collection.find_one({'$or': [{'username': Email}, {'Email': Email}]})
        if user:
            otp = random.randint(100000, 999999)
            otp_collection.insert_one({'User': Email, 'OTP': otp,'created_at': datetime.now()})
            send_email_reset(Email, otp)
            flash(f'OTP has been sent to {Email}', 'success')
            return render_template('reset.html', email=Email)
        flash('User not found.', 'danger')
        return redirect(url_for('reset_pass.check_user'))
    return render_template('check_user.html')
        
@reset_pass_bp.route('/reset_password', methods=['POST'])
@limiter.limit("5 per minute")
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
            
            # Clear user cache after password reset
            user = users_collection.find_one({'Email': email})
            if user and 'user_id' in user:
                cache.delete(f"user_{user['user_id']}")
            
            # Remove used OTP
            otp_collection.delete_one({'User': email, 'OTP': int(user_otp)})
            
            if result.modified_count > 0:
                flash('Password updated successfully.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('User not found.', 'danger')
                return render_template('check_user.html')
        else:
            flash('Invalid OTP.', 'danger')
            return redirect(url_for('reset_pass.check_user'))  
            
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return render_template('reset.html', email=email)
    
