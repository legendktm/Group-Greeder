import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    JobQueue
)

# --- Configuration & Setup ---

# Set up logging for detailed information
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Define state keys for the user conversation flow
AWAITING_GROUP_INFO, AWAITING_MESSAGE = range(2)

# Global map to track which group belongs to which initiating user
# Structure: { chat_id (group ID): initiator_user_id }
# This is crucial for forwarding replies back to the correct person.
GROUP_TO_INITIATOR = {}

# Store the Telegram Bot Token (Replace 'YOUR_BOT_TOKEN_HERE' or use an environment variable)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7716852016:AAF_0q53GVWjNlA76m1g5u2GRyUeMSFTVUk")

# --- Core Job Function ---

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    """The function executed every minute by the JobQueue."""
    # Retrieve the target group ID and the message from the job context
    group_id = context.job.data.get("group_id")
    message_text = context.job.data.get("message")
    
    if group_id and message_text:
        try:
            # Send the message to the target group
            await context.bot.send_message(
                chat_id=group_id,
                text=message_text
            )
            logging.info(f"Scheduled message sent to group: {group_id}")
        except Exception as e:
            logging.error(f"Failed to send message to group {group_id}: {e}")
            # Optionally, notify the initiating user if the bot was removed from the group
            # or if the group was deactivated.

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command, initiates the setup process."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please use the /start command in a private chat with me to begin the setup.")
        return

    user_id = update.effective_user.id
    
    # Check if the user is already setting up a group
    if context.user_data.get('state') == AWAITING_GROUP_INFO:
        await update.message.reply_text(
            "You are already in the process of setting up a group. Please follow the instructions to continue."
        )
        return

    # Set the user's state to step 1
    context.user_data['state'] = AWAITING_GROUP_INFO
    context.user_data['initiator_id'] = user_id
    
    await update.message.reply_text(
        f"👋 Hello, {update.effective_user.first_name}!\n\n"
        "To activate the automated messaging service, please follow these two steps:\n\n"
        "1. **Add me to your target group** as an administrator.\n"
        "2. **Forward any message from that group** to this private chat, or send me the group's public `@username`.\n\n"
        "I need this to securely identify the group. Awaiting your input..."
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops the scheduled job associated with the initiating user's group."""
    user_id = update.effective_user.id
    
    # Find the group ID this user is associated with as an initiator
    # We must search the GROUP_TO_INITIATOR map by value (initiator_user_id)
    target_group_id = next((gid for gid, uid in GROUP_TO_INITIATOR.items() if uid == user_id), None)

    if target_group_id:
        # Construct the job name based on the group ID (must match how it was created)
        job_name = f"scheduled_message_{target_group_id}"
        
        # Remove the job from the job queue
        current_jobs = context.application.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            
        # Clear the global tracking maps
        GROUP_TO_INITIATOR.pop(target_group_id, None)
        
        # Clear user state data
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Automation successfully stopped for group ID `{target_group_id}`.\n"
            "The scheduled messages will no longer be sent."
        )
        logging.info(f"Automation stopped by user {user_id} for group {target_group_id}.")
    else:
        await update.message.reply_text(
            "No active automated message job found under your account. Use /start to set one up."
        )

# --- Message Handlers (For conversation flow and forwarding) ---

async def handle_group_info_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the user's input to identify the target group."""
    user_id = update.effective_user.id
    
    # Ensure this is a private chat and the user is in the correct state
    if update.effective_chat.type != "private" or context.user_data.get('state') != AWAITING_GROUP_INFO:
        return # Ignore non-relevant messages

    group_id = None
    
    # 1. Check if the message is a Forwarded message from a channel/group
    if update.message.forward_from_chat:
        group_id = update.message.forward_from_chat.id
        group_name = update.message.forward_from_chat.title or "Your Group"
        
    # 2. Check if the message is a group/channel username (e.g., @mygroup)
    elif update.message.text and update.message.text.startswith('@'):
        # Telegram chat IDs for public usernames are formatted like @username
        # Note: Bot must be added to a public group by its @username for this to work
        group_id = update.message.text 
        group_name = update.message.text
        
    if group_id:
        # Check if this group is already configured by *another* user
        if group_id in GROUP_TO_INITIATOR and GROUP_TO_INITIATOR[group_id] != user_id:
             await update.message.reply_text(
                 f"❌ Error: Group {group_name} is already managed by another user. "
                 "Only one initiating user can manage a group's scheduling."
             )
             context.user_data.pop('state', None) # Clear state
             return

        # Store the identified group ID
        context.user_data['group_id'] = group_id
        context.user_data['state'] = AWAITING_MESSAGE
        GROUP_TO_INITIATOR[group_id] = user_id # Temporarily map for setup
        
        logging.info(f"Group ID {group_id} registered for user {user_id}.")

        await update.message.reply_text(
            f"✅ Group Identified: **{group_name}**.\n\n"
            "Now, what message should I send to this group every **1 minute**?\n"
            'Please specify the exact text in a single message (e.g., "Your Message").'
        )
    else:
        await update.message.reply_text(
            "I couldn't identify the group. Please ensure you forward a message *from* the group or send the public `@username`."
        )


