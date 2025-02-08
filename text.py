import os
import json
import pickle
import copy
from io import BytesIO

from google.genai.chats import AsyncChat
from pyrogram import filters
from pyrogram.enums import ParseMode

from app import BOT, Message, bot, Config
from app.plugins.ai.media_query import handle_media
from app.plugins.ai.models import (
    Settings,
    async_client,
    get_response_text,
    run_basic_check,
)


@bot.add_cmd(cmd="fh")
async def init_task(bot=bot, message=None):
    past_message_id = int(os.environ.get("PAST_MESSAGE_ID"))

    past_message = await bot.get_messages(
        chat_id=Config.LOG_CHAT, message_ids=past_message_id
    )

    json_data = json.loads(past_message.text)
    global PAST_MODEL 
    PAST_MODEL = json_data["model"]
    global PAST_SI
    PAST_SI = json_data["text"]

    if message is not None:
        await message.reply("Done.", del_in=2)


async def create_cmodel():
    CMODEL = copy.deepcopy(Settings)
    CMODEL.MODEL = PAST_MODEL
    CMODEL.CONFIG.system_instruction = PAST_SI
    return CMODEL


@bot.add_cmd(cmd=["r","rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    reply_text = reply.text if reply else ""
    MODEL = Settings if message.cmd == "r" else await create_cmodel()

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
