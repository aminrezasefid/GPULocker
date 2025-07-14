import sys
import os
from datetime import datetime
#from decouple import config

# Add the current directory to the path so we can import our app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.utils.db import MongoDBConnection
from app.utils.logger import logger

def migrate_telegram_users():
    """
    Migrate Telegram IDs from users collection to the new telegram_users collection
    """
    logger.info("Starting migration of Telegram IDs from users collection to telegram_users collection")
    
    with MongoDBConnection() as (client, db):
        # Create the telegram_users collection if it doesn't exist
        if "telegram_users" not in db.list_collection_names():
            logger.info("Creating telegram_users collection")
            db.create_collection("telegram_users")
        
        # Find all users with tg_id field
        users_with_tg = db.users.find({"tg_id": {"$exists": True}})
        count = 0
        already_migrated = 0
        
        for user in users_with_tg:
            username = user.get("username")
            tg_id = user.get("tg_id")
            
            if not username or not tg_id:
                continue
                
            # Check if this telegram ID is already in the new collection
            existing = db.telegram_users.find_one({
                "username": username,
                "tg_id": tg_id
            })
            
            if existing:
                already_migrated += 1
                logger.info(f"User {username} already has Telegram ID {tg_id} in the new collection")
                continue
            
            # Insert record into telegram_users collection
            result = db.telegram_users.insert_one({
                "username": username,
                "tg_id": tg_id,
                "tg_username": None,  # We don't have this info from the old structure
                "registered_at": datetime.now()
            })
            
            if result.inserted_id:
                count += 1
                logger.info(f"Migrated Telegram ID {tg_id} for user {username}")
        
        logger.info(f"Migration complete: {count} Telegram IDs migrated, {already_migrated} already existed")
        
        # Now update the notification.py module to use the new structure
        # Since we've already updated the code, we just need to inform the user
        logger.info("Make sure to restart all services to use the new telegram_users structure")

if __name__ == "__main__":
    migrate_telegram_users()
