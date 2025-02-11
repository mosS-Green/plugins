from pyrogram.enums import ParseMode

from ub_core.utils.helpers import TELEGRAPH, post_to_telegraph

from app import BOT, Message, bot
from .text import text_gen, get_response_text, FAST, MEDIUM, SLOW, run_basic_check, get_slow_text


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
        "Embed Images using their links."
        "IMPORTANT - Do not include a title."
        "IMPORTANT - Do not write inside an html code block."
        "IMPORTANT - Do not any give pretext. Immediately start with article."
    )

    if "-t" in message.flags:
        model = SLOW
        get = get_slow_text
    else:
        model = MEDIUM
        get = get_response_text
    
    response = await text_gen(contents=base_prompt, **model)
    article_content = get(response)

    title_prompt = f"Generate a very concise and short title for this article: {article_content}. Only reply with the Title."
    title_response = await text_gen(contents=title_prompt, **FAST)
    title = get_response_text(title_response)

    page_url = await post_to_telegraph(title, article_content)

    await load_msg.edit(f"[{title}]({page_url})", parse_mode=ParseMode.MARKDOWN, disable_preview=True)


@bot.add_cmd(cmd="tf")
@run_basic_check
async def tf(bot: BOT, message: Message):
    content = message.replied
    title = message.input or "Telegraphed"

    load_msg = await message.reply("<code>...</code>")

    page_url = await post_to_telegraph(title, content)

    await load_msg.edit(f"[{title}]({page_url})", parse_mode=ParseMode.MARKDOWN, disable_preview=True)
