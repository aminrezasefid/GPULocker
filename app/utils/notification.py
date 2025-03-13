from app.utils.db import get_db_connection
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