from app.utils.db import get_db_connection
from app.utils.db import MongoDBConnection
from tg_bot.bot import build_bot
from datetime import datetime
from app.utils.logger import logger
import asyncio
from decouple import config, Csv

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


def send_notification(username,message):
    with MongoDBConnection() as (client, db):
        db.notifications.insert_one({
                            'username': username,
                            'message': message,
                            'read': False,
                            'created_at': datetime.now()
                        })
        user=db.users.find_one({
                    'username': username,
                    })
        application=build_bot()
        user_tg_id=user.get("tg_id")
        if user_tg_id:
            asyncio.run(application.bot.send_message(chat_id=user_tg_id, text=message))
        else:
            logger.warning(f"{username} didn't have telegram id")
        application.stop()