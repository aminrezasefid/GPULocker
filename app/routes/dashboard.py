from flask import Blueprint,render_template, request, session, redirect, url_for, flash
from decouple import config,Csv
from app.utils.logger import logger
import jdatetime
import pymongo
from app.utils.gpu_monitoring import get_gpu_status,unallocate_gpu,get_gpu_config,set_available_gpus,set_gpu_permission,allocate_gpu
from app.utils.db import *
from app.utils.redis_utils import DistributedLock
from app.config import REDIS_CLIENT,REDIS_KEYS,DISK_CACHE_TIMEOUT
from app.utils.disk import get_disk_cache,get_user_disk_usage,set_disk_cache
from app.routes.auth import login_required
import json

from app.utils.gpu_monitoring import get_available_gpus
from app.utils.notification import get_unread_notifications_count
dashboard_bp = Blueprint('dashboard', __name__,static_url_path="dashboard")
@dashboard_bp.route('/')
def index():
    """Root route that redirects to the login page"""
    return redirect(url_for('auth.login'))
@dashboard_bp.route('/schedule')
@login_required
def schedule():
    try:
        with MongoDBConnection() as (client, db):
            # Query for all active allocations
            allocations = list(db.gpu_allocations.find({
                'released_at': None
            }).sort('expiration_time', pymongo.ASCENDING))  # Sort by expiration time
            
            # Format dates for display
            formatted_allocations = format_allocations_for_display(allocations)
            
    except Exception as e:
        logger.error(f"Error fetching schedule: {str(e)}")
        formatted_allocations = []
    
    # Get initial GPU status for first page load
    gpu_status = get_gpu_status()
    
    # Get refresh rate from .env
    refresh_rate = config('GPUs_STATUS_REFRESH_RATE_SECONDS', default=5, cast=float)
    refresh_rate_ms = int(refresh_rate * 1000)  # Convert to milliseconds
    
    # Get unread notifications count
    unread_count = get_unread_notifications_count(session['username'])
    
    return render_template('schedule.html', 
                          allocations=formatted_allocations,
                          gpu_status=gpu_status,
                          refresh_rate_ms=refresh_rate_ms,
                          unread_notifications_count=unread_count)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    username = session["username"]
    
    try:
        with MongoDBConnection() as (client, db):
            # Query for active allocations (where released_at is None)
            allocations = list(db.gpu_allocations.find({
                'username': username,
                'released_at': None
            }))
            
            # For admin users, get all active allocations
            all_allocations = []
            authorized_users = config('PRIVILEGED_USERS', cast=Csv())
            is_admin = username in authorized_users
            
            if is_admin:
                all_allocations = list(db.gpu_allocations.find({
                    'released_at': None
                }))
                all_allocations = format_allocations_for_display(all_allocations)
            
            # Format dates for display
            allocations = format_allocations_for_display(allocations)
            
            # Get available GPUs from Redis
            available_gpus = get_available_gpus()
            
            # Get user's disk usage from Redis cache
            disk_usage_data = get_disk_cache(username)
            if disk_usage_data is None:
                # Cache miss - calculate and cache
                used_bytes, used_by_others_bytes, total_bytes = get_user_disk_usage(username)
                disk_usage_data = {
                    'used': format_size(used_bytes),
                    'used_by_others': format_size(used_by_others_bytes),
                    'free': format_size(total_bytes - used_bytes - used_by_others_bytes),
                    'total': format_size(total_bytes),
                    'percent_used': round((used_bytes / total_bytes) * 100, 2) if total_bytes > 0 else 0,
                    'percent_others': round((used_by_others_bytes / total_bytes) * 100, 2) if total_bytes > 0 else 0,
                    'percent_free': round(((total_bytes - used_bytes - used_by_others_bytes) / total_bytes) * 100, 2) if total_bytes > 0 else 0
                }
                # Cache the result
                set_disk_cache(username, disk_usage_data, timeout=DISK_CACHE_TIMEOUT)
            
            # Get unread notifications count
            unread_count = get_unread_notifications_count(username)
            
            # Get GPU status from Redis or calculate
            gpu_status_key = REDIS_KEYS['gpu_status']
            gpu_status = REDIS_CLIENT.get(gpu_status_key)
            if gpu_status:
                gpu_status = json.loads(gpu_status)
            else:
                gpu_status = get_gpu_status()
                # Cache GPU status for a short time (e.g., 5 seconds)
                REDIS_CLIENT.setex(gpu_status_key, 5, json.dumps(gpu_status))
            
            return render_template('dashboard.html',
                                gpu_dict=available_gpus,
                                allocations=allocations,
                                all_allocations=all_allocations,
                                is_admin=is_admin,
                                disk_usage=disk_usage_data,
                                unread_notifications_count=unread_count,
                                gpu_status=gpu_status)
            
    except Exception as e:
        logger.error(f"Error in dashboard route: {str(e)}")
        flash("An error occurred while loading the dashboard", "error")
        return redirect(url_for('auth.login'))

@dashboard_bp.route('/release_gpu', methods=['POST'])
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
            return redirect(url_for('dashboard.dashboard'))
        
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
    
    return redirect(url_for('dashboard.dashboard'))
