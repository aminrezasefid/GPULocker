from flask import Flask
from decouple import config
import logging
from logging.handlers import RotatingFileHandler
import os
from tg_bot.bot import build_bot
import threading
from redis.lock import Lock as RedisLock
import schedule as sched_module
from app.routes import init_routes
from app.utils.db import setup_database
from app.utils.gpu_monitoring import initialize_gpu_config, initialize_gpu_tracking,reset_user_access,reset_gpu_access,check_allocation_utilization,check_and_revoke_idle_allocation
from app.utils.gpu_monitoring  import restore_monitoring_jobs,check_expired_reservations
from app.config import REDIS_CLIENT, REDIS_BINARY, REDIS_KEYS
from app.utils.logger import logger
from decouple import config
import json
import pickle
def threaded_function():
    import time
    try:
        check_expired_reservations()
        while True:
            try:
                process_scheduler_job_queue()
                process_scheduler_cancel_job_queue()
                sched_module.run_pending()
                time.sleep(30)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
                time.sleep(30)
    except Exception as e:
        logger.error(f"Fatal error in threaded_function: {str(e)}")

def process_scheduler_job_queue():
    """Process any new jobs in the scheduler queue"""
    # Use a pipeline to make operations atomic
    pipe = REDIS_BINARY.pipeline()
    pipe.lrange(REDIS_KEYS['scheduler_job_queue'], 0, -1)
    pipe.delete(REDIS_KEYS['scheduler_job_queue'])
    results = pipe.execute()
    
    jobs = results[0]  # Jobs from lrange
    
    if jobs:
        for job_data in jobs:
            try:
                # Use pickle.loads to deserialize the data
                job = pickle.loads(job_data)
                
                job_unit = job.get('job_unit')
                job_interval = job.get('job_interval')
                job_function = job.get('job_function')
                job_input = job.get('job_input')
                
                # Make sure job_input has _id before accessing it
                if job_input and '_id' in job_input:
                    id = job_input.get('_id')
                    
                    if job_unit == 'hours':
                        job = sched_module.every(job_interval).hours.do(globals()[job_function], job_input).tag(f"{id}:{job_function}")
                    elif job_unit == 'minutes':
                        job = sched_module.every(job_interval).minutes.do(globals()[job_function], job_input).tag(f"{id}:{job_function}")
                    elif job_unit == 'seconds':
                        job = sched_module.every(job_interval).seconds.do(globals()[job_function], job_input).tag(f"{id}:{job_function}")
                    
                    logger.info(f"Added interval job: {job_function} every {job_interval} {job_unit}")
                    #REDIS_BINARY.rpush(f"scheduled_job:{id}:{job_function}", pickle.dumps(job))
                else:
                    logger.error(f"Job input missing _id field: {job_input}")
            except Exception as e:
                logger.error(f"Error processing scheduler job: {str(e)}")

def process_scheduler_cancel_job_queue():
    """Process any jobs that need to be cancelled from the scheduler"""
    # Use a pipeline to make operations atomic
    pipe = REDIS_BINARY.pipeline()
    pipe.lrange(REDIS_KEYS['scheduler_cancel_job_queue'], 0, -1)
    pipe.delete(REDIS_KEYS['scheduler_cancel_job_queue'])
    results = pipe.execute()
    
    cancel_requests = results[0]  # Cancellation requests from lrange
    
    if cancel_requests:
        for request_data in cancel_requests:
            try:
                # Use pickle.loads to deserialize the data
                request = pickle.loads(request_data)
                
                job_function = request.get('job_function')
                id = request.get('id')
                
                # Initialize cancelled flag
                cancelled = False
                
                # Get job from Redis
                #job_data = REDIS_BINARY.rpop(f"scheduled_job:{id}:{job_function}")
                sched_module.clear(f"{id}:{job_function}")
                cancelled = True
                logger.info(f"Cancelled scheduled job: {job_function} with id {id}")
                
                if not cancelled:
                    logger.warning(f"No matching job found to cancel: {job_function} with id {id}")
                    
            except Exception as e:
                logger.error(f"Error processing scheduler job cancellation: {str(e)}")

class APIStatusFilter(logging.Filter):
    def filter(self, record):
        # Check if this is a log for /api/gpu_status with 200 status
        if ' 200 ' in record.getMessage() and '/api/gpu_status' in record.getMessage():
            return False  # Don't log this record
        return True  # Log all other records

# Apply the filter to werkzeug logger
logging.getLogger('werkzeug').addFilter(APIStatusFilter())

def on_initial():
    """Initialize system state - should only be called by master worker"""
    logger.info(f'Starting GPULocker application - worker_id: {os.environ.get("GUNICORN_WORKER_ID")}')
    #bot = build_bot()
    #bot.send_message(chat_id=config("TELEGRAM_BOT_ADMIN_ID"), text="GPULocker application started")
    try:
        init_lock = RedisLock(
            REDIS_CLIENT,
            REDIS_KEYS['init_lock'],
            timeout=60
        )
        
        if not init_lock.acquire(blocking=False):
            logger.info("Another worker is handling initialization")
            return True
            
        try:
            logger.info("Master worker performing system initialization")
            
            # Initialize GPU configuration first
            if not initialize_gpu_config():
                logger.error("Error initializing GPU configuration")
                return False
            
            # Initialize GPU tracking
            if not initialize_gpu_tracking():
                logger.error("Error initializing GPU tracking")
                return False
            
            # Reset GPU permissions
            if not reset_gpu_access():
                logger.error("Error resetting GPU permissions")
                return False
                
            # Reset user access
            if not reset_user_access():
                logger.error("Error resetting user access")
                return False
            restore_monitoring_jobs()
            # Set up scheduled tasks
            sched_module.every(config('CHECK_FOR_IDLE_GPU_HOURS',default=6,cast=int)).hours.do(check_expired_reservations)
            
            # Start the scheduler thread
            thread = threading.Thread(target=threaded_function)
            thread.daemon = True  # Make thread daemon so it exits when main process exits
            thread.start()
                
            # Set initialization flag in Redis
            REDIS_CLIENT.set(REDIS_KEYS['system_initialized'], '1')
            logger.info("System initialization completed successfully")
            return True
            
        finally:
            # Release the initialization lock
            init_lock.release()
            
    except Exception as e:
        logger.error(f"Error during system initialization: {str(e)}")
        return False
    
def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    app.secret_key = config('SECRET_KEY')
    init_routes(app)
    return app