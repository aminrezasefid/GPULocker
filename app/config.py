from decouple import config, Csv
import redis
from rq import Queue
from app.utils.logger import logger
DISK_CACHE_TIMEOUT = config("DISK_CACHE_TIMEOUT_SECONDS",10,cast=int)   # 10 minutes in seconds

# Redis connection configuration
REDIS_CLIENT = redis.Redis(
    host=config('REDIS_HOST', default='localhost'),
    port=config('REDIS_PORT', default=6379, cast=int),
    db=config('REDIS_DB', default=0),
    decode_responses=True  # For normal strings
)

# Binary Redis client for pickle data
REDIS_BINARY = redis.Redis(
    host=config('REDIS_HOST', default='localhost'),
    port=config('REDIS_PORT', default=6379, cast=int),
    db=config('REDIS_DB', default=0),
    decode_responses=False  # For binary data
)


def enqueue_job(job_name,*args,**kwargs):
    logger.info(f"Enqueuing job {job_name} with args {args} and kwargs {kwargs}")
    redis_conn = REDIS_BINARY
    q = Queue(connection=redis_conn)
    q.enqueue(job_name,*args,**kwargs)

# Redis keys
REDIS_KEYS = {
    'scheduler_job_queue': 'gpulocker:scheduler_job_queue',
    'scheduler_cancel_job_queue': 'gpulocker:scheduler_cancel_job_queue',
    'gpu_lock': 'gpulocker:gpu_lock',
    'available_gpus': 'gpulocker:available_gpus',
    'disk_cache': 'gpulocker:disk_cache',
    'allocation_jobs': 'gpulocker:allocation_jobs',
    'scheduler_lock': 'gpulocker:scheduler_lock',
    'worker_heartbeat': 'gpulocker:worker_heartbeat:{}',  # Format with worker id
    'init_lock': 'gpulocker:init_lock',
    'system_initialized': 'gpulocker:system_initialized',
    'gpu_status': 'gpulocker:gpu_status',
    'gpu_config': 'gpulocker:gpu_config'
}