async def handle_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the message input and starts the scheduled job."""
    user_id = update.effective_user.id
    
    # Ensure this is a private chat and the user is in the correct state
    if update.effective_chat.type != "private" or context.user_data.get('state') != AWAITING_MESSAGE:
        return # Ignore non-relevant messages

    message_text = update.message.text
    group_id = context.user_data.get('group_id')
    
    if not message_text:
        await update.message.reply_text("Please send the message text, not a photo or sticker.")
        return

    if not group_id:
        # This should not happen if the flow is correct, but handles a safeguard
        await update.message.reply_text("Configuration error: Target group ID is missing. Please restart with /start.")
        context.user_data.clear()
        return

    # --- Start the Scheduling Job ---
    
    job_name = f"scheduled_message_{group_id}"
    
    # Remove any old jobs for this group just in case (e.g., if user ran /start twice)
    current_jobs = context.application.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    # Add the new recurring job
    context.application.job_queue.run_repeating(
        send_scheduled_message,
        interval=60,  # 60 seconds (1 minute)
        first=0,      # Start immediately
        data={
            "group_id": group_id,
            "message": message_text
        },
        name=job_name
    )

    # Clear user state and confirm
    context.user_data.clear()
    
    await update.message.reply_text(
        f"🎉 **Automation is now LIVE!**\n\n"
        f"I will send the message:\n\n"
        f"_{message_text}_\n\n"
        f"to group `{group_id}` every minute.\n\n"
        "**Reply Forwarding is Active:** Any replies to my scheduled messages in that group will be forwarded back to this chat.\n\n"
        "Use /stop at any time to halt the scheduled messages."
    )
    logging.info(f"Job started for group {group_id} by user {user_id} with message: {message_text}")


async def forward_reply_to_initiator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Checks if a message is a reply to the bot and forwards it to the initiating user."""
    
    # 1. Must be a group chat
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    message = update.effective_message
    
    # 2. Must be a reply
    if not message.reply_to_message:
        return
        
    reply_to = message.reply_to_message
    
    # 3. The message being replied to must have been sent by the bot
    if not reply_to.from_user.is_bot or reply_to.from_user.id != context.bot.id:
        return

    group_id = update.effective_chat.id
    
    # 4. Check if this group is currently tracked in our global map
    if group_id in GROUP_TO_INITIATOR:
        initiator_id = GROUP_TO_INITIATOR[group_id]
        
        try:
            # Forward the original reply message to the initiator
            await context.bot.forward_message(
                chat_id=initiator_id,
                from_chat_id=group_id,
                message_id=message.message_id
            )
            # Send a context message to the initiator
            await context.bot.send_message(
                chat_id=initiator_id,
                text=f"**Group Reply Received!**\nThis reply came from group `{update.effective_chat.title}`:",
            )
            logging.info(f"Reply forwarded from group {group_id} to initiator {initiator_id}.")
        except Exception as e:
            logging.error(f"Failed to forward reply to initiator {initiator_id}: {e}")


def main() -> None:
    """Starts the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # --- Handlers ---
    
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))

    # Message handlers for conversational flow in private chat
    # We use a single text handler and check the state within the handlers
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_group_info_input,
    ), group=1) # Group 1 for group info input
    
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_message_input,
    ), group=2) # Group 2 for message input

    # Handler for messages in groups that are replies to the bot
    application.add_handler(MessageHandler(
        filters.REPLY & filters.ChatType.GROUPS,
        forward_reply_to_initiator,
    ), group=3) # Group 3 for reply forwarding

    # Run the bot until the user presses Ctrl-C
    # Using long polling is standard for local development or for services like Render
    print("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
