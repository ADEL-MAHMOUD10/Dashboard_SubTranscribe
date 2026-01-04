from flask import Blueprint ,request ,redirect,url_for ,flash,session ,render_template 
from module.config import users_collection, limiter, cache 
from module.config import is_session_valid
from module.send_mail import send_email_welcome
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo.errors import DuplicateKeyError
from loguru import logger
from datetime import datetime, timezone
import uuid
import re
import hashlib
auth_bp = Blueprint('auth', __name__)

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$') # powerful 
# EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+") # simple regex validation not used now
PASS_REGEX = r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$'

def login_rate_key():
    ip = request.headers.get("CF-Connecting-IP", request.remote_addr)
    identifier = request.form.get('email')

    if identifier:
        identifier = identifier.strip().lower()
        return f"login:{identifier}:{ip}"

    return f"login:anonymous:{ip}"


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    """register new user in db"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        Email = request.form.get('email', '').strip()
        confirm_password = request.form.get('c_password','').strip()
        reg_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
        user_id = str(uuid.uuid4())

        try:
            if password != confirm_password:
                flash('Passwords do not match', 'danger')
                return redirect(url_for('auth.register'))    
            
            if not re.match(PASS_REGEX, password):
                flash('Password must be at least 8 characters long and include uppercase, lowercase, number, and special character.', 'danger')
                return redirect(url_for('auth.register'))
            
            if not username or len(username) < 4:
                flash('Username must be at least 4 characters long', 'danger')
                return redirect(url_for('auth.register'))
            
            if not Email or not EMAIL_REGEX.match(Email):
                flash('Invalid email address', 'danger')
                return redirect(url_for('auth.register'))
            
            hashed_password = generate_password_hash(password, method='scrypt', salt_length=16)
            session_token = str(uuid.uuid4())
            users_collection.insert_one({
                'Email': Email,
                'username': username,
                'password': hashed_password ,
                "user_id":user_id,
                "created_at": reg_time,
                "last_login_req": reg_time,
                "settings": {
                        "accent_color": "purple",
                        "theme": "dark",
                        "notifications": {
                            "email": True,
                            "marketing": False,
                            "processing": True
                        }
                },
                'session_tokens': [session_token]
                })
            session['user_id'] = user_id
            session['username'] = username  # Store username in session
            session['email'] = Email  # Store email in session
            session['session_token'] = session_token

            try:
                send_email_welcome(Email, username)
            except Exception as e:
                logger.error(f"Error sending welcome email to {Email}: {e}")
                        
            flash('Successfully registered! Welcome to Subtranscribe', 'success')
            return redirect(url_for('auth.login'))
                
        except DuplicateKeyError as e:
            error_msg = str(e)
            if 'username' in error_msg:
                flash('Username already exists', 'danger')
            elif 'Email' in error_msg:
                flash('Email already registered', 'danger')
            else:
                flash('Username or Email already exists', 'danger')
            return redirect(url_for('auth.register'))
        
        except Exception as e:
            flash(f'An error occurred, try again later.', 'danger')
            logger.error(f"Error during registration: {e}")
            return redirect(url_for('auth.register'))

    return render_template('register.html')

# def deduct_on_failed_login(response):
#     if response.status_code in (401, 403):
#         return True
#     return False

@auth_bp.route('/login', methods=['GET', 'POST'])
# @limiter.limit("10 per minute", key_func=login_rate_key, deduct_when=deduct_on_failed_login,error_message="Too many failed login attempts")
@limiter.limit("10 per minute", key_func=login_rate_key,error_message="Too many failed login attempts")
def login():
    session.permanent = True
    if 'user_id' in session and is_session_valid():
        return redirect(url_for('main_user', user_id=session['user_id']))

    if request.method == 'POST':

        identifier = request.form['email'].strip()
        password = request.form.get('password', '')
        if not identifier or not password:
            flash('Please enter both username/email and password', 'danger')
            return redirect(url_for('auth.login'))
        try:
            login_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
            user = users_collection.find_one({'$or':[{'username':identifier},{'Email':identifier}]})
            if user and check_password_hash(user['password'], password):
                new_session_token = str(uuid.uuid4())
                ip = request.headers.get(
                    'CF-Connecting-IP',
                    request.headers.get('X-Forwarded-For', request.remote_addr)
                )
                users_collection.update_one(
                    {'user_id': user['user_id']},
                    {
                        '$set': {
                            'last_login_req': login_time
                            },
                        '$push': {
                            'session_tokens': {
                                '$each': [{
                                    'token': new_session_token,
                                    'created_at': login_time,
                                    "last_login": login_time,
                                    "device": request.user_agent.string,
                                    "ip_hash": hashlib.sha256(ip.encode()).hexdigest()
                                }],
                                '$slice': -5
                            }
                        }
                    }
                )
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                session['session_token'] = new_session_token
                flash('Successfully logged in!', 'success')
                # if user and 'Email' in user:
                #     send_email_welcome(user['Email'], user['username'])
                #     return redirect(url_for('main_user', user_id=user['user_id']))
                # else:
                #     flash('No email found for this user', 'danger')
                return redirect(url_for('main_user', user_id=user['user_id']))
            else:
                logger.warning(f"Failed login attempt for identifier: {identifier}")
                flash('Incorrect username or password', 'danger')
                return redirect(url_for('auth.login'))
        except Exception as e:
            logger.error(f"Error during login for identifier {identifier}: {e}")
            flash('An error occurred, please try again later', 'danger')
            return redirect(url_for('auth.login'))
    return render_template('login.html')

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    try:
        user_id = session.get('user_id')
        current_token = session.get('session_token')
        if user_id and current_token:
            users_collection.update_one(
                {
                    'user_id': user_id,
                },
                {
                    '$pull': {
                        'session_tokens': {
                            'token': current_token
                        }
                    }
                }
            )
    except Exception:
        logger.error(f"Error logging out user {user_id}")
        flash('An error occurred, please try again later', 'danger')
        return redirect(url_for('auth.login'))
    try:
        session.clear()
        cache.delete(f"user:{user_id}")
        flash('Successfully logged out!', 'success')
        return redirect(url_for('auth.login'))
    except Exception:
        logger.error(f"Error clearing session and cache")
        flash('An error occurred, please try again later', 'danger')
        return redirect(url_for('auth.login'))
