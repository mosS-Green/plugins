from pyrogram.enums import ParseMode
from ub_core.utils.helpers import TELEGRAPH, post_to_telegraph

from app import BOT, Message, bot
from .aicore import ask_ai, DEFAULT, THINK, QUICK, run_basic_check


@bot.add_cmd(cmd="rg")
@run_basic_check
async def generate_article(bot: BOT, message: Message):
    reply = message.replied
    if reply and reply.text:
        content = [str(reply.text), message.input or "answer"]
    else:
        content = [message.input]
        
    load_msg = await message.reply("<code>...</code>")

    base_prompt = (
        f"Write a well-structured, informative, and engaging article based on the following input: {content}. "
        "Ensure proper formatting with paragraphs, bullet points if necessary, and a natural flow."
        "Note - use HTML formatting. You are writing on the Telegra.ph platform."
        "IMPORTANT - Do not include a title."
        "IMPORTANT - Do not write inside an html code block."
        "IMPORTANT - Do not any give pretext. Immediately start with article."
    )
    
    article_content = await ask_ai(prompt=base_prompt, **DEFAULT)

    title_prompt = f"Generate a very concise and short title for this article: {article_content}. Only reply with the Title."
    title = await ask_ai(prompt=title_prompt, **QUICK)

    page_url = await post_to_telegraph(title, article_content)

    await load_msg.edit(f"**>\n**[{title}]({page_url})**<**", parse_mode=ParseMode.MARKDOWN, disable_preview=True)


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

    page_url = await post_to_telegraph(title, content)

    await load_msg.edit(f"**>\n**[{title}]({page_url})**<**", parse_mode=ParseMode.MARKDOWN, disable_preview=True)
