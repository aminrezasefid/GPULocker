import os
from app.utils.logger import logger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from decouple import config
# Remove the auth import to break the circular dependency
# from app.routes.auth import decrypt_username
from app.utils.db import MongoDBConnection
from app.utils.crypto import decrypt_username
import asyncio
# Enable logging


# Bot token should be stored as an environment variable
TOKEN = config("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables")

# Add decryption function directly here to avoid circular imports


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Log the message sent by user
    logger.info(f"TGLOG:User {user.id} ({user.username}) sent: {update.message.text}")
    
    # Check if there's a start parameter (for registration)
    if context.args and len(context.args[0]) > 0:
        encrypted_username = context.args[0]
        username = decrypt_username(encrypted_username)
        
        if username:
            # Store the telegram ID in the user document
            with MongoDBConnection() as (client, db):
                result = db.users.update_one(
                    {"username": username},
                    {"$set": {"tg_id": chat_id}}
                )
                
                if result.modified_count > 0:
                    await update.message.reply_html(
                        f"Hi {user.mention_html()}! Your account has been successfully connected to the GPULocker system. "
                        f"You will now receive notifications about your GPU allocations and other important updates."
                    )
                    logger.info(f"TGLOG:User {username} connected Telegram account (ID: {chat_id})")
                    return
                else:
                    logger.warning(f"TGLOG:Failed to find user {username} for Telegram registration")
    
    # Regular start message if not registering
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your notification bot for GPULocker. "
        f"Use /help to see available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
Available commands:
/start - Start the bot
/help - Show this help message
    """
    await update.message.reply_text(help_text)

async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all messages that are not commands."""
    user = update.effective_user
    logger.info(f"TGLOG:User {user.id} ({user.username}) sent message: {update.message.text}")

def build_bot() -> Application:
    """Start the bot."""
    # Create the Application with proxy support
    proxy_url = config("PROXY_URL", default=None)  # e.g., "socks5://user:pass@host:port"
    
    builder = Application.builder().token(TOKEN)
    
    # Add proxy if configured
    if proxy_url:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
        logger.info(f"Bot configured to use proxy: {proxy_url}")
    
    application = builder.build()
    
    # Add only necessary command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add a handler for all other messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, log_message))
    
    return application

def run_bot():
    """Run the bot in polling mode"""
    bot = build_bot()
    logger.info("TGLOG:Bot started in polling mode")
    try:
        # Use asyncio.run to create and manage the event loop
        asyncio.run(bot.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True))
    except Exception as e:
        logger.error(f"TGLOG:Bot polling failed with error: {str(e)}")
    finally:
        logger.info("TGLOG:Bot stopped")

if __name__ == "__main__":
    run_bot()
    
