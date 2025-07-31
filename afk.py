import time
from datetime import datetime

# This will store the AFK users. In a real bot, you'd use a database.
# Format: {chat_id: {user_id: {"reason": "some reason", "time": timestamp, "user_name": "John"}}}
AFK_USERS = {}

# In-memory cache to map usernames to user IDs to avoid repeated API calls.
# Format: {chat_id: {"username": user_id}}
USERNAME_CACHE = {}

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

# Part 1: The command to set AFK status
@bot.add_cmd("afk")
async def set_afk(bot, message):
    """Sets your AFK status in the chat."""
    chat_id = message.chat.id
    user = message.from_user
    
    reason = "bhaad me gaya" # Default reason
    
    if message.input:
        reason = message.input
    elif message.reply_to_message and message.reply_to_message.text:
        reason = message.reply_to_message.text
        
    if chat_id not in AFK_USERS:
        AFK_USERS[chat_id] = {}
        
    AFK_USERS[chat_id][user.id] = {
        "reason": reason,
        "time": time.time(),
        "user_name": user.first_name, # Store the first name for cleaner replies
    }
    
    await message.reply(f"<b>{user.first_name}</b> is now AFK!\n<b>Reason:</b> {reason}", parse_mode="HTML")


# Part 2: The handler to check for AFK users on mentions
@bot.on_message()
async def afk_checker(bot, message):
    """Checks for mentions of AFK users and replies."""
    chat_id = message.chat.id

    # If the chat has no AFK users recorded, or the message is from a bot, do nothing.
    if chat_id not in AFK_USERS or (message.from_user and message.from_user.is_bot):
        return

    # --- 1. Check if the message sender is returning from AFK ---
    if message.from_user and message.from_user.id in AFK_USERS[chat_id]:
        afk_user_info = AFK_USERS[chat_id].pop(message.from_user.id)
        afk_duration = get_readable_time(int(time.time() - afk_user_info['time']))
        
        # Make a silent return if the user just used the /afk command
        if message.text and message.text.lower().startswith("/afk"):
            return
            
        await message.reply(
            f"Welcome back, <b>{message.from_user.first_name}</b>!\n"
            f"You were away for <b>{afk_duration}</b>.",
            parse_mode="HTML"
        )
        if not AFK_USERS[chat_id]:
            del AFK_USERS[chat_id]

    # --- 2. Check if the message is a reply to an AFK user ---
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user_id = message.reply_to_message.from_user.id
        if replied_user_id in AFK_USERS.get(chat_id, {}):
            afk_info = AFK_USERS[chat_id][replied_user_id]
            afk_since = get_readable_time(int(time.time() - afk_info['time']))
            
            await message.reply(
                f"<b>{afk_info['user_name']}</b> is AFK (for <b>{afk_since}</b>).\n"
                f"<b>Reason:</b> {afk_info['reason']}",
                parse_mode="HTML"
            )
            return # Stop checking once we've found a mention

    # --- 3. Check if the message contains @username or name-mentions of an AFK user ---
    if message.entities:
        afk_user_ids_in_chat = list(AFK_USERS.get(chat_id, {}).keys())
        
        for entity in message.entities:
            mentioned_user_id = None
            
            # Case A: Name mention (e.g., from typing @ and selecting a user)
            if entity.type == "text_mention" and entity.user:
                 mentioned_user_id = entity.user.id

            # Case B: Standard @username mention
            elif entity.type == "mention":
                username = message.text[entity.offset + 1 : entity.offset + entity.length].lower()
                
                # Check cache first to avoid API calls
                if chat_id in USERNAME_CACHE and username in USERNAME_CACHE[chat_id]:
                    mentioned_user_id = USERNAME_CACHE[chat_id][username]
                else:
                    # If not in cache, we need to iterate through members to find the user ID
                    # This is an expensive operation, so caching is important
                    async for member in bot.get_chat_members(chat_id):
                        if member.user and member.user.username and member.user.username.lower() == username:
                            mentioned_user_id = member.user.id
                            # Add to cache for next time
                            if chat_id not in USERNAME_CACHE:
                                USERNAME_CACHE[chat_id] = {}
                            USERNAME_CACHE[chat_id][username] = mentioned_user_id
                            break
            
            # If we found a mentioned user and they are AFK, reply and stop.
            if mentioned_user_id and mentioned_user_id in afk_user_ids_in_chat:
                afk_info = AFK_USERS[chat_id][mentioned_user_id]
                afk_since = get_readable_time(int(time.time() - afk_info['time']))
                
                await message.reply(
                    f"<b>{afk_info['user_name']}</b> is AFK (for <b>{afk_since}</b>).\n"
                    f"<b>Reason:</b> {afk_info['reason']}",
                    parse_mode="HTML"
                )
                return # Stop after the first found AFK user
