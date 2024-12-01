from pymongo import MongoClient
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import os

load_dotenv()

TOKEN_ONE = os.getenv("M_api_key")
TOKEN_THREE = os.getenv("A_api_key")

cluster = MongoClient(TOKEN_ONE)

dbs = cluster["User_DB"]  # Database name
users_collection = dbs["users"]  # Users collection
files_collection = dbs["files"]  # Files collection


def update_password():
    # البحث عن المستخدم باستخدام اسم المستخدم
    user = users_collection.find_one({"username": "Adel"})
    
    if user:
        # طباعة بيانات المستخدم وكلمة المرور القديمة
        pas = user['password']
        print(f'user: {user}')
        print("_" * 30)
        print(f'Old password: {pas}')
        print("_" * 30)

        # تحديد كلمة المرور الجديدة (مثال: "new_password123")
        new_password = "Adel@10a"  # استبدلها بكلمة المرور الجديدة
        hashed_password = generate_password_hash(new_password)
        # تحديث كلمة المرور في قاعدة البيانات
        update_result = users_collection.update_one(
            {"username": "Adel"},  # البحث عن المستخدم
            {"$set": {"password": hashed_password}}  # تحديث كلمة المرور
        )

        if update_result.matched_count > 0:
            print("Password updated successfully.")
        else:
            print("Password not changed.")
    else:
        print("User not found.")

update_password()

