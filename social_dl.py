from pyrogram.raw.types.messages import BotResults
from ub_core import BOT, Message

reya = "@reyakamibot"


@BOT.add_cmd("d")
async def rsdl(bot: BOT, message: Message):
    """Downloads media from social platforms via rsdl_bot."""
    proc = await message.reply("processing...")
    link = message.input if message.input else message.replied.text

    try:
        result: BotResults = await bot.user.get_inline_bot_results("rsdl_bot", link)

        if not result.results:
            await message.reply("Invalid url.")
            return

        await bot.user.send_inline_bot_result(
            chat_id=reya, query_id=result.query_id, result_id=result.results[0].id
        )

        async with bot.Convo(
            chat_id=reya, client=bot, from_user=bot.user.me.id, timeout=90
        ) as c:
            for _ in range(6):
                response = await c.get_response()

                # If it's just text or an animation (waiting gif), skip it
                if not response.media or response.animation:
                    continue

                # If it has media (Video, Audio, Document, Photo) and isn't the warning message
                if "more than one media" not in (response.content or ""):
                    await response.copy(message.chat.id)
                    return

    except Exception as e:
        await message.reply(str(e))
    finally:
        await proc.delete()
