import time

from app import BOT, Config, Message, bot
from pyrogram.enums import ParseMode
from datetime import datetime

# Mock classes for demonstration. In your code, you already have these.
# from app import BOT, Config, Message, bot

# This will store the AFK users. In a real bot, you'd use a database.
# Format: {chat_id: {user_id: {"reason": "...", "time": ..., "user_name": "...", "username": "..."}}}
AFK_USERS = {}

# The USERNAME_CACHE is no longer needed with this simpler approach.

def get_readable_time(seconds: int) -> str:
    """Converts a duration in seconds to a human-readable string."""
    count = 0
    readable_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "d"]

    for i in range(4):
        count = seconds % 60
        if count > 0:
            time_list.append(str(count) + time_suffix_list[i])
        seconds //= 60
        if seconds == 0:
            break
            
    for i in range(len(time_list)):
        readable_time += time_list[len(time_list) - 1 - i]
    
    return readable_time or "0s"

# Part 1: The command to set AFK status (with a small addition)
@bot.add_cmd("afk")
async def set_afk(bot, message):
    """Sets your AFK status in the chat."""
    chat_id = message.chat.id
    user = message.from_user
    
    reason = "No reason given." # Changed default reason for clarity
    
    if message.input:
        reason = message.input
    elif message.reply_to_message and message.reply_to_message.text:
        reason = message.reply_to_message.text
        
    if chat_id not in AFK_USERS:
        AFK_USERS[chat_id] = {}
        
    # --- CHANGED: We now also store the username ---
    AFK_USERS[chat_id][user.id] = {
        "reason": reason,
        "time": time.time(),
        "user_name": user.first_name,
        "username": user.username.lower() if user.username else None,
    }
    
    await message.reply(f"<b>{user.first_name}</b> is now AFK!\n<b>Reason:</b> {reason}", parse_mode=ParseMode.HTML)


# Part 2: The handler to check for AFK users (now much simpler)
@bot.on_message()
async def afk_checker(bot, message):
    """Checks for mentions of AFK users and replies."""
    chat_id = message.chat.id

    if chat_id not in AFK_USERS or (message.from_user and message.from_user.is_bot):
        return

    # --- 1. Check if the message sender is returning from AFK (No change here) ---
    if message.from_user and message.from_user.id in AFK_USERS[chat_id]:
        afk_user_info = AFK_USERS[chat_id].pop(message.from_user.id)
        afk_duration = get_readable_time(int(time.time() - afk_user_info['time']))
        
        # Make a silent return if the user just used the /afk command
        if message.text and message.text.lower().startswith(("/afk", ".afk")): # Added support for bot prefixes
            return
            
        await message.reply(
            f"Welcome back, <b>{message.from_user.first_name}</b>!\n"
            f"You were away for <b>{afk_duration}</b>.",
            parse_mode=ParseMode.HTML
        )
        if not AFK_USERS[chat_id]:
            del AFK_USERS[chat_id]
        # We return here because if the user is coming back online, we don't need to check for mentions in their message.
        return

    # --- 2. Check if the message is a reply to an AFK user (No change here) ---
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user_id = message.reply_to_message.from_user.id
        if replied_user_id in AFK_USERS.get(chat_id, {}):
            afk_info = AFK_USERS[chat_id][replied_user_id]
            afk_since = get_readable_time(int(time.time() - afk_info['time']))
            
            await message.reply(
                f"<b>{afk_info['user_name']}</b> is AFK (for <b>{afk_since}</b>).\n"
                f"<b>Reason:</b> {afk_info['reason']}",
                parse_mode=ParseMode.HTML
            )
            return # Stop checking once we've found one

    # --- 3. THE NEW, SIMPLER MENTION CHECK ---
    # We check the raw text for "@username". This is much more efficient.
    if message.text:
        # Get a list of all AFK users in the current chat
        afk_users_in_chat = AFK_USERS.get(chat_id, {})
        
        # Iterate through each AFK user to see if they were mentioned
        for user_id, afk_info in afk_users_in_chat.items():
            # Check if the user has a username and if it's in the message
            if afk_info.get("username") and f"@{afk_info['username']}" in message.text.lower():
                afk_since = get_readable_time(int(time.time() - afk_info['time']))
                
                await message.reply(
                    f"<b>{afk_info['user_name']}</b> is AFK (for <b>{afk_since}</b>).\n"
                    f"<b>Reason:</b> {afk_info['reason']}",
                    parse_mode=ParseMode.HTML
                )
                return # Important: Stop after finding the first AFK user to avoid spam
