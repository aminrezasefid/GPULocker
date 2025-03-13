from flask import Blueprint,render_template, request, session, redirect, url_for, flash
import pam
import pwd
from decouple import config,Csv
from app.utils.logger import logger
from app.utils.db import *
from functools import wraps
auth_bp = Blueprint('auth', __name__)

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
        logger.info(f"User {session['username']} accessed {request.endpoint} from {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated_function