import os

from pyrogram.types import InputMediaPhoto

from app import BOT, Message, bot
from pyrogram.enums import ParseMode

from .aicore import MODEL, ask_ai, run_basic_check
from .telegraph import tele_graph


@bot.add_cmd(cmd=["r", "rx", "ri"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    input = message.input

    user_first_name = message.from_user.first_name if message.input else None
    reply_first_name = reply.from_user.first_name if reply and reply.from_user else None

    if (
        message.cmd == "rx"
        and reply
        and reply_first_name
        and not (reply.media or not input)
    ):
        prompt = f"[{user_first_name}]:- {input}"
        query = f"[{reply_first_name}]:- {reply.text}" if reply.text else None
    else:
        prompt = input
        query = reply

    MODEL_MAP = {
        "ri": MODEL["IMG_EDIT"],
        "rx": MODEL["LEAF"],
        "r": MODEL["DEFAULT"],
    }
    model = MODEL_MAP.get(message.cmd)
    loading_msg = await message.reply("<code>...</code>")

    ai_text, ai_image = await ask_ai(prompt=prompt, query=query, quote=True, **model)

    if ai_image:
        if len(ai_text) <= 200:
            await loading_msg.edit_media(
                InputMediaPhoto(
                    media=ai_image,
                    caption=ai_text,
                    parse_mode=ParseMode.MARKDOWN,
                )
            )
        else:
            await loading_msg.edit_media(InputMediaPhoto(media=ai_image))
            await message.reply(f"{ai_text}", parse_mode=ParseMode.MARKDOWN)
    else:
        await loading_msg.edit(
            text=ai_text, parse_mode=ParseMode.MARKDOWN, disable_preview=True
        )


@bot.add_cmd(cmd="rt")
@run_basic_check
async def ai_think(bot: BOT, message: Message):
    reply = message.replied
    prompts = message.input
    load_msg = await message.reply("<code>...</code>")
    content = await ask_ai(prompt=prompts, query=reply, **MODEL["THINK"])
    await tele_graph(load_msg=load_msg, title="Answer", text=content)


@bot.add_cmd(cmd="f")
@run_basic_check
async def fix(bot: BOT, message: Message):
    prompts = (
        "REWRITE FOLLOWING MESSAGE AS IS, "
        "WITH NO CHANGES TO FORMAT AND SYMBOLS ETC."
        f"AND ONLY WITH CORRECTION TO SPELLING ERRORS :- "
        f"\n{message.replied.text}"
    )
    response = await ask_ai(prompt=prompts, **MODEL["QUICK"])
    await message.replied.edit(response)


@bot.add_cmd(cmd="hu")
@run_basic_check
async def humanize(bot: BOT, message: Message):
    reply = message.replied

    load_msg = await message.reply("`dumbing down...`")

    prompts = (
        "Please convert the following content into a concise, easily human readable & understandable info. "
        "If the content includes lengthy logs, error messages, or commit entries, extract only the latest three entries "
        "and provide concise, clear explanations for each. Preserve essential details while improving readability."
        "\nIMPORTANT - Keep response concise."
    )

    response = await ask_ai(prompt=prompts, query=reply, quote=True, **MODEL["DEFAULT"])
    await load_msg.edit(response)
