from app.plugins.misc.inline_bot_results import run_with_timeout_guard
from pyrogram.raw.types.messages import BotResults
from ub_core import BOT, Message


@BOT.add_cmd("rn")
@run_with_timeout_guard
async def ub_lastfm(bot: BOT, message: Message):
    """Triggers own Last.fm inline bot."""

    result: BotResults = await bot.get_inline_bot_results(bot="reyakamibot")

    if not result.results:
        return None, None, "No results found."

    return result.query_id, result.results[0].id, ""


@BOT.add_cmd("dl")
@run_with_timeout_guard
async def rsdl(bot: BOT, message: Message):
    """Downloads media via rsdl_bot inline."""
    link = message.input if message.input else message.replied.text
    result: BotResults = await bot.get_inline_bot_results("rsdl_bot", link)

    if not result.results:
        return None, None, "No results found."

    return result.query_id, result.results[0].id, ""
