import asyncio
from app import BOT, Message, bot

SOCIAL_BOT = 1528267349


@bot.add_cmd(cmd="d")
async def social_dl(bot: BOT, message: Message):
    link = message.input
    if not link:
        await message.reply("Give me a link.")
        return

    status = await message.reply("Processing...")

    try:
        # Send request
        await bot.user.send_message(SOCIAL_BOT, f"_dl {link}")
    except Exception as e:
        await status.edit(f"Failed to send request: {e}")
        return

    # Polling
    found = False
    attempts = 0
    # Wait up to 60 seconds (20 * 3)
    max_attempts = 20

    while attempts < max_attempts:
        await asyncio.sleep(3)
        attempts += 1

        try:
            # Get last message
            async for msg in bot.user.get_chat_history(SOCIAL_BOT, limit=1):
                last_msg = msg
                break
            else:
                continue

            # Ignore if it's our own message
            if last_msg.from_user and last_msg.from_user.is_self:
                continue

            # Check for "Sauce" in caption
            if last_msg.caption and "Sauce" in last_msg.caption:
                # Found it
                await bot.user.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=SOCIAL_BOT,
                    message_id=last_msg.id,
                )
                found = True
                break

        except Exception as e:
            await status.edit(f"Error while polling: {e}")
            return

    if found:
        await status.delete()
    else:
        await status.edit("Timeout: No 'Sauce' found in response.")
