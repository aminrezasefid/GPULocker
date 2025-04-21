from app.config import REDIS_BINARY,REDIS_KEYS,DISK_CACHE_TIMEOUT
import pwd
import shutil
import subprocess
from app.utils.logger import logger
import pickle
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
def update_user_disk_cache(username):
    used, others, total = get_user_disk_usage(username)
    try:
        data = {
            'used': format_size(used),
            'used_by_others': format_size(others),
            'free': format_size(total - used - others),
            'total': format_size(total),
            'percent_used': round((used / total) * 100, 2) if total > 0 else 0,
            'percent_others': round((others / total) * 100, 2) if total > 0 else 0,
            'percent_free': round(((total - used - others) / total) * 100, 2) if total > 0 else 0
        }
        set_disk_cache(username, data)
        logger.info(f"Disk usage cache updated for {username}")
    except Exception as e:
        logger.error(f"Failed to update disk usage cache for {username}: {e}")


def get_user_disk_usage(username):
    """Get disk usage for a user with Redis caching
    
    Args:
        username: Username to get disk usage for
        
    Returns:
        tuple: (used_space_bytes, used_by_others_bytes, total_space_bytes)
    """
    try:
        # Try to get cached data from Redis
        cache_key = f"{REDIS_KEYS['disk_cache']}:{username}"
        cached_data = REDIS_BINARY.get(cache_key)
        
        if cached_data:
            try:
                # Cached data exists, return it
                return pickle.loads(cached_data)
            except pickle.UnpicklingError as e:
                logger.error(f"Error unpickling disk usage cache for {username}: {str(e)}")
                # Continue to recalculate if unpickling fails
        
        # No valid cache, calculate disk usage
        logger.debug(f"Calculating disk usage for user {username}")
        
        try:
            user_info = pwd.getpwnam(username)
            home_dir = user_info.pw_dir
            
            # Get total disk usage for the filesystem
            total, used_total, free = shutil.disk_usage(home_dir)
            
            # Get user's specific usage by running du command
            du_process = subprocess.run(
                ['sudo', 'du', '-sb', home_dir],
                capture_output=True, text=True,
            )
            try:
                user_used = int(du_process.stdout.split()[0])
            except Exception as e:
                logger.error(f"Error calculating disk usage for {username}: {str(e)}")
                return (0, 0, 0)
            
            # Calculate space used by others
            used_by_others = used_total - user_used
            
            # Create tuple of results
            disk_data = (user_used, used_by_others, total)
            
            try:
                # Cache the result in Redis with timeout
                REDIS_BINARY.setex(
                    cache_key,
                    DISK_CACHE_TIMEOUT,  # Use the existing timeout value
                    pickle.dumps(disk_data)
                )
                logger.debug(f"Cached disk usage for user {username}")
            except Exception as cache_error:
                logger.error(f"Error caching disk usage for {username}: {str(cache_error)}")
                # Continue even if caching fails
            
            return disk_data
            
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.error(f"Error calculating disk usage for {username}: {str(e)}")
            return (0, 0, 0)
            
    except Exception as e:
        logger.error(f"Unexpected error in get_user_disk_usage for {username}: {str(e)}")
        return (0, 0, 0)
    
def get_disk_cache(username):
    """Get disk usage cache from Redis"""
    cache_data = REDIS_BINARY.get(f"{REDIS_KEYS['disk_cache']}:{username}")
    if cache_data:
        return pickle.loads(cache_data)
    return None

def set_disk_cache(username, data, timeout=600):
    """Set disk usage cache in Redis"""
    REDIS_BINARY.setex(
        f"{REDIS_KEYS['disk_cache']}:{username}",
        timeout,
        pickle.dumps(data)
    )
