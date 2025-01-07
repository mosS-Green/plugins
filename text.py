import json
import mimetypes
import os
import pickle
from io import BytesIO

from pyrogram import filters
from pyrogram.enums import ParseMode

from app import BOT, Convo, Message, bot, Config
from google.ai import generativelanguage as glm
import google.generativeai as genai
from app.plugins.ai.text_query import do_convo
from .models import MEDIA_MODEL, run_basic_check, get_response_text, SAFETY_SETTINGS, GENERATION_CONFIG
from .media import handle_photo, handle_audio

CONV = []

@bot.add_cmd(cmd="fh")
async def init_task(bot=bot, message=None):
    past_message_id = int(os.environ.get("PAST_MESSAGE_ID"))
    
    past_message = await bot.get_messages(
        chat_id=Config.LOG_CHAT, message_ids=past_message_id
    )
    
    past = json.loads(past_message.text)
    
    global MPAST
    MPAST = genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest",
        generation_config=GENERATION_CONFIG,
        system_instruction=past,
        safety_settings=SAFETY_SETTINGS,
    )
    
    if message is not None:
        await message.reply("Done.", del_in=5)

@bot.add_cmd(cmd = "ah")
async def fix(bot: BOT, message: Message):
    global CONV
    if message.replied:
        CONV = json.loads(message.replied.text)
    else:
        CONV = []

@bot.add_cmd(cmd="rxc")
async def ai_chat(bot: BOT, message: Message):
    """
    CMD: AIC
    INFO: Have a Conversation with Gemini AI.
    USAGE:
        .aichat hello
        keep replying to AI responses
        After 5 mins of Idle bot will export history and stop chat.
        use .load_history to continue
    """
    if not await run_basic_check(message):
        return
    chat = MPAST.start_chat(history=[])
    await do_convo(chat=chat, message=message)


@bot.add_cmd(cmd="lxc")
async def history_chat(bot: BOT, message: Message):
    """
    CMD: LOAD_HISTORY
    INFO: Load a Conversation with Gemini AI from previous session.
    USAGE:
        .load_history {question} [reply to history document]
    """
    if not await run_basic_check(message):
        return
    reply = message.replied
    
    if (
        not reply
        or not reply.document
        or not reply.document.file_name
        or reply.document.file_name != "AI_Chat_History.pkl"
    ):
        await message.reply("Reply to a Valid History file.")
        return
        
    resp = await message.reply("<i>Loading History...</i>")
    doc: BytesIO = (await reply.download(in_memory=True)).getbuffer()  # NOQA
    history = pickle.loads(doc)
    await resp.edit("<i>History Loaded... Resuming chat</i>")
    chat = MPAST.start_chat(history=history)
    await do_convo(chat=chat, message=message)


@bot.add_cmd(cmd="ry")
async def question(bot: BOT, message: Message):
    """
    CMD: AI
    INFO: Ask a question to Gemini AI.
    USAGE: .ai what is the meaning of life.
    """

    prompt = message.input
        
    response = await MPAST.generate_content_async(prompt)

    response_text = get_response_text(response)

    await message.edit(
        text=f"```\n{prompt}```**Leaflet**:\n{response_text.strip()}",
        parse_mode=ParseMode.MARKDOWN,
    )

@bot.add_cmd(cmd=["r","rx"])
async def reya(bot: BOT, message: Message):
    """
    CMD: R
    INFO: Ask a question to Reya.
    USAGE: .r How to be strong?
    """
    if not (await run_basic_check(message)):  # fmt:skip
        return
    MODEL = MEDIA_MODEL if message.cmd == "r" else MPAST
    replied = message.replied
    prompt = message.input
    message_response = await message.reply("...")
  
    if replied and replied.photo:
        response_text = await handle_photo(prompt, replied, MODEL)
    
    elif replied and (replied.audio or replied.voice):
        response_text = await handle_audio(prompt, replied, MODEL)

    else:
        if replied and message.input:
            prompt = f"{replied.text}\n\n{message.input}"
        elif not message.input:
            prompt = replied.text
          
        convo = MODEL.start_chat(history = CONV)
        response = await convo.send_message_async(prompt)
        response_text = get_response_text(response)
    
    await message_response.edit(response_text)

@bot.add_cmd(cmd = "f")
async def fix(bot: BOT, message: Message):
    if not (await run_basic_check(message)):  # fmt:skip
        return
        
    prompt = f"REWRITE FOLLOWING MESSAGE AS IS, WITH NO CHANGES TO FORMAT AND SYMBOLS ETC. AND ONLY WITH CORRECTION TO SPELLING ERRORS :- {message.replied.text}"
    
    response = await MEDIA_MODEL.generate_content_async(prompt)
    response_text = get_response_text(response)
    message_response = message.replied
    await message_response.edit(response_text)
