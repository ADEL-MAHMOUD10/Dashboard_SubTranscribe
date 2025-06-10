from flask import Blueprint , request ,redirect ,flash , render_template, url_for
from module.config import users_collection ,otp_collection ,limiter ,EMAIL_PASSWORD ,EMAIL_USER
from werkzeug.security import generate_password_hash
from datetime import datetime ,timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import smtplib
import random

reset_pass_bp = Blueprint('reset_pass', __name__)

@reset_pass_bp.route('/check_user', methods=['GET', 'POST'])
@limiter.limit("60 per hour")
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
        return redirect(url_for('reset_pass.check_user'))
    return render_template('check_user.html')
        
@reset_pass_bp.route('/reset_password', methods=['POST'])
@limiter.limit("60 per hour")
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