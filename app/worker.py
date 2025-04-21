import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from decouple import config, Csv
from app.utils.logger import logger
from app.config import REDIS_BINARY
import os
import sys

from rq import Worker, Queue

def main():
    q = Queue(connection=REDIS_BINARY)
    worker = Worker(queues=q, connection=REDIS_BINARY)
    worker.work()

if __name__ == '__main__':
    main()
    
    