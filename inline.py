from pyrogram.raw.types.messages import BotResults
from ub_core import BOT, Message, Config
from app.plugins.misc.inline_bot_results import run_with_timeout_guard


@BOT.add_cmd("dl")
@run_with_timeout_guard
async def rsdl(bot: BOT, message: Message):
    """
    CMD: DL
    INFO: use bitch's bot
    USAGE: .dl link
    """

    result: BotResults = await bot.get_inline_bot_results("rsdl_bot", message.input)

    if not result.results:
        return None, None, "No results found."

    return result.query_id, result.results[0].id, ""
