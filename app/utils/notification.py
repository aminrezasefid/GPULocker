from app.utils.db import get_db_connection
from app.utils.db import MongoDBConnection
from bot import build_bot
from datetime import datetime
from app.utils.logger import logger
import time
import asyncio
from decouple import config, Csv
from app.config import enqueue_job

def get_unread_notifications_count(username):
    """Get the count of unread notifications for a user"""
    client, db = get_db_connection()
    try:
        count = db.notifications.count_documents({
            'username': username,
            'read': False
        })
        return count
    finally:
        client.close()


async def send_bulk_notification(message, users):
    """
    Send notification to multiple users asynchronously
    """
    try:
        application = build_bot()
        with MongoDBConnection() as (client, db):
            for username in users:
                try:
                    
                    logger.info(f"Sending notification to {username}")
                    db.notifications.insert_one({
                        'username': username,
                        'message': message,
                        'read': False,
                        'created_at': datetime.now()
                    })
                    
                    # Get all Telegram accounts for this user
                    telegram_accounts = list(db.telegram_users.find({"username": username}))
                    
                    if telegram_accounts:
                        for account in telegram_accounts:
                            user_tg_id = account.get("tg_id")
                            if user_tg_id:
                                time.sleep(.2)
                                await application.bot.send_message(chat_id=user_tg_id, text=message)
                    else:
                        logger.warning(f"{username} doesn't have any Telegram accounts")
                except Exception as e:
                    logger.error(f"Error sending notification to {username}: {e}", exc_info=True)
                    continue
    except Exception as e:
        logger.error(f"Error sending bulk notification: {e}", exc_info=True)


async def _send_notification_async(username, message):
    """
    Async function to send notification to a user's telegram accounts
    """
    try:
        application = build_bot()
        with MongoDBConnection() as (client, db):
            # First store the notification in database
            db.notifications.insert_one({
                'username': username,
                'message': message,
                'read': False,
                'created_at': datetime.now()
            })
            
            # Get all Telegram accounts for this user
            telegram_accounts = list(db.telegram_users.find({"username": username}))
            
            if telegram_accounts:
                for account in telegram_accounts:
                    user_tg_id = account.get("tg_id")
                    if user_tg_id:
                        try:
                            await application.bot.send_message(chat_id=user_tg_id, text=message)
                            logger.info(f"Sent notification to {username} via Telegram ID {user_tg_id}")
                        except Exception as e:
                            logger.error(f"Failed to send Telegram message to {username} (ID {user_tg_id}): {e}")
            else:
                logger.warning(f"{username} doesn't have any Telegram accounts")
    except Exception as e:
        logger.error(f"Error in async notification: {e}", exc_info=True)


def _run_async_notification(username, message):
    """
    Helper function to run the async notification in a separate context
    """
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info(f"Running async notification for {username}")
        # Run the async function in this loop
        loop.run_until_complete(_send_notification_async(username, message))
        loop.close()
    except Exception as e:
        logger.error(f"Error in async notification runner: {e}", exc_info=True)


def send_notification(username, message):
    """
    Enqueue a notification to be sent asynchronously
    This function should be used from synchronous contexts
    """
    # Enqueue the async notification job
    enqueue_job(_run_async_notification, username, message)
    logger.info(f"Notification for {username} has been enqueued: {message[:50]}...")