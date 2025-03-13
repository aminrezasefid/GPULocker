from redis.lock import Lock as RedisLock
from app.config import REDIS_CLIENT,REDIS_KEYS
import json
class DistributedLock:
    """Redis-based distributed lock"""
    def __init__(self, lock_key, expire_time=60):
        self.lock = RedisLock(
            REDIS_CLIENT,
            lock_key,
            #timeout=expire_time,
            #blocking_timeout=5
        )
    
    def __enter__(self):
        if not self.lock.acquire():
            raise Exception("Could not acquire lock")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()
def get_available_gpus():
    """Get available GPUs from Redis"""
    gpu_data = REDIS_CLIENT.get(REDIS_KEYS['available_gpus'])
    if gpu_data:
        return json.loads(gpu_data)
    return {}

def set_available_gpus(gpu_dict):
    """Set available GPUs in Redis"""
    REDIS_CLIENT.set(REDIS_KEYS['available_gpus'], json.dumps(gpu_dict))