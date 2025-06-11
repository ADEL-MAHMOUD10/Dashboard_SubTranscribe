from flask import Flask
from flask_cors import CORS
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from datetime import timedelta  
from pymongo import MongoClient 
import os 

load_dotenv()

TOKEN_ONE = os.getenv("M_api_key")
TOKEN_THREE = os.getenv("A_api_key")
SESSION_USERS = os.getenv('SESSION_ID')
REDIS_URI = os.getenv("REDIS_URI")
REDIS_TOKEN = os.getenv("REDIS_TOKEN")
EMAIL_USER = os.getenv("STMP_USER")
EMAIL_PASSWORD = os.getenv("STMP_PASSWORD")

# Get the absolute paths to the templates and static directories
template_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# Configure cache

app.config['CACHE_TYPE'] = 'redis'
app.config['CACHE_REDIS_URL'] = REDIS_URI
cache = Cache(app)

# set token 
load_dotenv()



limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["700 per hour"],
    storage_uri= REDIS_URI
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
app.config['DEBUG'] = False  


app.secret_key = SESSION_USERS

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