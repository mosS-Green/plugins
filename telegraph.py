from app import BOT, Message, bot
from pyrogram.enums import ParseMode
from ub_core.utils.helpers import post_to_telegraph

from .ai_sandbox.core import ask_ai, MODEL
from app.plugins.ai.gemini.utils import run_basic_check


async def tele_graph(
    load_msg: Message,
    title: str,
    text: str,
    author_name: str = "leaflet",
    author_url: str = "https://t.me/leafinferno",
):
    """Posts content to Telegraph and edits message with the link."""
    page_url = await post_to_telegraph(title, text, author_name, author_url)

    await load_msg.edit(
        f"[{title}]({page_url})", parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )


@bot.add_cmd(cmd="tf")
@run_basic_check
async def tf(bot: BOT, message: Message):
    """Posts text directly to Telegraph without AI processing."""
    reply = message.replied
    load_msg = await message.reply("<code>...</code>")

    if reply and reply.text:
        content = reply
        title = message.input
    else:
        content = message.input
        title = "Click to read"

    await tele_graph(load_msg, title, content)
