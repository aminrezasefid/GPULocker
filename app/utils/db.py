from pymongo import MongoClient
from contextlib import contextmanager
from datetime import datetime, timedelta
from app.utils.logger import logger
from bson import ObjectId
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

def setup_database():
    """Initialize the database with required collections"""
    client, db = get_db_connection()
    try:
        # Create collections if they don't exist
        if 'gpus' not in db.list_collection_names():
            db.create_collection('gpus')
            
        if 'allocations' not in db.list_collection_names():
            db.create_collection('allocations')
            
        if 'users' not in db.list_collection_names():
            db.create_collection('users')
            # Initialize with the list of users
        default_users = [
            "root", "sync", "user01", "admin", "zteam", "ehsan", "amin", 
            "khalooei", "armin", "mabanayeean", "mirzaei", "hosna", 
            "aezzati", "sahand", "afarzane", "akasaei", "testamin", 
            "postgres", "frahmani", "mnafez"
        ]
        
        # Add each user to the database if they don't exist
        for username in default_users:
            if not db.users.find_one({"username": username}):
                db.users.insert_one({
                    "username": username,
                    "created_at": datetime.now()
                })
            
        if 'notifications' not in db.list_collection_names():
            db.create_collection('notifications')
            
        logger.info("Database setup complete")
    finally:
        client.close()

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