import pickle
from io import BytesIO

from google.genai.chats import AsyncChat
from pyrogram import filters
from pyrogram.enums import ParseMode

from app import BOT, Convo, Message, bot, Config
from app.plugins.ai.media_query import handle_media
from app.plugins.ai.models import (
    Settings,
    async_client,
    get_response_text,
    run_basic_check,
)
from .cmodel import Fast


@bot.add_cmd(cmd=["r","rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    reply_text = reply.text if reply else ""
    MODEL = Settings if message.cmd == "r" else Fast

    if reply and reply.media:
        message_response = await message.reply(
            "<code>...</code>"
        )
        prompt = message.input
        response_text = await handle_media(
            prompt=prompt, media_message=reply, **MODEL.get_kwargs()
        )
    else:
        message_response = await message.reply(
            "<code>...</code>"
        )
        prompt = f"{reply_text}\n\n\n{message.input}".strip()
        response = await async_client.models.generate_content(
            contents=prompt, **MODEL.get_kwargs()
        )
        response_text = get_response_text(response)

    await message_response.edit(
        text=f"<blockquote expandable=True><pre language=text>{response_text.strip()}</pre></blockquote>",
        parse_mode=ParseMode.MARKDOWN,
        disable_preview=True,
    )


@bot.add_cmd(cmd = "f")
@run_basic_check
async def fix(bot: BOT, message: Message):   
    prompt = f"REWRITE FOLLOWING MESSAGE AS IS, WITH NO CHANGES TO FORMAT AND SYMBOLS ETC. AND ONLY WITH CORRECTION TO SPELLING ERRORS :- {message.replied.text}"
    
    response = await async_client.models.generate_content(
        contents=prompt, **Settings.get_kwargs()
    )
    response_text = get_response_text(response)
    message_response = message.replied
    await message_response.edit(response_text)
