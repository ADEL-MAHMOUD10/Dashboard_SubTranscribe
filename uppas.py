from pymongo import MongoClient
# from dotenv import load_dotenv
from datetime import datetime
from werkzeug.security import generate_password_hash
import os

# Load environment variables
# load_dotenv()

# MongoDB connection and database/collection setup
# TOKEN_ONE = os.getenv("M_api_key")
cluster = MongoClient("mongodb+srv://Adde:1234@cluster0.1xefj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

dbs = cluster["User_DB"]  # Database name
users_collection = dbs["users"]  # Users collection
files_collection = dbs["files"]  # Files collection

# Function to update the user's password
def update_password():
    user = users_collection.find_one({"username": "Adel"})
    if user:
        old_password = user['password']
        print(f"User: {user}")
        print("_" * 30)
        print(f"Old password: {old_password}")
        print("_" * 30)

        new_password = "Adel@10a"  # Replace with a new password
        hashed_password = generate_password_hash(new_password)
        update_result = users_collection.update_one(
            {"username": "Adel"},
            {"$set": {"password": hashed_password}}
        )

        if update_result.matched_count > 0:
            print("Password updated successfully.")
        else:
            print("Password not changed.")
    else:
        print("User not found.")

# Function to delete a file by ID
def delete_file():
    user_id = "c5276ce7-3107-4940-ad64-e02eb39a79c5"
    user_file = files_collection.find_one({'user_id': user_id})
    
    if user_file:
        delete_result = files_collection.delete_one({'transcript_id': "61fcea80-7221-4b99-adaf-9b3a253575fc"})
        if delete_result.deleted_count > 0:
            print("File deleted successfully.")
        else:
            print("Error deleting file.")
    else:
        print("File not found.")

# Function to add data to the database
def add_data():
    user = users_collection.find_one({'username': 'ADELMAHMOUD'})
    if user:
        for i in range(1, 15):
            file_name = f"Test File {i}"
            file_size = 1132383
            file_transcript_id = f'77919969-f59f-4148-88e4-8d22cfe81924{i}'
            file_upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            files_collection.insert_one({
                'username': 'ADELMAHMOUD',
                'user_id': '4c7a5d23-0105-468a-9974-38b97479d5ec',
                'file_name': file_name,
                'file_size': file_size,
                'transcript_id': file_transcript_id,
                'upload_time': file_upload_time
            })
        print("Data added successfully.")
    else:
        print("User not found.")

def totaluser():
    total_user = users_collection.count_documents({})
    print(f'total_user: {total_user}')
def totalfiles():
    total_files = files_collection.count_documents({})
    print(f'total_user: {total_files}')

# Main program to ask the user which function to run
def main():
    print("Choose a function to execute:")
    print("1. Update Password")
    print("2. Delete File")
    print("3. Add Data")
    print("4. Total user")
    print("5. Total Files")
    
    choice = input("Enter the number of your choice: ")
    
    if choice == "1":
        update_password()
    elif choice == "2":
        delete_file()
    elif choice == "3":
        add_data()
    elif choice == "4":
        totaluser()
    elif choice == "5":
        totalfiles()
    else:
        print("Invalid choice. Please enter a valid number.")

if __name__ == "__main__":
    main()
