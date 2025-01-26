from pyrogram.raw.types.messages import BotResults
from ub_core import BOT, Message, Config


@BOT.add_cmd("dl")
async def rsdl(bot: BOT, message: Message):
    """
    CMD: DL
    INFO: use bitch's bot
    USAGE: .dl link
    """

    results = await bot.get_inline_bot_results("rsdl_bot", message.input)

    if results.results:
        first_result = results.results[0]
        await message.reply_inline_bot_result(
            query_id=results.query_id,
            result_id=first_result.id
        )
    else:
        await message.reply("No results found.")