@dashboard_bp.route('/lock_gpu', methods=['POST'])
@login_required
def lock_gpu():
    requested_gpu_dict = {}
    requested_days = {}
    username = session['username']
    
    try:
        # Get GPU configuration from Redis
        gpu_config = get_gpu_config()
        if not gpu_config:
            logger.error("Could not retrieve GPU configuration")
            flash("System configuration error", "error")
            return redirect(url_for('dashboard.dashboard'))
        
        # Parse requested GPUs and days
        for gpu_type in gpu_config.keys():
            try:
                quantity = request.form.get(f'quantity_{gpu_type}', '0')
                days = request.form.get(f'days_{gpu_type}', '0')
                
                # Validate input
                if not quantity.isdigit() or not days.isdigit():
                    flash("Invalid input values", "error")
                    return redirect(url_for('dashboard.dashboard'))
                
                requested_gpu_dict[gpu_type] = int(quantity)
                requested_days[gpu_type] = int(days)
                
                # Validate days range
                if requested_days[gpu_type] <= 0 or requested_days[gpu_type] > 7:
                    flash("Number of days must be between 1 and 7", "error")
                    return redirect(url_for('dashboard.dashboard'))
                
            except ValueError as e:
                logger.error(f"Invalid form data: {str(e)}")
                flash("Invalid input values", "error")
                return redirect(url_for('dashboard.dashboard'))
        
        logger.info(f"User {username} requested GPUs: {requested_gpu_dict} for days: {requested_days}")
        
        # Use distributed lock for the entire allocation process
        with DistributedLock(REDIS_KEYS['gpu_lock']):
            # Get current available GPUs from Redis
            available_gpus = get_available_gpus()
            if not available_gpus:
                flash("No GPUs available at the moment", "error")
                return redirect(url_for('dashboard.dashboard'))
            
            # Validate against GPU configuration
            for gpu_type, count in requested_gpu_dict.items():
                if count > 0:
                    # Check if GPU type exists
                    if gpu_type not in gpu_config:
                        flash(f"Invalid GPU type: {gpu_type}", "error")
                        return redirect(url_for('dashboard.dashboard'))
                    
                    # Check if enough GPUs are available
                    if gpu_type not in available_gpus or len(available_gpus[gpu_type]) < count:
                        flash(f"Not enough {gpu_type} GPUs available", "error")
                        return redirect(url_for('dashboard.dashboard'))
            
            # Track successful allocations for rollback
            successful_allocations = []
            allocated_gpus = {}
            
            try:
                with MongoDBConnection() as (client, db):
                    # Perform allocations
                    for gpu_type, count in requested_gpu_dict.items():
                        if count > 0:
                            allocated_gpus[gpu_type] = []
                            
                            for _ in range(count):
                                if not available_gpus[gpu_type]:
                                    raise Exception(f"No more {gpu_type} GPUs available")
                                
                                gpu_id = available_gpus[gpu_type].pop(0)
                                
                                # Verify GPU ID is valid according to configuration
                                if gpu_id not in gpu_config[gpu_type]:
                                    raise Exception(f"Invalid GPU ID {gpu_id} for type {gpu_type}")
                                
                                # Allocate GPU to user
                                success, result = allocate_gpu(
                                    username,
                                    gpu_type,
                                    gpu_id,
                                    requested_days[gpu_type]
                                )
                                
                                if success:
                                    successful_allocations.append({
                                        'gpu_type': gpu_type,
                                        'gpu_id': gpu_id,
                                        'allocation_id': result
                                    })
                                    allocated_gpus[gpu_type].append(gpu_id)
                                else:
                                    # Put GPU back in available pool
                                    available_gpus[gpu_type].append(gpu_id)
                                    raise Exception(f"Failed to allocate GPU {gpu_id}: {result}")
                    
                    # Update available GPUs in Redis
                    set_available_gpus(available_gpus)
                    
                    if allocated_gpus:
                        flash(f"Successfully allocated GPUs: {allocated_gpus} with expiration times: {requested_days} days", "success")
                    else:
                        flash("No GPUs were allocated", "info")
                    
                    return redirect(url_for('dashboard.dashboard'))
                    
            except Exception as e:
                # Rollback all successful allocations
                logger.error(f"Error during GPU allocation: {str(e)}")
                
                with MongoDBConnection() as (client, db):
                    for alloc in successful_allocations:
                        try:
                            # Remove GPU access
                            set_gpu_permission(username, alloc['gpu_id'], grant=False)
                            
                            # Remove database entry
                            db.gpu_allocations.delete_one({'_id': alloc['allocation_id']})
                            
                            # Return GPU to available pool
                            available_gpus[alloc['gpu_type']].append(alloc['gpu_id'])
                            
                            logger.debug(f"Rolled back allocation for GPU {alloc['gpu_id']}")
                        except Exception as rollback_error:
                            logger.error(f"Error during rollback: {str(rollback_error)}")
                    
                    # Update available GPUs in Redis after rollback
                    set_available_gpus(available_gpus)
                
                flash(f"Failed to allocate GPUs: {str(e)}", "error")
                return redirect(url_for('dashboard.dashboard'))
                
    except Exception as e:
        logger.error(f"Unexpected error in lock_gpu: {str(e)}")
        flash("An unexpected error occurred", "error")
        return redirect(url_for('dashboard.dashboard'))
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