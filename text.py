import os

from pyrogram.enums import ParseMode
from pyrogram.types import InputMediaDocument

from app import BOT, Message, bot

from .aicore import MODEL, ask_ai, run_basic_check, ask_ai_exp
from .telegraph import tele_graph


@bot.add_cmd(cmd=["r", "rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    prompt = message.input
    message_response = await message.reply("<code>...</code>")
    model = MODEL["DEFAULT"] if message.cmd == "r" else MODEL["LEAF"]
    response = await ask_ai(prompt=prompt, query=reply, quote=True, **model)
    await message_response.edit(
        text=response, parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )


@bot.add_cmd(cmd="rt")
@run_basic_check
async def ai_think(bot: BOT, message: Message):
    reply = message.replied
    prompts = message.input
    load_msg = await message.reply("<code>...</code>")
    content = await ask_ai(prompt=prompts, query=reply, **MODEL["THINK"])
    await tele_graph(load_msg=load_msg, title="the Answer", text=content)


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


@bot.add_cmd(cmd="rh")
@run_basic_check
async def ai_page(bot: BOT, message: Message):
    reply = message.replied
    temp_html = "Answer.html"
    prompt = (
        f"{message.input}\n\n"
        "Create a complete, standalone HTML page based on the above query. "
        "REQUIREMENTS: \n"
        "1. Use Material You/Monet design principles\n"
        "2. Base color scheme: Light moss green (#8FBC8F)\n"
        "3. Use rounded and proportional UI elements\n"
        "4. Ensure responsive design\n"
        "5. Include modern, clean typography\n"
        "6. Provide full, self-contained HTML that can be directly rendered\n"
        "7. Include meta tags for proper rendering\n"
        "8. Add basic, elegant interactivity\n\n"
        "IMPORTANT - Only write the code, do not include any comments or explanations.\n"
        "IMPORTANT - Do not include any external resources or links."
    )

    load_msg = await message.reply("<code>doing ai things...</code>")

    try:
        content = await ask_ai(prompt=prompt, query=reply, **MODEL["THINK"])

        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(content)

        await load_msg.edit_media(
            media=InputMediaDocument(media=temp_html, caption="Here you go.")
        )

    except Exception as e:
        await load_msg.edit_text(f"Error generating HTML: {str(e)}")

    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)


@bot.add_cmd(cmd="ri")
@run_basic_check
async def ri_question(bot: BOT, message: Message):
    reply = message.replied
    prompt = message.input
    loading_msg = await message.reply("<code>...</code>")
    response = await ask_ai_exp(prompt=prompt, query=reply, quote=True, **MODEL["EXP"])
    text_response = response.get("text", "")
    image_path = response.get("image")
    if image_path:
        if len(text_response) <= 200:
            await loading_msg.edit_media(
                InputMediaPhoto(
                    media=image_path,
                    caption=f"**>\n{text_response}<**",
                    parse_mode=ParseMode.MARKDOWN,
                )
            )
        else:
            await loading_msg.edit_media(InputMediaPhoto(media=image_path))
            await message.reply(f"> {text_response}", parse_mode=ParseMode.MARKDOWN)
        os.remove(image_path)
    else:
        await loading_msg.edit(
            text=f"> {text_response}",
            parse_mode=ParseMode.MARKDOWN,
            disable_preview=True,
        )
