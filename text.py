import json
import os
from pyrogram.enums import ParseMode

from app import BOT, Message, bot, Config
from .aicore import ask_ai, MODEL, run_basic_check
from .telegraph import post_to_telegraph


@bot.add_cmd(cmd=["r", "rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    prompt = message.input

    message_response = await message.reply("<code>...</code>")

    if message.cmd == "r":
        model = MODEL["DEFAULT"]
    else:
        model = MODEL["LEAF"]

    response = await ask_ai(
        prompt=prompt, query=reply, quote=True, **model
    )
    
    await message_response.edit(
        text=response, parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )


@bot.add_cmd(cmd="rt")
@run_basic_check
async def ai_think(bot: BOT, message: Message):
    reply = message.replied
    prompts = message.input

    load_msg = await message.reply("<code>...</code>")

    title = "Scroll of Truth"
    article = await ask_ai(
        prompt=prompts, query=reply, **MODEL["THINK"]
    )

    page_url = await post_to_telegraph(title, article)

    await load_msg.edit(f"[{title}]({page_url})", parse_mode=ParseMode.MARKDOWN, disable_preview=True)


@bot.add_cmd(cmd="f")
@run_basic_check
async def fix(bot: BOT, message: Message):
    prompts = [
        "REWRITE FOLLOWING MESSAGE AS IS, WITH NO CHANGES TO FORMAT AND SYMBOLS ETC."
        f"AND ONLY WITH CORRECTION TO SPELLING ERRORS :- \n{message.replied.text}"
    ]
    
    response = await ask_ai(prompt=prompts, **MODEL["QUICK"])

    await message.replied.edit(response)