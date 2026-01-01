import asyncio
from app import BOT, Message, bot
from pyrogram.raw.types import UpdateNewMessage, UpdateNewChannelMessage

SOCIAL_BOT = "rsdl_bot"
DUMP_CHAT = -1002394753605


@bot.add_cmd(cmd="d")
async def social_dl(bot: BOT, message: Message):
    link = message.input
    if not link:
        await message.reply("Give me a link.")
        return

    status = await message.reply("Processing...")

    try:
        # 1. Get Inline Results
        results = await bot.user.get_inline_bot_results(SOCIAL_BOT, link)
        if not results.results:
            await status.edit("No results found from rsdl_bot.")
            return

        # 2. Send to Dump Chat
        # send_inline_bot_result returns the sent Message object directly
        sent_msg = await bot.user.send_inline_bot_result(
            DUMP_CHAT, results.query_id, results.results[0].id
        )
        
        if not sent_msg:
             await status.edit("Failed to send message.")
             return

        sent_msg_id = sent_msg.id

    except Exception as e:
        await status.edit(f"Error initiating request: {e}")
        return

    # 4. Polling for "Sauce"
    found = False
    attempts = 0
    max_attempts = 30 # 30 * 3s = 90s timeout

    while attempts < max_attempts:
        await asyncio.sleep(3)
        attempts += 1

        try:
            # Check specific message
            check_msg = await bot.user.get_messages(DUMP_CHAT, sent_msg_id)
            
            # Check for "Sauce" in caption
            if check_msg.caption and "Sauce" in check_msg.caption:
                # Found it!
                await bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=DUMP_CHAT,
                    message_id=sent_msg_id,
                )
                found = True
                break
                
        except Exception as e:
            await status.edit(f"Error while polling: {e}")
            return

    if found:
        await status.delete()
    else:
        await status.edit("Timeout: 'Sauce' never appeared.")
