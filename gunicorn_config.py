import multiprocessing
import os
import logging
from app import on_initial,setup_database
import signal
import sys

# Number of worker processes
workers = 5

# Worker class
worker_class = 'sync'

# Bind address
bind = '0.0.0.0:5151'

# SSL configuration
certfile = 'cert.pem'
keyfile = 'key.pem'

# Timeout configuration
timeout = 120
keepalive = 10

# Log configuration
logfile = 'gunicorn.log'
accesslog = logfile
errorlog = logfile
loglevel = 'error'

# Configure logger
logger = logging.getLogger('gunicorn.error')

def on_starting(server):
    """Called just before the master process is initialized"""
    try:
        mongo_client = setup_database()  # Store the client connection
        if not on_initial():
            logger.error("Error while initializing system ... exiting")
            mongo_client.close()  # Close MongoDB connection
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        sys.exit(1)

def worker_int(worker):
    """Called when a worker exits abruptly"""
    worker_id = os.getenv('GUNICORN_WORKER_ID', '0')
    logger.info(f"Worker {worker_id} exiting")

def worker_abort(worker):
    print(f"Worker {worker.pid} timeout, killing it.")
    os.kill(worker.pid, signal.SIGKILL)

def post_fork(server, worker):
    """Called just after a worker has been forked"""
    # Set unique worker ID
    worker_id = str(worker.pid)
    os.environ['GUNICORN_WORKER_ID'] = worker_id

def when_ready(server):
    """Called just after the server is started"""
    pass
        