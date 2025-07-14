from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app.routes.auth import login_required
from app.utils.db import MongoDBConnection
from app.utils.crypto import encrypt_username
from decouple import config
from app.utils.notification import get_unread_notifications_count
from bson import ObjectId
from datetime import datetime

telegram_bp = Blueprint('telegram', __name__)

@telegram_bp.route('/telegram_settings')
@login_required
def telegram_settings():
    username = session['username']
    
    with MongoDBConnection() as (client, db):
        # Get all registered telegram accounts for this user
        telegram_accounts = list(db.telegram_users.find({"username": username}))
        
        # Format dates for display
        for account in telegram_accounts:
            registered_at = account.get('registered_at')
            if registered_at:
                account['registered_at_str'] = registered_at.strftime("%Y-%m-%d %H:%M:%S")
    
    # Generate registration link
    encrypted_username = encrypt_username(username)
    bot_username = config('TELEGRAM_BOT_USERNAME', default='')
    telegram_link = f"https://t.me/{bot_username}?start={encrypted_username}"
    
    # Get unread notifications count for navbar
    unread_count = get_unread_notifications_count(username)
    
    return render_template('telegram_settings.html',
                          telegram_accounts=telegram_accounts,
                          telegram_link=telegram_link,
                          unread_notifications_count=unread_count)
                          
@telegram_bp.route('/remove_telegram_account', methods=['POST'])
@login_required
def remove_telegram_account():
    username = session['username']
    telegram_id = request.form.get('telegram_id')
    
    if not telegram_id:
        flash('Invalid request', 'error')
        return redirect(url_for('telegram.telegram_settings'))
    
    with MongoDBConnection() as (client, db):
        # First check if the user has more than one telegram account
        count = db.telegram_users.count_documents({"username": username})
        
        if count <= 1:
            flash('You must have at least one Telegram account connected', 'error')
            return redirect(url_for('telegram.telegram_settings'))
            
        # Remove the specified telegram account
        result = db.telegram_users.delete_one({
            "_id": ObjectId(telegram_id),
            "username": username  # Security check to ensure users can only remove their own accounts
        })
        
        if result.deleted_count > 0:
            flash('Telegram account removed successfully', 'success')
        else:
            flash('Failed to remove Telegram account', 'error')
            
    return redirect(url_for('telegram.telegram_settings'))
