import logging
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler
from telegram.ext import JobQueue
import time # Included for potential future use, though not strictly required for the current schedule

# --- Configuration ---
# IMPORTANT: 
# 1. Replace 'YOUR_BOT_TOKEN' with the actual token you get from BotFather.
# 2. Make sure you install the library: pip install python-telegram-bot
BOT_TOKEN = "7716852016:AAF_0q53GVWjNlA76m1g5u2GRyUeMSFTVUk" 

# Enable logging to see activity in the console
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variable to store the Chat ID of the group where the message should be sent
TARGET_CHAT_ID = None

# --- Scheduled Job Function ---

async def periodic_broadcast(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Sends the recurring message to the configured TARGET_CHAT_ID every minute.
    This function is executed by the JobQueue.
    """
    global TARGET_CHAT_ID

    if TARGET_CHAT_ID:
        # --- THE MESSAGE CONTENT ---
        message_text = "Hi I'm boy"
        # ---------------------------
        
        try:
            # Send the message to the stored chat ID
            await context.bot.send_message(
                chat_id=TARGET_CHAT_ID, 
                text=message_text
            )
            logger.info(f"Scheduled message sent successfully to chat ID: {TARGET_CHAT_ID}")
        except Exception as e:
            # Catch errors (e.g., bot was removed from the chat)
            logger.error(f"Failed to send scheduled message to chat {TARGET_CHAT_ID}. Error: {e}")
    else:
        logger.warning("Scheduled job ran, but TARGET_CHAT_ID is not set. Use /set_group in a chat.")


# --- Handlers (Commands) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and instructions."""
    instructions = (
        "Hello! I am your minute-by-minute Scheduled Bot.\n\n"
        "To activate my automatic message broadcast in this group, please use the command:\n"
        "👉 /set_group"
    )
    await update.message.reply_text(instructions)


async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the current group's ID as the target for the scheduled job."""
    global TARGET_CHAT_ID
    
    # Get the current chat ID and title
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title if update.effective_chat.title else "this private chat"

    # Restrict /set_group usage to actual group chats
    if chat_id > 0 and update.effective_chat.type == 'private':
        await update.message.reply_text("Please use the /set_group command inside the Telegram **group** you want me to message.")
        return

    # Store the new target ID globally
    TARGET_CHAT_ID = chat_id
    
    await update.message.reply_text(
        f"✅ Success! I will now broadcast the message 'Hi I'm boy' to **{chat_title}** every 60 seconds."
    )
    logger.info(f"Target Chat ID set to: {TARGET_CHAT_ID} ({chat_title})")


def main() -> None:
    """Starts the bot, initializes the JobQueue, and schedules the job."""
    
    # Safety check for the token
    if BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("FATAL ERROR: Please replace 'YOUR_BOT_TOKEN' with your actual Telegram Bot Token before running.")
        return
        
    # 1. Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # 2. Get the JobQueue instance
    job_queue = application.job_queue

    # 3. Schedule the repeating task (Job)
    # interval=60 means it runs every 60 seconds (1 minute)
    # first=0 means it runs immediately upon startup, and then every 60 seconds
    job_queue.run_repeating(
        periodic_broadcast, 
        interval=60, 
        first=0, 
        name='minute_broadcast'
    )
    print("Scheduled job (minute broadcast) successfully added.")


    # 4. Register Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_group", set_group))

    # 5. Start the Bot (polling mode)
    print("Bot is starting and minute-by-minute broadcast is scheduled...")
    # This function is blocking and will run until you press Ctrl+C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
