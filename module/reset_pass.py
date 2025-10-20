from flask import Blueprint, request, redirect, flash, render_template, url_for
from module.config import users_collection, otp_collection,limiter, cache
from module.send_mail import send_email_reset
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from loguru import logger
import random
import hashlib

reset_pass_bp = Blueprint('reset_pass', __name__)

@reset_pass_bp.route('/check_user', methods=['GET', 'POST'])
@limiter.limit("8 per minute")
def check_user():
    if request.method == 'POST':
        Email = request.form['email']
        user = users_collection.find_one({'$or': [{'username': Email}, {'Email': Email}]})
        
        if user:
            otp_plain = str(random.randint(100000, 999999))
            otp_hashed = hashlib.sha256(otp_plain.encode()).hexdigest()
            otp_collection.insert_one({
                'User': Email,
                'OTP_hash': otp_hashed,
                'created_at': datetime.now()
            })
            send_email_reset(Email, otp_plain)
            logger.success(f"OTP is send to {Email}")
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
    
    if password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return render_template('reset.html', email=email)
    
    if not user_otp.isdigit():
        flash('OTP must be numeric.', 'danger')
        return render_template('reset.html', email=email)
    
    otp_input_hashed = hashlib.sha256(user_otp.encode()).hexdigest()
    
    try:
        saved_otp = otp_collection.find_one({'User': email, 'OTP_hash': otp_input_hashed})
        if saved_otp:
            if datetime.now() - saved_otp['created_at'] > timedelta(minutes=2):
                otp_collection.delete_one({'User': email, 'OTP_hash': otp_input_hashed})
                flash('OTP has expired. Please request a new one.', 'warning')
                return render_template('check_user.html')
            
            hashed_password = generate_password_hash(password)
            result = users_collection.update_one(
                {'$or': [{'username': email}, {'Email': email}]},
                {'$set': {'password': hashed_password}}
            )
            
            user = users_collection.find_one({'$or': [{'username': email}, {'Email': email}]})
            if user and 'user_id' in user:
                cache.delete(f"user_{user['user_id']}")
            
            otp_collection.delete_one({'User': email, 'OTP_hash': otp_input_hashed})
            
            if result.modified_count > 0:
                flash('Password updated successfully.', 'success')
                logger.success(f"{email} update Password successfully ")
                return redirect(url_for('auth.login'))
            else:
                flash('User not found in database.', 'danger')
                return render_template('check_user.html')
        else:
            flash('Invalid OTP.', 'danger')
            return redirect(url_for('reset_pass.check_user'))
    
    except Exception as e:
        flash(f'An error occurred when reset password, try again later', 'danger')
        logger.error(f"An error occurred when reset password for {email} : {e}")
        return render_template('reset.html', email=email)
