import logging
from logging.handlers import RotatingFileHandler
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
logFormatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s :: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)
consoleHandler.setFormatter(logFormatter)

fileHandler = RotatingFileHandler("gpulock.log", maxBytes=10*1024*1024, backupCount=3)
#fileHandler = logging.FileHandler('gpulock.log')
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
logger.addHandler(fileHandler)