from flask import Blueprint, session, redirect, url_for, flash
import subprocess
import os
from decouple import config,Csv
from app.utils.logger import logger
from app.routes.auth import login_required
from app.utils.notification import *
from app.utils.db import *
from app.utils.gpu_monitoring import set_gpu_permission,get_gpu_config,initialize_gpu_tracking
from app.utils.gpu_monitoring import cancel_allocation_monitoring
admin_bp = Blueprint('admin', __name__)
@admin_bp.route('/reset', methods=['GET', 'POST'])
@login_required
def reset_all():
    username = session['username']
    authorized_users = config('PRIVILEGED_USERS', cast=Csv())
    # Check if the user is admin
    if username not in authorized_users:
        logger.warning(f"Unauthorized reset attempt by user {username}")
        flash('You are not authorized to perform this action', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    try:
        logger.info(f"Admin user {username} requested full system reset")
        
        # Connect to database
        client, db = get_db_connection()
        
        # Step 1: Get all active allocations
        active_allocations = list(db.gpu_allocations.find({'released_at': None}))
        logger.info(f"Found {len(active_allocations)} active allocations to reset")
        
        # Cancel all monitoring jobs
        for allocation in active_allocations:
            cancel_allocation_monitoring(str(allocation['_id']))
        
        # Step 2: Revoke all GPU access and mark allocations as released
        for allocation in active_allocations:
            alloc_username = allocation['username']
            gpu_id = allocation['gpu_id']
            gpu_type = allocation['gpu_type']
            allocation_id = allocation['_id']
            
            # Remove user's access to the GPU
            set_gpu_permission(alloc_username, gpu_id, grant=False)
            
            # Mark allocation as released in database with a comment
            comment = f"Released during system reset by admin {username}"
            update_allocation_status(db, allocation_id, released=True, comment=comment)
            
            logger.debug(f"Revoked access to GPU {gpu_id} for user {alloc_username}")
        
        # Step 3: Reset all GPU permissions using reset_gpus.sh script
        # Collect all GPU IDs to pass to the script
        all_gpu_ids = []
        gpu_dict=get_gpu_config()
        for gpu_type in gpu_dict.keys():
            for gpu_id in gpu_dict[gpu_type]:
                all_gpu_ids.append(str(gpu_id))
        
        # Call the reset_gpus.sh script with all GPU IDs as arguments and suppress output
        if all_gpu_ids:
            try:
                # Construct the command with all GPU IDs as arguments and suppress output
                script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'reset_gpus.sh')
                cmd = ['sudo', script_path] + all_gpu_ids
                subprocess.run(cmd, check=True, 
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                                 )
                logger.info(f'Reset permissions for GPUs {all_gpu_ids} using reset_gpus.sh')
            except subprocess.CalledProcessError as e:
                logger.error(f'Failed to reset permissions using reset_gpus.sh: {str(e)}')
        
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
    
    return redirect(url_for('dashboard.dashboard'))