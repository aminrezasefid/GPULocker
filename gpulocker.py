from flask import Flask, render_template, request, session, redirect, url_for, flash
import pam
import subprocess
import os
from functools import wraps
import pwd
import logging
from logging.handlers import RotatingFileHandler
from decouple import config, Csv
from threading import Lock
from datetime import datetime, timedelta
import pymongo
import schedule as sched_module
from pymongo import MongoClient
from bson import ObjectId
import jdatetime
import shutil

# Add disk usage cache
DISK_USAGE_CACHE = {}
DISK_CACHE_TIMEOUT = config("DISK_CACHE_TIMEOUT",10,cast=int)   # 10 minutes in seconds

# Add context manager for MongoDB connections
class MongoDBConnection:
    def __init__(self):
        self.client = None
        
    def __enter__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        return self.client, self.client.gpulocker
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            self.client.close()

# Helper functions to reduce code duplication
def get_db_connection():
    """Create and return a MongoDB connection and database"""
    client = MongoClient('mongodb://localhost:27017/')
    return client, client.gpulocker

def set_gpu_permission(username, gpu_id, grant=True):
    """Set or remove GPU permission for a user
    Args:
        username: Username to modify permissions for
        gpu_id: GPU ID to modify permissions for
        grant: True to grant access, False to remove access
    Returns:
        bool: Success status
    """
    try:
        user_info = pwd.getpwnam(username)
        uid = user_info.pw_uid
        gpu_device = f'/dev/nvidia{gpu_id}'
        
        if grant:
            subprocess.run(['sudo', 'setfacl', '-m', f'u:{uid}:rw', gpu_device], check=True)
            logger.debug(f'Granted access to GPU {gpu_id} for user {username}')
        else:
            subprocess.run(['sudo', 'setfacl', '-x', f'u:{uid}', gpu_device], check=True)
            logger.debug(f'Removed access to GPU {gpu_id} for user {username}')
        return True
    except (KeyError, subprocess.CalledProcessError) as e:
        logger.error(f'Failed to {"grant" if grant else "remove"} access for user {username}: {str(e)}')
        return False

def is_user_using_gpu(username, gpu_id):
    """Check if a user is actively using a specific GPU
    Returns:
        bool: True if user is using the GPU, False otherwise
    """
    try:
        nvidia_smi = subprocess.run(
            ['sudo', 'nvidia-smi', '--id=' + str(gpu_id), '--query-compute-apps=pid', '--format=csv,noheader'],
            capture_output=True, text=True, check=True
        )
        
        if not nvidia_smi.stdout.strip():
            return False
            
        for line in nvidia_smi.stdout.strip().split('\n'):
            if not line.strip():
                continue
            
            pid = line.strip()
            try:
                process_owner = subprocess.run(
                    ['ps', '-o', 'user=', '-p', pid],
                    capture_output=True, text=True, check=True
                ).stdout.strip()
                
                if process_owner == username:
                    return True
            except subprocess.CalledProcessError:
                continue
                
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking if user {username} is using GPU {gpu_id}: {str(e)}")
        return False

def update_allocation_status(db, allocation_id, released=True):
    """Update the status of a GPU allocation in the database
    Args:
        db: MongoDB database connection
        allocation_id: ID of the allocation to update
        released: True to mark as released, False to mark as active
    Returns:
        bool: Success status
    """
    try:
        release_time = datetime.now() if released else None
        db.gpu_allocations.update_one(
            {'_id': ObjectId(allocation_id) if isinstance(allocation_id, str) else allocation_id},
            {'$set': {'released_at': release_time}}
        )
        logger.debug(f"Updated allocation {allocation_id} status: released={released}")
        return True
    except Exception as e:
        logger.error(f"Failed to update allocation status: {str(e)}")
        return False

def format_allocations_for_display(allocations):
    """Format allocation dates for display using jdatetime
    Args:
        allocations: List of allocation documents from MongoDB
    Returns:
        List of formatted allocation documents
    """
    for allocation in allocations:
        allocation['allocated_at'] = jdatetime.datetime.fromgregorian(
            datetime=allocation['allocated_at']).strftime('%Y-%m-%d %H:%M:%S')
        allocation['expiration_time'] = jdatetime.datetime.fromgregorian(
            datetime=allocation['expiration_time']).strftime('%Y-%m-%d %H:%M:%S')
    return allocations

