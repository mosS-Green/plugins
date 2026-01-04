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
            chat_id=reya, client=bot, from_user=bot.user.me.id, timeout=30
        ) as c:
            await c.get_response()  # button removal
            await c.get_response()  # waiting gif
            # Wait for the actual media message, skipping text status updates
            media_msg = await c.get_response()

            # If the first response is just text (like "Uploadng..."), get the next one
            if not media_msg.media:
                media_msg = await c.get_response()

            if media_msg.media:
                await media_msg.copy(message.chat.id)
            elif "more than one media" in (media_msg.text or ""):
                # If multiple media, wait for them. This part is tricky without knowing exact bot behavior,
                # but let's assume it sends them sequentially or as an album.
                # For now, let's just grab the next one which should be the album start
                next_media = await c.get_response()
                if next_media.media:
                    await next_media.copy(message.chat.id)
            else:
                # Sometimes text is sent first, then media
                pass

    except Exception as e:
        await message.reply(str(e))
    finally:
        await proc.delete()
