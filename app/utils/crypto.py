from cryptography.fernet import Fernet
from app.utils.db import MongoDBConnection
import base64
import urllib.parse
from decouple import config
from app.utils.logger import logger

# Initialize encryption key for Telegram registration
TELEGRAM_ENCRYPTION_KEY = config('TELEGRAM_ENCRYPTION_KEY', default=Fernet.generate_key().decode())
cipher_suite = Fernet(TELEGRAM_ENCRYPTION_KEY.encode())

def encrypt_username(username):
    with MongoDBConnection() as (client, db):
        user=db.users.find_one({"username": username})
        user_id=str(user.get("_id"))
        return user_id

def decrypt_username(encrypted_text):
    from bson import ObjectId
    """Decrypt username from telegram bot registration"""
    with MongoDBConnection() as (client, db):
        user = db.users.find_one({"_id": ObjectId(encrypted_text)})
        if user:
            return user.get("username")