GPU_LOCK=Lock()
# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
logFormatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s :: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)
consoleHandler.setFormatter(logFormatter)
fileHandler = logging.FileHandler('gpulock.log')
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
logger.addHandler(fileHandler)

app = Flask(__name__)
app.secret_key = config('SECRET_KEY')

# Get available GPUs from environment
GPU_DICT=eval(config('GPU_CONFIG'))
AVAILABLE_GPUs = {}

def initialize_gpu_tracking():
    """Initialize available GPU tracking from GPU_DICT"""
    global AVAILABLE_GPUs
    AVAILABLE_GPUs = {gpu_type: list(gpus) for gpu_type, gpus in GPU_DICT.items()}

            
    logger.info(f"Initialized available GPUs: {AVAILABLE_GPUs}")
    return True

def setup_database():
    """Create MongoDB connection and required collections"""
    try:
        client = MongoClient('mongodb://localhost:27017/')
        db = client.gpulocker
        
        # Create an index on username field if it doesn't exist
        db.gpu_allocations.create_index("username")
        
        logger.info("MongoDB connection and setup completed successfully")
        return client
    except Exception as e:
        logger.error(f"Failed to setup MongoDB connection: {str(e)}")
        raise

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Root route that redirects to the login page"""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('dashboard'))
        
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
                return redirect(url_for('dashboard'))
            else:
                logger.warning(f"Failed login attempt for user {username}")
                flash('Invalid credentials')
        except KeyError:
            # User doesn't exist in the system
            logger.warning(f"Login attempt with non-existent user: {username}")
            flash('Invalid credentials')
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    logger.debug(f'User {session["username"]} accessed dashboard')
    username = session["username"]
    
    # Get user's GPU allocations from MongoDB
    try:
        with MongoDBConnection() as (client, db):
            # Query for active allocations (where released_at is None)
            allocations = list(db.gpu_allocations.find({
                'username': username,
                'released_at': None
            }))
            
            # For admin user "amin", get all active allocations
            all_allocations = []
            authorized_users = config('PRIVILEGED_USERS', cast=Csv())
            is_admin=False
            if username in authorized_users:
                is_admin=True
                all_allocations = list(db.gpu_allocations.find({
                    'released_at': None
                }))
                all_allocations = format_allocations_for_display(all_allocations)
            
            # Format dates for display
            allocations = format_allocations_for_display(allocations)
            
    except Exception as e:
        logger.error(f"Error fetching allocations: {str(e)}")
        allocations = []
        all_allocations = []
    
    # Get user's disk usage
    used_bytes, used_by_others_bytes, total_bytes = get_user_disk_usage(username)
    disk_usage = {
        'used': format_size(used_bytes),
        'used_by_others': format_size(used_by_others_bytes),
        'free': format_size(total_bytes - used_bytes - used_by_others_bytes),
        'total': format_size(total_bytes),
        'percent_used': round((used_bytes / total_bytes) * 100, 2) if total_bytes > 0 else 0,
        'percent_others': round((used_by_others_bytes / total_bytes) * 100, 2) if total_bytes > 0 else 0,
        'percent_free': round(((total_bytes - used_bytes - used_by_others_bytes) / total_bytes) * 100, 2) if total_bytes > 0 else 0
    }
    
    return render_template('dashboard.html', 
                          gpu_dict=AVAILABLE_GPUs, 
                          allocations=allocations,
                          all_allocations=all_allocations,
                          is_admin=is_admin,
                          disk_usage=disk_usage)

def allocate_gpu(username, gpu_type, gpu_id, days):
    """Allocate a GPU to a user with proper permission setting and database tracking
    
    Args:
        username: Username to allocate GPU to
        gpu_type: Type of GPU being allocated
        gpu_id: ID of the GPU to allocate
        days: Number of days for allocation
        
    Returns:
        tuple: (success, allocation_id or error_message)
    """
    try:
        logger.debug(f"Allocating GPU {gpu_id} ({gpu_type}) to user {username} for {days} days")
        
        # Calculate expiration time
        allocation_time = datetime.now()
        expiration_time = allocation_time.replace(day=allocation_time.day + days)
    
        # Connect to database
        client, db = get_db_connection()
    
        try:
            # Step 1: Set GPU permission for user
            if set_gpu_permission(username, gpu_id, grant=True):
                logger.debug(f"Set permissions for GPU {gpu_id} for user {username}")
                
                try:
                    # Step 2: Record allocation in MongoDB
                    allocation_id = db.gpu_allocations.insert_one({
                        'username': username,
                        'gpu_type': gpu_type,
                        'gpu_id': gpu_id,
                        'allocated_at': allocation_time,
                        'expiration_time': expiration_time,
                        'released_at': None
                    }).inserted_id
                    
                    logger.info(f"Granted access to GPU {gpu_id} ({gpu_type}) for user {username} until {expiration_time}")
                    return True, allocation_id
                    
                except Exception as e:
                    # Rollback Step 1: Remove permissions if database insert fails
                    logger.error(f"Failed to record allocation in database: {str(e)}")
                    set_gpu_permission(username, gpu_id, grant=False)
                    return False, f"Database error: {str(e)}"
            else:
                return False, "Failed to set GPU permissions"
        except Exception as e:
            logger.error(f"Error during GPU allocation: {str(e)}")
            return False, str(e)
        finally:
            client.close()
    except Exception as e:
        logger.error(f"Unexpected error in allocate_gpu: {str(e)}")
        return False, str(e)

@app.route('/lock_gpu', methods=['POST'])
@login_required
def lock_gpu():
    requested_gpu_dict = {}
    requested_days = {}
    username = session['username']
    
    try:
        # Parse requested GPUs and hours
        for gpu_type in GPU_DICT.keys():
            requested_gpu_dict[gpu_type] = int(request.form.get(f'quantity_{gpu_type}', 0))
            requested_days[gpu_type] = int(request.form.get(f'days_{gpu_type}', 1))
        logger.info(f"User {username} requested GPUs: {requested_gpu_dict} for days: {requested_days}")
    
        # Check availability - no need for GPU_LOCK here as we're just reading
        if not check_if_available(requested_gpu_dict):
            flash('There are not enough GPU resources available to meet your demand.', "error")
            return redirect(url_for('dashboard'))
        
        # Allocate GPUs and track assignments
        allocated_gpus = {}
        successful_allocations = []  # Track successful allocations for rollback
        
        try:
            # Use GPU_LOCK for the entire allocation process
            with GPU_LOCK:
                for gpu_type, count in requested_gpu_dict.items():
                    if count > 0 and requested_days[gpu_type] > 0 and requested_days[gpu_type] <= 7:
                        allocated_gpus[gpu_type] = []
                        for _ in range(count):
                            gpu_id = AVAILABLE_GPUs[gpu_type].pop(0)  # Get first available GPU
                            
                            # Allocate GPU to user - no need for GPU_LOCK here as we're already holding it
                            success, result = allocate_gpu(
                                username, 
                                gpu_type, 
                                gpu_id, 
                                requested_days[gpu_type]
                            )
                            
                            if success:
                                # Track successful allocation for potential rollback
                                successful_allocations.append({
                                    'gpu_type': gpu_type,
                                    'gpu_id': gpu_id,
                                    'allocation_id': result
                                })
                                allocated_gpus[gpu_type].append(gpu_id)
                            else:
                                # Allocation failed, raise exception to trigger rollback
                                raise Exception(f"Failed to allocate GPU {gpu_id}: {result}")
            if allocated_gpus:
                flash(f"Successfully allocated GPUs: {allocated_gpus} with expiration times: {requested_days} days", "success")
            else:
                flash(f"Nothing changed")
            
        except Exception as e:
            # Rollback all successful allocations
            client, db = get_db_connection()
            try:
                with GPU_LOCK:  # Use lock for rollback to prevent race conditions
                    for alloc in successful_allocations:
                        try:
                            # Remove GPU access
                            set_gpu_permission(username, alloc['gpu_id'], grant=False)
                            
                            # Remove database entry
                            db.gpu_allocations.delete_one({'_id': alloc['allocation_id']})
                            
                            # Return GPU to available pool
                            AVAILABLE_GPUs[alloc['gpu_type']].append(alloc['gpu_id'])
                            
                            logger.debug(f"Rolled back allocation for GPU {alloc['gpu_id']}")
                        except Exception as rollback_error:
                            logger.error(f"Error during rollback: {str(rollback_error)}")
            finally:
                client.close()
            
            logger.error(f"Error during GPU allocation: {str(e)}")
            flash("Failed to allocate GPUs. Please try again.", "error")
            return redirect(url_for('dashboard'))
    
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"Unexpected error in lock_gpu: {str(e)}")
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('dashboard'))

def reset_gpu_access():
    reset_gpus = []
    
    try:
        # # Check each GPU in AVAILABLE_GPUs for running processes
        # for gpu_type in GPU_DICT.keys():
        #     for gpu_id in GPU_DICT[gpu_type]:
        #         nvidia_smi = subprocess.run(
        #             ['sudo','nvidia-smi', '--id=' + str(gpu_id), '--query-compute-apps=pid', '--format=csv,noheader'],
        #             capture_output=True, text=True, check=True
        #         )
            
        #         # If there's any output, there's a process running on this GPU
        #         if nvidia_smi.stdout.strip():
        #             logger.debug(f'Active process found on GPU {gpu_id}, skipping permission reset')
        #             return False  # Return empty list if any GPU is busy
        
        # If we get here, all GPUs are free
        #logger.debug('All available GPUs are idle, resetting permissions')
        for gpu_type in GPU_DICT.keys():
            for gpu_id in GPU_DICT[gpu_type]:
                gpu_device = f'/dev/nvidia{gpu_id}'
                try:
                    # Change permissions to 660
                    subprocess.run(['sudo', 'chmod', '660', gpu_device], check=True)
                    logger.debug(f'Reset permissions for GPU {gpu_id} to 660')
                    reset_gpus.append(gpu_id)
                except subprocess.CalledProcessError as e:
                    logger.error(f'Failed to reset permissions for GPU {gpu_id}: {str(e)}')
                    return False
        return True    
    except subprocess.CalledProcessError as e:
        logger.error(f'Error checking GPU processes: {str(e)}')
        return False
    
def reset_user_access():
    """
    Reset GPU access by checking each user's access and removing it only if they
    shouldn't have access (not in active allocation within penalty period or privileged).
    
    Expects:
        PRIVILEGED_USERS in .env as comma-separated usernames
        USER_PENALTY in .env as integer (hours)
    Returns:
        bool: True if all permissions were successfully reset, False otherwise
    """
    try:
        logger.debug('Attempting to reset user-specific GPU access')
        
        # Get penalty period from .env
        penalty_hours = config('USER_PENALTY', default=24, cast=int)
        authorized_users = config('PRIVILEGED_USERS', cast=Csv())
        current_time = datetime.now()
        
        # Connect to MongoDB
        client, db = get_db_connection()
        
        # First, collect all users that should keep access
        users_to_keep = set()  # Using a set to avoid duplicates
        
        # Check each GPU's allocations
        for gpu_type in GPU_DICT.keys():
            for gpu_id in GPU_DICT[gpu_type]:
                # Find active allocation for this GPU
                allocation = db.gpu_allocations.find_one({
                    'gpu_id': gpu_id,
                    'gpu_type': gpu_type,
                    'released_at': None
                })
                
                if allocation:
                    # expiration_with_penalty = allocation['expiration_time'].replace(
                    #     hour=allocation['expiration_time'].hour + penalty_hours
                    # )
                    
                    # if current_time < expiration_with_penalty:
                    users_to_keep.add((allocation['username'], gpu_id))
                    AVAILABLE_GPUs[gpu_type].remove(gpu_id)
                    logger.debug(f"Found active allocation for GPU {gpu_id} ({gpu_type}) for user {allocation['username']}")
                    logger.debug(f"Removing GPU {gpu_id} from available {gpu_type} GPUs")
                    # else:
                    #     # Update the allocation to mark it as released
                    #     update_allocation_status(db, allocation['_id'], released=True)
                    #     logger.info(f"Marked allocation {allocation['_id']} as released due to expiration")
        
        # Add privileged users for all GPUs
        for username in authorized_users:
            try:
                pwd.getpwnam(username)  # Verify user exists
                for gpu_type in GPU_DICT.keys():
                    for gpu_id in GPU_DICT[gpu_type]:
                        users_to_keep.add((username, gpu_id))
            except KeyError:
                logger.warning(f'Privileged user {username} not found in system')
        
        # Check and update access for each GPU
        for gpu_type in GPU_DICT.keys():
            for gpu_id in GPU_DICT[gpu_type]:
                gpu_device = f'/dev/nvidia{gpu_id}'
                try:
                    # Get current ACL entries
                    acl_output = subprocess.run(
                        ['sudo', 'getfacl', gpu_device],
                        capture_output=True,
                        text=True,
                        check=True
                    ).stdout
                    
                    # Parse ACL entries to get current users
                    current_users = []
                    for line in acl_output.splitlines():
                        if line.startswith('user:'):
                            # Format is "user:username:rw-"
                            parts = line.split(':')
                            if len(parts) >= 2 and parts[1]:  # Skip default user entry
                                current_users.append(parts[1])
                    
                    # Remove access for users who shouldn't have it
                    for username in current_users:
                        if (username, gpu_id) not in users_to_keep:
                            # Check if user is actively using the GPU before removing access
                            set_gpu_permission(username, gpu_id, grant=False)
                            logger.debug(f'Removed access to GPU {gpu_id} for user {username}')
                    
                    # Grant access to users who should have it but don't
                    for username, kept_gpu_id in users_to_keep:
                        if kept_gpu_id == gpu_id and username not in current_users:
                            set_gpu_permission(username, gpu_id, grant=True)
                            logger.debug(f'Granted access to GPU {gpu_id} for user {username}')
                
                except subprocess.CalledProcessError as e:
                    logger.error(f'Failed to manage ACL for GPU {gpu_id}: {str(e)}')
                    client.close()
                    return False
        
        logger.info('Successfully reset and configured user-specific GPU access')
        client.close()
        return True
    
    except Exception as e:
        logger.error(f'Unexpected error while resetting user access: {str(e)}')
        if 'client' in locals():
            client.close()
        return False

def on_initial():
    """
    Check if processes are running on GPUs listed in AVAILABLE_GPUS.
    Reset permissions to 660 only if all available GPUs are idle.
    Returns a list of GPUs that were successfully reset.
    """
    states = [False] * 3
    i=0
    states[i]=initialize_gpu_tracking()
    if states[i]:
        states[i+1]=reset_gpu_access()
        i+=1
    if states[i]:
        states[2]=reset_user_access()
        i+=1
    if states[i]:
        return True
    return False
    

def check_if_available(requested_gpu_dict):
    """
    Check if requested GPU resources are available
    Args:
        requested_gpu_dict: Dictionary with gpu_type as key and requested count as value
    Returns:
        bool: True if resources are available, False otherwise
    """
    for gpu_type, requested_count in requested_gpu_dict.items():
        # Check if gpu_type exists in GPU_DICT
        if gpu_type not in GPU_DICT.keys():
            logger.error(f"Requested GPU type {gpu_type} not available")
            return False
            
        # Check if requested count is valid
        if requested_count < 0:
            logger.error(f"Invalid requested count {requested_count} for {gpu_type}")
            return False
            
        # Check if enough GPUs of this type are available
        if len(AVAILABLE_GPUs[gpu_type]) < requested_count:
            logger.error(f"Not enough {gpu_type} GPUs available. Requested: {requested_count}, Available: {len(GPU_DICT[gpu_type])}")
            return False
    
    logger.debug("Requested GPU resources are available")
    return True

@app.route('/release_gpu', methods=['POST'])
@login_required
def release_gpu():
    username = session['username']
    allocation_id = request.form.get('allocation_id')
    authorized_users = config('PRIVILEGED_USERS', cast=Csv())
    if username in authorized_users:
        is_admin=True 
    else:
        is_admin=False
    
    try:
        client, db = get_db_connection()
        
        # Find the allocation - if admin, don't check username
        query = {'_id': ObjectId(allocation_id), 'released_at': None}
        if not is_admin:
            # Regular users can only release their own GPUs
            query['username'] = username
            
        allocation = db.gpu_allocations.find_one(query)
        
        if not allocation:
            flash('Invalid GPU allocation or unauthorized access', 'error')
            return redirect(url_for('dashboard'))
        
        gpu_type = allocation['gpu_type']
        gpu_id = allocation['gpu_id']
        user_username = allocation['username']  # The actual owner of the GPU
        
        # Use the common unallocate function
        if unallocate_gpu(user_username, gpu_id, gpu_type, allocation_id, db):
            if is_admin and username != user_username:
                flash(f'Successfully released GPU {gpu_id} from user {user_username}', 'success')
                logger.info(f"Admin {username} released GPU {gpu_id} from user {user_username}")
            else:
                flash(f'Successfully released GPU {gpu_id}', 'success')
        else:
            flash('Failed to release GPU', 'error')
                
    except Exception as e:
        logger.error(f"Error in release_gpu route: {str(e)}")
        flash('Failed to release GPU', 'error')
    finally:
        if 'client' in locals():
            client.close()
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/schedule')
@login_required
def schedule():
    try:
        with MongoDBConnection() as (client, db):
            # Query for all active allocations
            allocations = list(db.gpu_allocations.find({
                'released_at': None
            }).sort('expiration_time', pymongo.ASCENDING))  # Sort by expiration time
            
            # Format dates for display
            allocations = format_allocations_for_display(allocations)
            
    except Exception as e:
        logger.error(f"Error fetching schedule: {str(e)}")
        allocations = []
    
    return render_template('schedule.html', allocations=allocations)


def check_expired_reservations():
    logger.info("Running scheduled check for expired reservations")
    try:
        client, db = get_db_connection()
        current_time = datetime.now()
        penalty_hours = config('USER_PENALTY', default=24, cast=int)
        
        # Find all active allocations
        active_allocations = list(db.gpu_allocations.find({'released_at': None}))
        logger.info(f"Found {len(active_allocations)} active allocations to check")
        
        # Filter allocations where expiration_time + penalty < current_time
        allocations_to_check = []
        for allocation in active_allocations:
            expiration_time = allocation['expiration_time']
            expiration_with_penalty = expiration_time.replace(hour=expiration_time.hour + penalty_hours)
            if current_time > expiration_with_penalty:
                logger.debug(f"Allocation {allocation['_id']} has expired (expiration: {expiration_time}, with penalty: {expiration_with_penalty})")
                allocations_to_check.append(allocation)
                
        logger.info(f"Found {len(allocations_to_check)} allocations within penalty period to check for GPU usage")
        
        for allocation in allocations_to_check:
            username = allocation['username']
            gpu_id = allocation['gpu_id']
            gpu_type = allocation['gpu_type']
            allocation_id = allocation['_id']
            
            logger.debug(f"Checking allocation {allocation_id}: GPU {gpu_id} ({gpu_type}) for user {username}")
            
            # Check if the user is actually using the GPU
            if not is_user_using_gpu(username, gpu_id):
                logger.info(f"User {username} is not using allocated GPU {gpu_id}. Releasing allocation {allocation_id}.")
                
                # Use the common unallocate function
                unallocate_gpu(username, gpu_id, gpu_type, allocation_id, db)
            else:
                logger.debug(f"User {username} is actively using GPU {gpu_id}, skipping release")
        
        logger.info("Completed checking all active allocations")
        
    except Exception as e:
        logger.error(f"Error in check_expired_reservations: {str(e)}")
    finally:
        if 'client' in locals():
            client.close()

def threaded_function():
    import time
    check_expired_reservations()
    while True:
        sched_module.run_pending()
        time.sleep(30)

def unallocate_gpu(username, gpu_id, gpu_type, allocation_id, db):
    """Release a GPU allocation with proper cleanup of permissions and database
    
    Args:
        username: Username that currently has the GPU allocated
        gpu_id: ID of the GPU to release
        gpu_type: Type of the GPU being released
        allocation_id: Database ID of the allocation
        db: MongoDB database connection
        
    Returns:
        bool: Success status
    """
    try:
        logger.debug(f"Releasing GPU {gpu_id} ({gpu_type}) from user {username}")
        
        # First, terminate any processes the user has running on this GPU
        try:
            # Get all processes running on this GPU
            nvidia_smi = subprocess.run(
                ['sudo', 'nvidia-smi', '--id=' + str(gpu_id), '--query-compute-apps=pid', '--format=csv,noheader'],
                capture_output=True, text=True, check=True
            )
            
            # For each process, check if it belongs to the user and kill it if so
            for line in nvidia_smi.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                
                pid = line.strip()
                try:
                    process_owner = subprocess.run(
                        ['ps', '-o', 'user=', '-p', pid],
                        capture_output=True, text=True, check=True
                    ).stdout.strip()
                    
                    if process_owner == username:
                        logger.info(f"Terminating process {pid} owned by {username} on GPU {gpu_id}")
                        subprocess.run(['sudo', 'kill', '-9', pid], check=True)
                except subprocess.CalledProcessError:
                    continue
            
            logger.debug(f"Terminated all processes for user {username} on GPU {gpu_id}")
        except Exception as e:
            logger.error(f"Error terminating processes on GPU {gpu_id}: {str(e)}")
            # Continue with release even if process termination fails
        
        with GPU_LOCK:
            # Step 1: Add GPU back to available pool
            AVAILABLE_GPUs[gpu_type].append(gpu_id)
            logger.debug(f"Added GPU {gpu_id} back to available pool")
            
            try:
                # Step 2: Mark allocation as released in database
                if update_allocation_status(db, allocation_id, released=True):
                    logger.debug(f"Updated allocation {allocation_id} status to released")
                    
                    try:
                        # Step 3: Remove user's access to the GPU
                        if set_gpu_permission(username, gpu_id, grant=False):
                            logger.info(f"Successfully released GPU {gpu_id} from user {username}")
                            return True
                        else:
                            raise Exception(f"Failed to remove permissions for GPU {gpu_id}")
                        
                    except Exception as e:
                        # Rollback Step 2: Revert the database update
                        logger.error(f"Failed to remove permissions for GPU {gpu_id}: {str(e)}")
                        update_allocation_status(db, allocation_id, released=False)
                        # Rollback Step 1: Remove GPU from available pool
                        AVAILABLE_GPUs[gpu_type].remove(gpu_id)
                        logger.error(f"Rolled back allocation release due to permission error")
                        return False
                else:
                    raise Exception(f"Failed to update allocation status in database")
                    
            except Exception as e:
                # Rollback Step 1: Remove GPU from available pool
                AVAILABLE_GPUs[gpu_type].remove(gpu_id)
                logger.error(f"Error updating database for GPU {gpu_id}: {str(e)}")
                return False
                
    except Exception as e:
        logger.error(f"Unexpected error releasing GPU {gpu_id}: {str(e)}")
        return False

def get_user_disk_usage(username):
    """Get disk usage for a user with caching
    
    Args:
        username: Username to get disk usage for
        
    Returns:
        tuple: (used_space_bytes, used_by_others_bytes, total_space_bytes)
    """
    current_time = datetime.now()
    
    # Check if we have a valid cached value
    if username in DISK_USAGE_CACHE:
        cache_time, disk_data = DISK_USAGE_CACHE[username]
        if (current_time - cache_time).total_seconds() < DISK_CACHE_TIMEOUT:
            logger.debug(f"Using cached disk usage for user {username}")
            return disk_data
    
    # No valid cache, calculate disk usage
    try:
        logger.debug(f"Calculating disk usage for user {username}")
        user_info = pwd.getpwnam(username)
        home_dir = user_info.pw_dir
        
        # Get total disk usage for the filesystem
        total, used_total, free = shutil.disk_usage(home_dir)
        
        # Get user's specific usage by running du command
        du_process = subprocess.run(
            ['sudo', 'du', '-sb', home_dir],
            capture_output=True, text=True, check=True
        )
        user_used = int(du_process.stdout.split()[0])
        
        # Calculate space used by others
        used_by_others = used_total - user_used
        
        # Cache the result
        disk_data = (user_used, used_by_others, total)
        DISK_USAGE_CACHE[username] = (current_time, disk_data)
        
        return disk_data
    except Exception as e:
        logger.error(f"Error getting disk usage for user {username}: {str(e)}")
        return (0, 0, 0)  # Return zeros on error

def format_size(size_bytes):
    """Format bytes to human-readable size
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        str: Formatted size string
    """
    if size_bytes == 0:
        return "0B"
    
    size_names = ("B", "KB", "MB", "GB", "TB", "PB")
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"

def clear_disk_usage_cache():
    """Clear the disk usage cache periodically"""
    logger.debug("Clearing disk usage cache")
    DISK_USAGE_CACHE.clear()

@app.route('/reset', methods=['GET', 'POST'])
@login_required
def reset_all():
    username = session['username']
    authorized_users = config('PRIVILEGED_USERS', cast=Csv())
    # Check if the user is admin
    if username not in authorized_users:
        logger.warning(f"Unauthorized reset attempt by user {username}")
        flash('You are not authorized to perform this action', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        logger.info(f"Admin user {username} requested full system reset")
        
        # Connect to database
        client, db = get_db_connection()
        
        # Step 1: Get all active allocations
        active_allocations = list(db.gpu_allocations.find({'released_at': None}))
        logger.info(f"Found {len(active_allocations)} active allocations to reset")
        for gpu_type in GPU_DICT.keys():
            for gpu_id in GPU_DICT[gpu_type]:
                gpu_device = f'/dev/nvidia{gpu_id}'
                try:
                    # Change permissions to 666
                    subprocess.run(['sudo', 'chmod', '666', gpu_device], check=True)
                    logger.debug(f'Reset permissions for GPU {gpu_id} to 666')
                except subprocess.CalledProcessError as e:
                    logger.error(f'Failed to reset permissions for GPU {gpu_id}: {str(e)}')
        # Step 2: Revoke all GPU access and mark allocations as released
        for allocation in active_allocations:
            alloc_username = allocation['username']
            gpu_id = allocation['gpu_id']
            gpu_type = allocation['gpu_type']
            allocation_id = allocation['_id']
            
            # Remove user's access to the GPU
            set_gpu_permission(alloc_username, gpu_id, grant=False)
            
            # Mark allocation as released in database
            update_allocation_status(db, allocation_id, released=True)
            
            logger.debug(f"Revoked access to GPU {gpu_id} for user {alloc_username}")
        
        # Step 3: Reset all GPU permissions to 666
        
        
        # Step 4: Reinitialize GPU tracking
        initialize_gpu_tracking()
        
        flash('Successfully reset all GPU permissions and allocations', 'success')
        logger.info(f"Admin user {username} successfully reset all GPU permissions and allocations")
        
    except Exception as e:
        logger.error(f"Error during system reset: {str(e)}")
        flash('Failed to reset system', 'error')
    finally:
        if 'client' in locals():
            client.close()
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    logger.info('Starting GPULocker application')
    import threading
    try:
        mongo_client = setup_database()  # Store the client connection
        initiated = on_initial()
        if not initiated:
                logger.error("Error while resetting permissions ... exiting")
                mongo_client.close()  # Close MongoDB connection
                exit(1)
        sched_module.every(config('CHECK_FOR_IDLE_GPU',default=6,cast=int)).hours.do(check_expired_reservations)
        # Add scheduled task to clear disk usage cache
        sched_module.every(DISK_CACHE_TIMEOUT).seconds.do(clear_disk_usage_cache)
        thread = threading.Thread(target=threaded_function)
        thread.start()
        app.run(
            host=config('HOST', default='0.0.0.0'),
            port=config('PORT', default=5151, cast=int),
            ssl_context='adhoc'
        )
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        exit(1)