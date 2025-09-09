from flask import Blueprint , request ,redirect ,flash , render_template, url_for
from module.config import users_collection ,otp_collection  ,EMAIL_PASSWORD ,EMAIL_USER
from datetime import datetime ,timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import smtplib

send_emails = Blueprint('send_emails', __name__)

def send_email(to_address, subject, html_content, image_path="subtitle.png"):
    smtp_server = 'smtp.gmail.com'
    port = 587
    from_address = EMAIL_USER
    password = EMAIL_PASSWORD

    message = MIMEMultipart()
    message['From'] = from_address
    message['To'] = to_address
    message['Subject'] = subject
    message.attach(MIMEText(html_content, 'html'))

    # Attach logo if available
    try:
        with open(image_path, 'rb') as img:
            mime_image = MIMEImage(img.read())
            mime_image.add_header('Content-ID', '<logo_image>')
            mime_image.add_header('Content-Disposition', 'inline', filename=image_path)
            message.attach(mime_image)
    except FileNotFoundError:
        print("Logo not found. Sending email without it.")

    smtpObj = None
    try:
        smtpObj = smtplib.SMTP(smtp_server, port)
        smtpObj.starttls()
        smtpObj.login(from_address, password)
        smtpObj.sendmail(from_address, to_address, message.as_string())
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")
    finally:
        if smtpObj:
            smtpObj.quit()

def send_email_reset(to_address, otp):    
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
    send_email(to_address, "Reset Your Password", html_content)

def send_email_welcome(to_address , username):    
    html_content = f"""
                <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                            <div style="text-align: center; margin-bottom: 20px;">
                                <img src="cid:logo_image" alt="Logo" style="max-width: 80px;">
                            </div>
                            <h2 style="text-align: center; color: #555;">Welcome to Subtranscribe!</h2>
                            <p>Hi {username},</p>
                            <p>Thank you for registering with Subtranscribe. We're excited to have you on board!</p>
                            <p>With Subtranscribe, you can easily transcribe and manage your audio and video files. We're here to help you make the most out of our services.</p>
                            <p>If you have any questions or need assistance, feel free to reach out to our
                            support team. We're always here to help!</p>
                            <p>Best Regards,<br>Team subtranscribe</p>
                            <div style="margin-top: 20px; text-align: center; font-size: 12px; color: #999;">
                                <p>© 2025 subtranscribe. All rights reserved.</p>
                            </div>
                        </div>
                    </body>
                </html>
            """
    send_email(to_address, "Welcome to Subtranscribe!", html_content)


def send_email_transcript(to_address ,username, user_id, transcript_id):
    html_content = f"""
                <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                            <div style="text-align: center; margin-bottom: 20px;">
                                <img src="cid:logo_image" alt="Logo" style="max-width: 80px;">
                            </div>
                            <h2 style="text-align: center; color: #555;">Your Transcript is Ready!</h2>
                            <p>Hi {username},</p>
                            <p>We are pleased to inform you that your transcript is now ready for download.</p>
                            <p>You can access your transcript by logging into your account and navigating to the "Dashboard" section.</p>
                            <p>Thank you for using Subtranscribe. We hope you find our service helpful and enjoyable.</p>
                            <a href="https://subtranscribe.koyeb.app/v1/{user_id}/download/{transcript_id}">Download Transcript</a>
                            <p>Best Regards,<br>Team subtranscribe</p>
                            <div style="margin-top: 20px; text-align: center; font-size: 12px; color: #999;">
                                <p>© 2025 subtranscribe. All rights reserved.</p>
                            </div>
                        </div>
                    </body>
                </html>
            """
    send_email(to_address, "Transcript Completed!", html_content)

