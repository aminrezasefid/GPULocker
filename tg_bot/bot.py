import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from decouple import config
# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Set higher logging level for httpx to avoid excessive logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Bot token should be stored as an environment variable
TOKEN = config("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables")

# Dictionary to store chat IDs for notification purposes
notification_subscribers = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your notification bot. Use /subscribe to receive notifications."
    )

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Subscribe a user to notifications."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    notification_subscribers[user_id] = {
        "chat_id": chat_id,
        "name": user_name
    }
    
    await update.message.reply_text(
        f"You've been subscribed to notifications! Your chat ID is {chat_id}"
    )
    logger.info(f"User {user_name} (ID: {user_id}) subscribed with chat ID {chat_id}")

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unsubscribe a user from notifications."""
    user_id = update.effective_user.id
    
    if user_id in notification_subscribers:
        del notification_subscribers[user_id]
        await update.message.reply_text("You've been unsubscribed from notifications.")
        logger.info(f"User {update.effective_user.first_name} (ID: {user_id}) unsubscribed")
    else:
        await update.message.reply_text("You weren't subscribed to notifications.")

async def list_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all subscribers (admin command)."""
    # You might want to add admin verification here
    if not notification_subscribers:
        await update.message.reply_text("No subscribers yet.")
        return
    
    subscriber_list = "\n".join([f"{data['name']} (ID: {user_id}, Chat ID: {data['chat_id']})" 
                                for user_id, data in notification_subscribers.items()])
    await update.message.reply_text(f"Current subscribers:\n{subscriber_list}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
Available commands:
/start - Start the bot
/help - Show this help message
/subscribe - Subscribe to notifications
/unsubscribe - Unsubscribe from notifications
    """
    await update.message.reply_text(help_text)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text("I'm a notification bot. Use /help to see available commands.")

# Function to send notifications (can be called from other parts of your application)
async def send_notification(message: str, bot_app: Application, user_id=None):
    """
    Send a notification to a specific user or all subscribers.
    
    Args:
        message: The notification message
        bot_app: The bot application instance
        user_id: Optional user ID to send to a specific user only
    """
    if user_id and user_id in notification_subscribers:
        chat_id = notification_subscribers[user_id]["chat_id"]
        await bot_app.bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Notification sent to user {user_id}")
        return True
    
    elif user_id is None:  # Send to all subscribers
        for user_id, data in notification_subscribers.items():
            chat_id = data["chat_id"]
            await bot_app.bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Notification sent to {len(notification_subscribers)} subscribers")
        return True
    
    return False  # User not found

def build_bot() -> Application:
    """Start the bot."""
    # Create the Application with proxy support
    proxy_url = config("PROXY_URL")  # e.g., "socks5://user:pass@host:port"
    
    builder = Application.builder().token(TOKEN)
    
    # Add proxy if configured
    if proxy_url:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
        logger.info(f"Bot configured to use proxy: {proxy_url}")
    
    application = builder.build()
    #await application.bot.send_message(chat_id=204971907, text="GPULocker application started")
    #Add command handlers
    # application.add_handler(CommandHandler("start", start))
    # application.add_handler(CommandHandler("help", help_command))
    # application.add_handler(CommandHandler("subscribe", subscribe))
    # application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    # application.add_handler(CommandHandler("list", list_subscribers))

    # # Add message handler for non-command messages
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Run the bot until the user presses Ctrl-C
    #application.run_polling(allowed_updates=Update.ALL_TYPES)
    return application

if __name__ == "__main__":
    bot = build_bot()
    bot.run_polling(allowed_updates=Update.ALL_TYPES)
    
