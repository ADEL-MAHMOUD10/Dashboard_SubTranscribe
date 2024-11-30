from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Secret key for session management

# Connect to MongoDB using MongoClient
client = MongoClient("mongodb+srv://Adde:1234@cluster0.1xefj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")  # Change URL if you're using another server
db = client["your_database_name"]  # Database name
users_collection = db["users"]  # Users collection
files_collection = db["files"]  # Files collection

@app.route('/')
def main():
    return render_template('index.html')

# Registration page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))

        existing_user = users_collection.find_one({'username': username})
        if existing_user:
            flash('User already exists', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        users_collection.insert_one({'username': username, 'password': hashed_password})
        flash('Successfully registered! You can now log in', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = users_collection.find_one({'username': username})
        if user and check_password_hash(user['password'], password):
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard', username=username))
        else:
            flash('Incorrect username or password', 'danger')

    return render_template('login.html')

# File upload page
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files['file']
        username = request.form['username']

        if file:
            # Create UUID for the file
            file_uuid = str(uuid.uuid4())
            filename = file.filename
            file_path = os.path.join('uploads', filename)
            
            # Save the file on the server (in the "uploads" folder by default)
            file.save(file_path)

            # Add file details to the database
            file_data = {
                'username': username,
                'filename': filename,
                'uuid': file_uuid,
                'upload_date': datetime.now()
            }
            files_collection.insert_one(file_data)

            flash('File uploaded successfully', 'success')
            return redirect(url_for('dashboard', username=username))

    return render_template('upload.html')

# Dashboard page to display files
@app.route('/dashboard/<username>')
def dashboard(username):
    # Retrieve files for the user
    files = files_collection.find({'username': "Adel"})
    return render_template('dashboard.html', username="Adel", files=files)

# Link to download the file
@app.route('/download/<uuid>')
def download(uuid):
    file_data = files_collection.find_one({'uuid': uuid})
    if file_data:
        file_path = os.path.join('uploads', file_data['filename'])
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True)
