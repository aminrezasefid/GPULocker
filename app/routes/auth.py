from flask import Blueprint,render_template, request, session, redirect, url_for, flash
import pam
import pwd
from decouple import config,Csv
from app.utils.logger import logger
from app.utils.db import *
from functools import wraps
from app.utils.notification import get_unread_notifications_count
from cryptography.fernet import Fernet
import base64
import urllib.parse
from app.utils.crypto import encrypt_username, decrypt_username

auth_bp = Blueprint('auth', __name__)

# Initialize encryption key for Telegram registration
TELEGRAM_ENCRYPTION_KEY = config('TELEGRAM_ENCRYPTION_KEY', default=Fernet.generate_key().decode())
cipher_suite = Fernet(TELEGRAM_ENCRYPTION_KEY.encode())

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('dashboard.dashboard'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            # First check if the user exists in the system
            pwd.getpwnam(username)
            
            # Verify credentials using PAM
            auth = pam.pam()
            if auth.authenticate(username, password):
                session['username'] = username
                logger.info(f"User {username} successfully logged in")
                
                # Check if user is admin (based on PRIVILEGED_USERS in .env)
                privileged_users = config('PRIVILEGED_USERS', cast=Csv())
                is_admin = username in privileged_users
                session['is_admin'] = is_admin
                client, db = get_db_connection()
                try:
                    if not db.users.find_one({"username": username}):
                        db.users.insert_one({
                            "username": username,
                            "created_at": datetime.now()
                        })
                        logger.info(f"Added new user {username} to database")
                finally:
                    client.close()
                return redirect(url_for('dashboard.dashboard'))
            else:
                logger.warning(f"Failed login attempt for user {username}")
                flash('Invalid credentials')
        except KeyError:
            # User doesn't exist in the system
            logger.warning(f"Login attempt with non-existent user: {username}")
            flash('Invalid credentials')
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('auth.login'))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('auth.login'))
        
        # Check if user has registered Telegram
        
        if config("TG_ACCOUNT_REQUIRED",cast=bool):
            client, db = get_db_connection()
            logger.info(f"user inside tg account")
            try:
                username = session['username']
                # Check if the user has any telegram IDs in the telegram_users collection
                telegram_user = db.telegram_users.find_one({"username": username})
                if not telegram_user:
                    # User doesn't have telegram ID, redirect to registration
                    if request.endpoint != 'auth.register_telegram':
                        return redirect(url_for('auth.register_telegram'))
            finally:
                client.close()
            
        logger.info(f"User {session['username']} accessed {request.endpoint} from {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/register_telegram')
def register_telegram():
    if 'username' not in session:
        return redirect(url_for('auth.login'))
        
    username = session['username']
    with MongoDBConnection() as (client,db):
        # Check if the user has any telegram IDs in the telegram_users collection
        tg_user = db.telegram_users.find_one({"username": username})
        if tg_user:
            return redirect(url_for('dashboard.dashboard'))
    
    encrypted_username = encrypt_username(username)
    
    # Get bot username from environment
    bot_username = config('TELEGRAM_BOT_USERNAME', default='')
    telegram_link = f"https://t.me/{bot_username}?start={encrypted_username}"
    
    # Pass unread notifications count to the template
    unread_count = get_unread_notifications_count(username)
    
    return render_template('register_telegram.html', 
                          telegram_link=telegram_link,
                          unread_notifications_count=unread_count)