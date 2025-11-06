from flask import Blueprint, request, redirect, flash, render_template, url_for
from module.config import users_collection, otp_collection,limiter, cache
from module.send_mail import send_email_reset
from werkzeug.security import generate_password_hash , check_password_hash
from datetime import datetime, timedelta
from loguru import logger
import random
import hashlib
import re 
import string
import secrets

reset_pass_bp = Blueprint('reset_pass', __name__)

PASS_REGEX = r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$'
OTP_ALLOWED = string.ascii_letters + string.digits
OTP_REGEX = r'^[A-Za-z0-9]{8}$'

def generate_otp(length:int=8) -> str :
    return ''.join(secrets.choice(OTP_ALLOWED) for _ in range(length))

@reset_pass_bp.route('/check_user', methods=['GET', 'POST'])
@limiter.limit("8 per minute")
def check_user():
    if request.method == 'POST':
        Email = request.form['email']
        user = users_collection.find_one({'$or': [{'username': Email}, {'Email': Email}]})
        
        if user:
            otp_plain = generate_otp()
            otp_hashed = hashlib.sha256(otp_plain.encode()).hexdigest()
            otp_collection.delete_many({'User': Email})
            otp_collection.insert_one({
                'User': Email,
                'OTP_hash': otp_hashed,
                'created_at': datetime.now(),
                'attempts': 0
            })
            send_email_reset(Email, otp_plain)
            logger.success(f"OTP is send to {Email}")
        flash(f"If an account exists for {Email}, an OTP has been sent.", "success")
        return render_template('reset.html', email=Email)
    
    return render_template('check_user.html')

@reset_pass_bp.route('/reset_password', methods=['POST'])
@limiter.limit("3 per minute")
def reset_password():
    email = request.form['email']
    user_otp = request.form['OTP'].strip()
    password = request.form['password'].strip()
    confirm_password = request.form['c_password'].strip()

    if not re.fullmatch(OTP_REGEX, user_otp):
        flash('Invalid OTP format.', 'danger')
        return render_template('reset.html', email=email)
    
    
    saved_otp = otp_collection.find_one(
        {'User': email},
        sort=[('created_at', -1)]
        ) 
    if not saved_otp:
        flash('Invalid or expired OTP. Please request a new one.', 'danger')
        return render_template('reset.html', email=email)      
    
    if datetime.now() - saved_otp['created_at'] > timedelta(minutes=2):
        otp_collection.delete_one({'_id': saved_otp['_id']})
        flash('OTP has expired. Please request a new one.', 'warning')
        return redirect(url_for('reset_pass.check_user'))
    
    if saved_otp and saved_otp['attempts'] >= 5:
        otp_collection.delete_one({'User': email})
        flash('Too many invalid attempts. Please request a new OTP.', 'danger')
        return redirect(url_for('reset_pass.check_user')) 
    
    otp_input_hashed = hashlib.sha256(user_otp.encode()).hexdigest()

    if saved_otp['OTP_hash'] != otp_input_hashed:
        otp_collection.update_one({'User': email}, {'$inc': {'attempts': 1}})
        flash('The provided OTP is invalid. Please try again.', 'danger')
        return render_template('reset.html', email=email)
    
    user = users_collection.find_one({'$or': [{'username': email}, {'Email': email}]})
    try:
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('setting.settings'))
        
        current_password = user['password']

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset.html', email=email)
        

        if check_password_hash(current_password, password):
            flash('New password cannot be the same as the current password', 'danger')
            return render_template('reset.html', email=email)
        
        if not re.match(PASS_REGEX, password):
            flash('Password must contain at least one uppercase letter, one lowercase letter, one digit, and one special character.', 'danger')
            return render_template('reset.html', email=email)
        
        hashed_password = generate_password_hash(password, method='scrypt', salt_length=16)
        result = users_collection.update_one(
            {'$or': [{'username': email}, {'Email': email}]},
            {'$set': {'password': hashed_password}}
        )
            
        if user and 'user_id' in user:
            cache.delete(f"user_{user['user_id']}")
            
        otp_collection.delete_one({'User': email, 'OTP_hash': otp_input_hashed})
            
        if result.modified_count > 0:
            flash('Your password has been reset successfully. You can now log in.', 'success')
            logger.success(f"{email} update Password successfully ")
            return redirect(url_for('auth.login'))
        else:
            flash('User not found in database.', 'danger')
            return render_template('check_user.html')
    
    except Exception as e:
        flash(f'An error occurred when reset password, try again later', 'danger')
        logger.error(f"An error occurred when reset password for {email} : {e}")
        return render_template('reset.html', email=email)
