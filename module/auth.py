from flask import Blueprint ,request ,redirect,url_for ,flash,session ,render_template 
from module.config import users_collection 
from module.send_mail import send_email_welcome
# from module.config import limiter
from werkzeug.security import check_password_hash, generate_password_hash
import uuid

auth_bp = Blueprint('auth', __name__)
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """register new user in db"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        Email = request.form['email']
        confirm_password = request.form['c_password']
        user_id = str(uuid.uuid4())

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('auth.register'))    

        existing_user = users_collection.find_one({'username': username})
        existing_email = users_collection.find_one({'Email': Email})
        
        if existing_user or existing_email:
            flash('User already exists', 'danger')
            return redirect(url_for('auth.register'))
        
        hashed_password = generate_password_hash(password, method='scrypt', salt_length=16)
        users_collection.insert_one({'Email': Email,'username': username, 'password': hashed_password ,"user_id":user_id})
        session['user_id'] = user_id
        session['username'] = username  # Store username in session
        session['email'] = Email  # Store email in session

        send_email_welcome(Email, username)
        
        flash('Successfully registered! Welcome to Subtranscribe', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
# @limiter.limit("100 per hour")
def login():
    session.permanent = True
    if 'user_id' in session:
        user = users_collection.find_one({'user_id': session['user_id']})
        if user:
            return redirect(url_for('main_user', user_id=session['user_id']))
        else:
            session.clear()
    if request.method == 'POST':
    
        identifier = request.form['email']
        password = request.form['password']

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
            #     return redirect(url_for('main_user', user_id=user['user_id']))
        flash('Incorrect username or password', 'danger')
        return redirect(url_for('auth.login'))

    return render_template('login.html')

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    if request.method == 'GET':
        session.pop('user_id',None)
        session.pop('username',None)
        session.pop('password',None)
        session.clear()
        flash('Successfully logged out!', 'success')
    return redirect(url_for('auth.login'))