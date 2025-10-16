from flask import Blueprint ,request ,redirect,url_for ,flash,session ,render_template 
from module.config import users_collection, limiter, cache 
from module.send_mail import send_email_welcome
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo.errors import DuplicateKeyError
from loguru import logger
import uuid
import re

auth_bp = Blueprint('auth', __name__)

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$') # powerful 
# EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+") # simple regex for email validation not used now

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    """register new user in db"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        Email = request.form.get('email', '').strip()
        confirm_password = request.form.get('c_password')
        user_id = str(uuid.uuid4())

        try:
            if password != confirm_password:
                flash('Passwords do not match', 'danger')
                return redirect(url_for('auth.register'))    
            
            if len(password) < 8:
                flash('Password must be at least 8 characters long', 'danger')
                return redirect(url_for('auth.register'))
            if not username or len(username) < 4:
                flash('Username must be at least 4 characters long', 'danger')
                return redirect(url_for('auth.register'))
            if not Email or not EMAIL_REGEX.match(Email):
                flash('Invalid email address', 'danger')
                return redirect(url_for('auth.register'))
            
            hashed_password = generate_password_hash(password, method='scrypt', salt_length=16)
            users_collection.insert_one({
                'Email': Email,
                'username': username,
                'password': hashed_password ,
                "user_id":user_id
                })
            session['user_id'] = user_id
            session['username'] = username  # Store username in session
            session['email'] = Email  # Store email in session

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

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute")
def login():
    session.permanent = True
    if 'user_id' in session:
        user = users_collection.find_one({'user_id': session['user_id']})
        if user:
            return redirect(url_for('main_user', user_id=session['user_id']))
        else:
            session.clear()
            flash('Session expired, please log in again', 'warning')
    if request.method == 'POST':
    
        identifier = request.form['email'].strip()
        password = request.form.get('password', '')
        if not identifier or not password:
            flash('Please enter both username/email and password', 'danger')
            return redirect(url_for('auth.login'))
        try:
            user = users_collection.find_one({'$or':[{'username':identifier},{'Email':identifier}]})
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['user_id']  # Store user_id in session
                session['username'] = user['username']  # Store username in session
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
    if request.method == 'GET':
        session.pop('user_id',None)
        session.pop('username',None)
        session.pop('email',None)
        session.clear()
        cache.clear()
        flash('Successfully logged out!', 'success')
    return redirect(url_for('auth.login'))