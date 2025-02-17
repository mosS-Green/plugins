import json
import os
from pyrogram.enums import ParseMode

from app import BOT, Message, bot, Config
from .aicore import ask_ai, LEAF_MODEL, QUICK, DEFAULT, run_basic_check


LEAF = None


@bot.add_cmd(cmd="fh")
async def init_task(bot=bot, message=None):
    past_message_id = int(os.environ.get("PAST_MESSAGE_ID"))

    past_message = await bot.get_messages(
        chat_id=Config.LOG_CHAT, message_ids=past_message_id
    )

    json_data = json.loads(past_message.text)

    LEAF_CONFIG = LEAF_MODEL.CONFIG
    LEAF_CONFIG.system_instruction = json_data["text"]
    LEAF_CONFIG.temperature = 0.8
    LEAF_CONFIG.max_output_tokens = 8192

    global LEAF
    LEAF = {"model": LEAF_MODEL.MODEL,"config": LEAF_CONFIG}
    
    if message is not None:
        await message.reply("Done.", del_in=2)


@bot.add_cmd(cmd=["r", "rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    prompt = message.input

    message_response = await message.reply("<code>...</code>")

    if message.cmd == "r":
        model = DEFAULT
    else:
        model = LEAF

    response = await ask_ai(
        prompt=prompt, query=reply, quote=True, **model
    )
    
    await message_response.edit(
        text=response, parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )


@bot.add_cmd(cmd="f")
@run_basic_check
async def fix(bot: BOT, message: Message):
    prompts = [
        "REWRITE FOLLOWING MESSAGE AS IS, WITH NO CHANGES TO FORMAT AND SYMBOLS ETC."
        f"AND ONLY WITH CORRECTION TO SPELLING ERRORS :- \n{message.replied.text}"
    ]
    
    response = await ask_ai(prompt=prompts, **QUICK)

    await message.replied.edit(response)
