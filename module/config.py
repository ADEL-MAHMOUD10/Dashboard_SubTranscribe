# from venv import logger
from flask import Flask, redirect , session , g, render_template
from flask_cors import CORS
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from datetime import timedelta  
from flask_wtf.csrf import CSRFProtect , generate_csrf, validate_csrf
from pymongo import MongoClient 
from rq import Queue
import redis
import secrets
import os 
import uuid 

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

if REDIS_UR:
    app.config['CACHE_TYPE'] = 'redis'
    app.config['CACHE_REDIS_URL'] = REDIS_UR
else:
    app.config['CACHE_TYPE'] = 'simple'  # Fallback to simple cache

app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes default cache timeout

cache = Cache(app)
# set token 
load_dotenv()

# Configure rate limiter with graceful Redis fallback
try:
    if REDIS_UR:
        # Test Redis connection with short timeout
        test_redis = redis.from_url(REDIS_UR, socket_connect_timeout=2, socket_timeout=2)
        test_redis.ping()
        limiter_storage = REDIS_UR
        print("✅ Rate limiter using Redis")
    else:
        limiter_storage = "memory://"
        print("⚠️  Rate limiter using in-memory storage (not suitable for production)")
except Exception as e:
    print(f"⚠️  Redis rate limiter failed: {e}")
    print("   Falling back to in-memory rate limiting")
    limiter_storage = "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=limiter_storage,
    headers_enabled=True,
    default_limits=["1000 per hour", "100 per minute"],
    in_memory_fallback_enabled=True
)

CORS(app, 
     supports_credentials=True, 
     origins=['https://subtranscribe.koyeb.app'],
     expose_headers=['Content-Type', 'X-CSRFToken', 'Cache-Control', 'X-Requested-With'],
     allow_headers=['Content-Type', 'X-CSRFToken', 'Authorization', 'Cache-Control', 'X-Requested-With'],
     methods=['GET', 'POST', 'OPTIONS'])
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['DEBUG'] = False
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files  
# In module/config.py

app.secret_key = SESSION_USERS
csrf = CSRFProtect(app)

# Set up MongoDB connection
# dbase = cluster["Datedb"]  # Specify the database name
# # fs = gridfs.GridFS(dbase)  # Create a GridFS instance for file storage
# progress_collection = dbase['progress']  #(Collection)
cluster = MongoClient(TOKEN_ONE)

dbs = cluster["User_DB"]  # Database name
users_collection = dbs["users"]  # Users collection
files_collection = dbs["files"]  # Files collection
otp_collection = dbs["otp"] # OTP collection

# Set up Flask session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

users_collection.create_index("username", unique=True)
users_collection.create_index("Email", unique=True)

# Set up RQ (Redis Queue) for background jobs
# Note: RQ doesn't support Windows directly due to os.fork() limitation
# For Windows development, use synchronous transcription fallback
import platform

if platform.system() == 'Windows':
    print("⚠️  Windows detected: RQ (background jobs) not supported")
    print("   Using synchronous transcription (blocking) instead")
    q = None
elif REDIS_UR:
    try:
        # Don't decode responses - RQ needs binary data
        redis_conn = redis.from_url(REDIS_UR, socket_connect_timeout=2, socket_timeout=2)
        redis_conn.ping()
        # Use a named queue so workers can listen on the same queue name
        q = Queue('transcription', connection=redis_conn)
        print("✅ RQ Queue initialized with Redis")
    except redis.ConnectionError as e:
        print(f"⚠️  Warning: Redis connection failed: {e}")
        print("   Background jobs disabled. Transcription will block requests.")
        q = None
    except Exception as e:
        print(f"⚠️  Warning: RQ Queue initialization failed: {e}")
        print("   Background jobs disabled. Transcription will block requests.")
        q = None
else:
    print("⚠️  Warning: REDIS_URI not set. Background jobs (RQ) disabled.")
    print("   App will work but transcription will block HTTP requests.")
    q = None

def create_app():
    app = Flask(__name__)
    csrf.init_app(app)
    return app

def clear_user_cache(user_id):
    """Clear cache for a specific user"""
    try:
        cache.delete(f"dashboard_{user_id}")
        cache.delete(f"user_{user_id}")
    except Exception as e:
        print(f"Error clearing cache for user {user_id}: {e}")

def clear_all_cache():
    """Clear all cache"""
    try:
        cache.clear()
    except Exception as e:
        print(f"Error clearing all cache: {e}")

def is_session_valid() -> bool:
    """Validate the session's user_id and session_token against the database.
    Supports both legacy single token and multi-device token arrays.
    """
    try:
        user_id = session.get('user_id')
        session_token = session.get('session_token')
        if not user_id or not session_token:
            return False
        user = users_collection.find_one({'user_id': user_id}, {'session_token': 1, 'session_tokens': 1})
        if not user:
            return False
        tokens = user.get('session_tokens')
        if isinstance(tokens, list) and session_token in tokens:
            return True
        return user.get('session_token') == session_token
    except Exception:
        return False

@app.before_request
def set_nonce():
    g.nonce = secrets.token_hex(16)

@app.after_request
def security_headers(response):
    csrf_token = generate_csrf()
    
    response.set_cookie(
        'csrf_token',
        csrf_token,
        httponly=False,
        secure=True,
        samesite='Strict'
    )

    # 🔒 Security Headers
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = "camera=(), microphone=(), geolocation=()"

    # 🛡️ CSP Policy (FULLY WORKING)
    csp = {
        "default-src": "'self'",
        
        "script-src": [
            "'self'",
            f"'nonce-{g.nonce}'",
            "https://cdn.tailwindcss.com",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
            "https://unpkg.com"
        ],

        "style-src": [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.tailwindcss.com",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
            "https://fonts.googleapis.com"
        ],
        
        "font-src": [
            "'self'",
            "data:",
            "https://fonts.gstatic.com",
            "https://cdnjs.cloudflare.com",
            "https://cdn.jsdelivr.net"
        ],
        
        "img-src": [
            "'self'",
            "data:",
        ],
        
        "connect-src": [
            "'self'",
            "https://subtranscribe.koyeb.app",
            "https://fonts.googleapis.com",
            "https://fonts.gstatic.com",
            "https://cdn.jsdelivr.net",
            "https://unpkg.com"
        ],
    }


    # build policy
    csp_policy = "; ".join([f"{k} {' '.join(v) if isinstance(v, list) else v}" for k, v in csp.items()])
    response.headers["Content-Security-Policy"] = csp_policy

    # Cache rules
    if 'text/html' in response.headers.get('Content-Type', ''):
        response.headers['Cache-Control'] = 'no-store'
    else:
        response.headers['Cache-Control'] = 'public, max-age=31536000'

    return response


# 404 Error
@app.errorhandler(404)
def page_not_found(e):
    error_id = str(uuid.uuid4())
    error_message = "Page Not Found. The requested resource could not be found."
    user_id = session.get('user_id')
    return render_template('error.html', error=error_message, user_id=user_id, error_id=error_id), 404

# 502 Error
@app.errorhandler(502)
def bad_gateway(e):
    error_id = str(uuid.uuid4())
    error_message = "Bad Gateway. The server received an invalid response from the upstream server."
    user_id = session.get('user_id')
    return render_template('error.html', error=error_message, user_id=user_id, error_id=error_id), 502

@app.errorhandler(429)
def too_many_requests(e):
    error_id = str(uuid.uuid4())
    error_message = "Too Many Requests. You have exceeded the rate limit. Please try again later."
    user_id = session.get('user_id')
    return render_template('error.html', error=error_message, user_id=user_id, error_id=error_id), 429
