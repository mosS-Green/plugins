from pyrogram.raw.types.messages import BotResults
from pyrogram import filters
from ub_core import BOT, bot, Message
import re


@BOT.add_cmd("d")
async def rsdl(bot: BOT, message: Message):
    """
    CMD: DL
    INFO: use bitch's bot
    USAGE: .d link
    """
    link = message.input or (message.replied and message.replied.text)
    if not link:
        await message.reply("link nahi diya?")
        return
    reya = bot.bot.me.id

    processing_msg = await message.reply("Processing...")

    try:
        result: BotResults = await bot.user.get_inline_bot_results("rsdl_bot", link)

        if not result.results:
            await processing_msg.edit("Invalid url.")
            return

        await bot.user.send_inline_bot_result(
            chat_id=reya, query_id=result.query_id, result_id=result.results[0].id
        )

        async with bot.Convo(
            chat_id=reya,
            client=bot,
            from_user=bot.user.me.id,
            timeout=45,
            filters=filters.regex(r"sauce", re.IGNORECASE),
        ) as c:
            media = await c.get_response()
            await media.copy(message.chat.id, caption="")
            await processing_msg.delete()

    except Exception as e:
        await processing_msg.edit(f"Error: {e}")
