# from venv import logger
from flask import Flask , session , g
from flask_cors import CORS
from flask_caching import Cache
# from flask_limiter import Limiter
# from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from datetime import timedelta  
from flask_wtf.csrf import CSRFProtect , generate_csrf, validate_csrf
from pymongo import MongoClient 
import secrets
import os 

load_dotenv()

TOKEN_ONE = os.getenv("M_api_key")
TOKEN_THREE = os.getenv("A_api_key")
SESSION_USERS = os.getenv('SESSION_ID')
REDIS_UR = os.getenv("REDIS_URI")
EMAIL_USER = os.getenv("STMP_USER")
EMAIL_PASSWORD = os.getenv("STMP_PASSWORD")

# Get the absolute paths to the templates and static directories
template_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# Configure cache

# app.config['CACHE_TYPE'] = 'redis'
# app.config['CACHE_REDIS_URL'] = REDIS_UR

# cache = Cache(app)
# set token 
load_dotenv()

# limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

# CORS(app, 
#      supports_credentials=True, 
#      origins=['*'],
#      expose_headers=['Content-Type', 'X-CSRFToken', 'Cache-Control', 'X-Requested-With'],
#      allow_headers=['Content-Type', 'X-CSRFToken', 'Authorization', 'Cache-Control', 'X-Requested-With'],
#      methods=['GET', 'POST', 'OPTIONS'])
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['DEBUG'] = False  


app.secret_key = SESSION_USERS
csrf = CSRFProtect(app)

# Set up MongoDB connection
cluster = MongoClient(TOKEN_ONE)
dbase = cluster["Datedb"]  # Specify the database name
# fs = gridfs.GridFS(dbase)  # Create a GridFS instance for file storage
progress_collection = dbase['progress']  #(Collection)

dbs = cluster["User_DB"]  # Database name
users_collection = dbs["users"]  # Users collection
files_collection = dbs["files"]  # Files collection
otp_collection = dbs["otp"] # OTP collection

# Set up Flask session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

def create_app():
    app = Flask(__name__)
    csrf.init_app(app)
    return app

@app.before_request
def set_nonce():
    # نولد nonce جديد لكل request
    g.nonce = secrets.token_hex(16)

@app.after_request
def set_csrf_cookie(response):
    csrf_token = generate_csrf()
    
    response.set_cookie(
        'csrf_token',
        csrf_token,
        httponly=False,
        secure=True,
        samesite='Strict'
    )
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = "camera=(), microphone=(), geolocation=()"
    # csp = {
    #     "default-src": "'self'",
    #     "script-src": [
    #         "'self'",
    #         f"'nonce-{g.nonce}'",
    #         "https://cdn.tailwindcss.com",
    #         "https://cdn.jsdelivr.net",
    #         "https://cdnjs.cloudflare.com"
    #     ],
    #     "style-src": [
    #         "'self'",
    #         f"'nonce-{g.nonce}'",
    #         "https://cdn.tailwindcss.com",
    #         "https://cdn.jsdelivr.net",
    #         "https://cdnjs.cloudflare.com",
    #         "https://fonts.googleapis.com"
    #     ],
    #     "font-src": [
    #         "'self'",
    #         "https://cdn.tailwindcss.com",
    #         "https://cdn.jsdelivr.net",
    #         "https://cdnjs.cloudflare.com",
    #         "https://fonts.gstatic.com"
    #     ],
    #     "img-src": [
    #         "'self'",
    #         "data:",
    #         "https://cdn.tailwindcss.com",
    #         "https://cdn.jsdelivr.net",
    #         "https://cdnjs.cloudflare.com"
    #     ],
    #     "connect-src": [
    #         "'self'",
    #         "https://cdn.tailwindcss.com",
    #         "https://fonts.googleapis.com",
    #         "https://fonts.gstatic.com"
    #     ]
    # }
    # csp_policy = "; ".join([f"{k} {' '.join(v) if isinstance(v, list) else v}" for k, v in csp.items()])
    # response.headers["Content-Security-Policy"] = csp_policy

    return response

@app.after_request
def add_cache_headers(response):
    if 'text/html' in response.headers.get('Content-Type', ''):
        response.headers['Cache-Control'] = 'no-store'
    else:
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    return response