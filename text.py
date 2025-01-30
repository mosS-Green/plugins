import json
import os
import pickle
from io import BytesIO

from pyrogram import filters
from pyrogram.enums import ParseMode

from app import BOT, Convo, Message, bot, Config
import google.generativeai as genai
from app.plugins.ai.text_query import do_convo, history_chat
from app.plugins.ai.media_query import handle_media
from app.plugins.ai.models import get_response_text, run_basic_check, SAFETY_SETTINGS, GENERATION_CONFIG, MODEL


@bot.add_cmd(cmd="fh")
async def init_task(bot=bot, message=None):
    past_message_id = int(os.environ.get("PAST_MESSAGE_ID"))
    
    past_message = await bot.get_messages(
        chat_id=Config.LOG_CHAT, message_ids=past_message_id
    )
    
    past = json.loads(past_message.text)
    
    global MPAST
    MPAST = genai.GenerativeModel(
        model_name="gemini-2.0-flash-exp",
        generation_config=GENERATION_CONFIG,
        system_instruction=past,
        safety_settings=SAFETY_SETTINGS,
    )
    
    if message is not None:
        await message.reply("Done.", del_in=5)

@bot.add_cmd(cmd="rxc")
@run_basic_check
async def ai_chat(bot: BOT, message: Message):
    chat = MPAST.start_chat(history=[])
    await do_convo(chat=chat, message=message)


@bot.add_cmd(cmd="lxc")
@run_basic_check
async def history_chat(bot: BOT, message: Message):
    MODEL = MPAST
    return await history_chat(bot, message)


@bot.add_cmd(cmd=["r","rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    reply_text = reply.text if reply else ""
    MODEL = MODEL if message.cmd == "r" else MPAST

    if reply and reply.media:
        message_response = await message.reply(
            "<code>Processing... this may take a while.</code>"
        )
        prompt = message.input
        response_text = await handle_media(
            prompt=prompt, media_message=reply, model=MODEL
        )
    else:
        message_response = await message.reply(
            "<code>Input received... generating response.</code>"
        )
        prompt = f"{reply_text}\n\n\n{message.input}".strip()
        response = await MODEL.generate_content_async(prompt)
        response_text = get_response_text(response)

    await message_response.edit(
        text=f"<blockquote expandable=True><pre language=text>{response_text.strip()}</pre></blockquote>",
        parse_mode=ParseMode.MARKDOWN,
    )


@bot.add_cmd(cmd = "f")
@run_basic_check
async def fix(bot: BOT, message: Message):   
    prompt = f"REWRITE FOLLOWING MESSAGE AS IS, WITH NO CHANGES TO FORMAT AND SYMBOLS ETC. AND ONLY WITH CORRECTION TO SPELLING ERRORS :- {message.replied.text}"
    
    response = await MODEL.generate_content_async(prompt)
    response_text = get_response_text(response)
    message_response = message.replied
    await message_response.edit(response_text)
