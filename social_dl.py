from pyrogram.raw.types.messages import BotResults
from pyrogram import filters
from ub_core import BOT, Message

reya = "@reyakamibot"


@BOT.add_cmd("d")
async def rsdl(bot: BOT, message: Message):
    """
    CMD: DL
    INFO: use bitch's bot
    USAGE: .d link
    """
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
            chat_id=reya,
            client=bot,
            from_user=bot.user.me.id,
            timeout=45,
            filters=filters.regex(r"sauce"),
        ) as c:
            media = await c.get_response()
            await media.copy(message.chat.id, caption="")

    except Exception as e:
        await message.reply(e)
