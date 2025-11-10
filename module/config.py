from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
# from models import data
import smtplib
import logging
import dotenv
import ssl
import os


# Load environment variables from .env file
dotenv.load_dotenv()
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Portfolio API", description="Backend API for portfolio contact form")

# ALLOWED_ORIGINS = [
#     "https://adelmahmoud.vercel.app",
#     "http://localhost:3000",
#     "http://127.0.0.1:5000"
# ]

# CORS middleware to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://adelmahmoud.vercel.app"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
SMTP_SERVER= os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT= int(os.getenv("SMTP_PORT", "587"))
EMAIL_USERNAME= os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD= os.getenv("EMAIL_PASSWORD", "")
FROM_EMAIL= os.getenv("FROM_EMAIL", "")
TO_EMAIL= os.getenv("TO_EMAIL", "")
USE_TLS= os.getenv("USE_TLS", "true").lower() == "true"
# Email configuration with multiple provider support
def get_email_config():
    return {
        "SMTP_SERVER": SMTP_SERVER,
        "SMTP_PORT": SMTP_PORT,
        "EMAIL_USERNAME": EMAIL_USERNAME,
        "EMAIL_PASSWORD": EMAIL_PASSWORD,
        "FROM_EMAIL": FROM_EMAIL,
        "TO_EMAIL": TO_EMAIL,
        "USE_TLS": USE_TLS,
    }
# Pydantic models for request validation
class ContactMessage(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    subject: str
    message: str

class EmailResponse(BaseModel):
    success: bool
    message: str
    timestamp: datetime

# Enhanced email sending function with better error handling
async def send_email(contact_data: ContactMessage):
    config = get_email_config()

    # Validate configuration
    if not all([config["EMAIL_USERNAME"], config["EMAIL_PASSWORD"], 
                config["FROM_EMAIL"], config["TO_EMAIL"]]):
        logger.error("Email configuration is incomplete")
        return False, "Email configuration is incomplete"

    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Portfolio Contact: {contact_data.subject}"
        msg["From"] = config["FROM_EMAIL"]
        msg["To"] = config["TO_EMAIL"]
        msg["Reply-To"] = contact_data.email  # Allow direct reply to sender

        # Create HTML email content
        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>New Contact Form Submission</title>
            <style>
                body {{
                    font-family: 'Arial', sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px 10px 0 0;
                    text-align: center;
                }}
                .content {{
                    background: #f9f9f9;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                    border: 1px solid #e0e0e0;
                }}
                .field {{
                    margin-bottom: 20px;
                    padding: 15px;
                    background: white;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }}
                .field-label {{
                    font-weight: bold;
                    color: #667eea;
                    margin-bottom: 5px;
                }}
                .field-value {{
                    color: #333;
                    word-wrap: break-word;
                }}
                .message-content {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    border: 1px solid #e0e0e0;
                    margin-top: 10px;
                    white-space: pre-wrap;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    padding: 15px;
                    color: #666;
                    font-size: 12px;
                }}
                .reply-info {{
                    background: #e8f4fd;
                    border: 1px solid #b3d9f2;
                    border-radius: 8px;
                    padding: 15px;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📧 New Contact Form Submission</h1>
                <p>From your portfolio website</p>
            </div>

            <div class="content">
                <div class="field">
                    <div class="field-label">👤 Full Name:</div>
                    <div class="field-value">{contact_data.firstName} {contact_data.lastName}</div>
                </div>

                <div class="field">
                    <div class="field-label">📧 Email Address:</div>
                    <div class="field-value">{contact_data.email}</div>
                </div>

                <div class="field">
                    <div class="field-label">📝 Subject:</div>
                    <div class="field-value">{contact_data.subject}</div>
                </div>

                <div class="field">
                    <div class="field-label">💬 Message:</div>
                    <div class="message-content">{contact_data.message}</div>
                </div>

                <div class="field">
                    <div class="field-label">⏰ Received:</div>
                    <div class="field-value">{datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}</div>
                </div>

                <div class="reply-info">
                    <strong>💡 Quick Reply:</strong> You can reply directly to this email to respond to {contact_data.firstName}.
                </div>
            </div>

            <div class="footer">
                <p>This email was sent automatically from your portfolio contact form.</p>
                <p>Sender IP and browser info available in server logs for security.</p>
            </div>
        </body>
        </html>
        '''

        # Create plain text version
        text_content = f'''
        New Contact Form Submission

        Name: {contact_data.firstName} {contact_data.lastName}
        Email: {contact_data.email}
        Subject: {contact_data.subject}

        Message:
        {contact_data.message}

        Received: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

        Reply directly to this email to respond to {contact_data.firstName}.
        '''

        # Attach both HTML and text versions
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")

        msg.attach(part1)
        msg.attach(part2)

        # Send email with enhanced error handling
        try:
            if config["USE_TLS"]:
                context = ssl.create_default_context()
                with smtplib.SMTP(config["SMTP_SERVER"], config["SMTP_PORT"]) as server:
                    server.starttls(context=context)
                    logger.info(f"Attempting to login with username: {config['EMAIL_USERNAME']}")
                    server.login(config["EMAIL_USERNAME"], config["EMAIL_PASSWORD"])
                    server.send_message(msg)
            else:
                with smtplib.SMTP_SSL(config["SMTP_SERVER"], config["SMTP_PORT"]) as server:
                    server.login(config["EMAIL_USERNAME"], config["EMAIL_PASSWORD"])
                    server.send_message(msg)

            logger.info(f"Email sent successfully to {config['TO_EMAIL']}")
            return True, "Email sent successfully"

        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP Authentication failed: {str(e)}"
            logger.error(error_msg)
            return False, "Email authentication failed. Please check your email credentials."

        except smtplib.SMTPRecipientsRefused as e:
            error_msg = f"SMTP Recipients refused: {str(e)}"
            logger.error(error_msg)
            return False, "Invalid recipient email address."

        except smtplib.SMTPServerDisconnected as e:
            error_msg = f"SMTP Server disconnected: {str(e)}"
            logger.error(error_msg)
            return False, "Email server connection lost. Please try again."

        except Exception as e:
            error_msg = f"Unexpected email error: {str(e)}"
            logger.error(error_msg)
            return False, "Failed to send email due to server error."

    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        logger.error(error_msg)
        return False, "Failed to prepare email for sending."

# API Routes
@app.post("/api/contact", response_model=EmailResponse)
async def send_contact_email(contact_data: ContactMessage,request: Request, background_tasks: BackgroundTasks):
    '''
    Send contact form email via SMTP
    '''
    origin = request.headers.get("origin")
    if origin != "https://adelmahmoud.vercel.app":
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        # Send email immediately for better error feedback
        success, message = await send_email(contact_data)

        if success:
            return EmailResponse(
                success=True,
                message="Your message has been sent successfully! I'll get back to you soon.",
                timestamp=datetime.now()
            )
        else:
            raise HTTPException(status_code=500, detail=message)

    except Exception as e:
        logger.error(f"Error processing contact form: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to send message. Please check the server configuration or try again later."
        )

@app.get("/api/health")
async def health_check():
    '''
    Health check endpoint
    This function provides a simple health check endpoint for the service.
    It returns the current status of the service along with a timestamp.
    Returns:
        dict: A dictionary containing the health status and current timestamp
    '''
    return {"status": "healthy", "timestamp": datetime.now()}  # Returns a JSON response with status and current time


app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    '''
    Serve the main portfolio page
    '''
    try:
        with open("templates/base.html", "r", encoding="utf-8") as file:
            return HTMLResponse(content=file.read(), status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Portfolio not found</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=5000, reload=True)
