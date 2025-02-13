import copy
import json
import os

from pyrogram.enums import ParseMode

from app import BOT, Config, Message, bot
from app.plugins.ai.media_query import handle_media
from app.plugins.ai.models import (
    Settings,
    async_client,
    get_response_text,
    run_basic_check,
)

PAST_MODEL = None
PAST_CONFIG = copy.deepcopy(Settings.CONFIG)
SLOW_CONFIG = copy.deepcopy(Settings.CONFIG)


@bot.add_cmd(cmd="fh")
async def init_task(bot=bot, message=None):
    past_message_id = int(os.environ.get("PAST_MESSAGE_ID"))

    past_message = await bot.get_messages(
        chat_id=Config.LOG_CHAT, message_ids=past_message_id
    )

    json_data = json.loads(past_message.text)

    global PAST_MODEL
    PAST_MODEL = json_data["model"]

    PAST_CONFIG.system_instruction = json_data["text"]

    if message is not None:
        await message.reply("Done.", del_in=2)


MEDIUM = {"model": "gemini-2.0-flash", "config": Settings.CONFIG}
slow = copy.deepcopy(Settings.CONFIG)
fast = copy.deepcopy(Settings.CONFIG)
slow.tools = []
fast.tools = []
slow.max_output_tokens = 60000
FAST = {"model": "gemini-2.0-flash-lite-preview-02-05", "config": slow}
SLOW = {"model": "gemini-2.0-flash-thinking-exp-01-21", "config": slow}


@bot.add_cmd(cmd=["r", "rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    prompt = message.input

    message_response = await message.reply("<code>...</code>")

    if message.cmd == "r":
        extra_args = Settings.get_kwargs()
    else:
        extra_args = {"model": PAST_MODEL, "config": PAST_CONFIG}

    if reply and reply.media:
        response_text = await handle_media(
            prompt=prompt, media_message=reply, **extra_args
        )
    else:
        if reply and reply.text:
            prompts = [str(reply.text), message.input or "answer"]
        else:
            prompts = [message.input]

        response = await text_gen(
            contents=prompts, **extra_args
        )
        response_text = get_response_text(response, quoted=True)

    await message_response.edit(
        text=response_text, parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )


@bot.add_cmd(cmd="f")
@run_basic_check
async def fix(bot: BOT, message: Message):
    prompts = f"REWRITE FOLLOWING MESSAGE AS IS, WITH NO CHANGES TO FORMAT AND SYMBOLS ETC. AND ONLY WITH CORRECTION TO SPELLING ERRORS :- {message.replied.text}"

    response = await text_gen(
        contents=prompts, **MEDIUM
    )

    response_text = get_response_text(response)

    await message.replied.edit(response_text)


async def text_gen(contents: str, **kwargs):
    prompt = contents
    
    response = await async_client.models.generate_content(
            contents = prompt, **kwargs
        )

    return response

def get_slow_text(response):
    candidate = response.candidates[0]
    text = "\n".join([part.text for part in candidate.content.parts])
    final_text = text.strip()
    return final_text
