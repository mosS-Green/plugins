from app import BOT, Message, bot
from pyrogram.enums import ParseMode
from ub_core.utils.helpers import post_to_telegraph

from .aicore import MODEL, ask_ai, run_basic_check


async def tele_graph(
    load_msg: Message,
    title: str,
    text: str,
    author_name: str = "leaflet",
    author_url: str = "https://t.me/leafinferno",
):
    page_url = await post_to_telegraph(title, text, author_name, author_url)

    await load_msg.edit(
        f"[{title}]({page_url})", parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )


@bot.add_cmd(cmd="rg")
@run_basic_check
async def generate_article(bot: BOT, message: Message):
    reply = message.replied
    content = [message.input]

    load_msg = await message.reply("<code>...</code>")

    base_prompt = (
        f"{content}\n\nWrite a well-structured, informative, and engaging article based on the above input."
        "Ensure proper formatting with paragraphs, bullet points if necessary, and a natural flow."
        "Note - use HTML formatting. You are writing on the Telegra.ph platform."
        "IMPORTANT - Do not include a title."
        "IMPORTANT - Do not write inside an html code block."
        "IMPORTANT - Do not any give pretext. Immediately start with article."
    )

    article_content = await ask_ai(prompt=base_prompt, query=reply, **MODEL["DEFAULT"])
    article = article_content.strip("'")

    title_prompt = f"Generate a very concise and short title for this article: {article_content}. IMPORTANT - Only reply with the Title."
    title = await ask_ai(prompt=title_prompt, **MODEL["QUICK"])

    await tele_graph(load_msg, title, article)


@bot.add_cmd(cmd="tf")
@run_basic_check
async def tf(bot: BOT, message: Message):
    reply = message.replied
    load_msg = await message.reply("<code>...</code>")

    if reply and reply.text:
        content = reply
        title = message.input
    else:
        content = message.input
        title = "Click to read"

    await tele_graph(load_msg, title, content)
