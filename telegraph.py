from pyrogram.enums import ParseMode

from app import BOT, Message, bot

from app.modules.text import text_gen, get_response_text, Settings
from ub_core.utils.helpers import TELEGRAPH, post_to_telegraph, run_basic_check


@bot.add_cmd(cmd="rg")
@run_basic_check
async def generate_article(bot: BOT, message: Message):
    if not message.input:
        await message.reply("Give me a topic or details to generate the article!")
        return

    load_msg = await message.reply("<code>...</code>")

    base_prompt = (
        f"Write a well-structured, informative, and engaging article based on the following input: {message.input}. "
        "Ensure proper formatting with paragraphs, bullet points if necessary, and a natural flow. IMPORTANT - use HTML formatting."
        "IMPORTANT - Do not include a title. And do not write within code block."
        "IMPORTANT - Do not any give pretext. Immediately start with article."
    )

    model = **Settings.get_kwargs()

    response = await text_gen(contents=base_prompt, model)
    article_content = get_response_text(response)

    title_prompt = f"Generate a concise and compact title for this article: {article_content}. Only reply with the Title."
    title_response = await text_gen(contents=title_prompt, model)
    title = get_response_text(title_response)

    page_url = await post_to_telegraph(title, article_content)

    await load_msg.edit(f"[{title}]({page_url})", parse_mode=ParseMode.MARKDOWN, disable_preview=True)


@bot.add_cmd(cmd="tf")
async def tf(bot: BOT, message: Message):
    text = message.input or (message.replied.text if message.replied and message.replied.text else None)
    if not text:
        await message.reply("Provide some text!")
        return
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Not enough text to generate title and content!")
        return
    title, content = parts[0], parts[1]
    page_url = await post_to_telegraph(title, content)

    await message.reply(f"[{title}]({page_url})", parse_mode=ParseMode.MARKDOWN, disable_preview=True)