import os
from pyrogram.types import InputMediaPhoto

from app import BOT, Message, bot
from pyrogram.enums import ParseMode

from .aicore import MODEL, ask_ai, run_basic_check, generate_speech_ai, TEMP_DIR
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

    loading_msg = await message.reply("<code>...</code>")
    ai_image = None

    if message.cmd == "ri":
        ai_text, ai_image = await ask_ai(
            prompt=prompt, query=query, quote=True, img=True, **MODEL["IMG_EDIT"]
        )
    else:
        model = MODEL["LEAF"] if message.cmd == "rx" else MODEL["DEFAULT"]
        ai_text = await ask_ai(prompt=prompt, query=query, quote=True, **model)

    if ai_image:
        await loading_msg.edit_media(
            InputMediaPhoto(
                media=ai_image,
                caption=ai_text,
                parse_mode=ParseMode.MARKDOWN,
            )
        )
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


@bot.add_cmd(cmd=["speak"])
@run_basic_check  # Ensures basic checks (like API key) pass
async def speak_command(bot: BOT, message: Message):
    script = message.input
    if not script:
        await message.reply_text(
            "<code>Please provide some text to speak after the command.</code>"
        )
        return

    loading_msg = await message.reply_text(
        "<code>Generating audio...</code> 🎙️", parse_mode=ParseMode.HTML
    )

    file_path, audio_mime_type = await generate_speech_ai(
        script=script,
    )

    if not file_path:  # Error occurred, audio_mime_type here is the error message
        await loading_msg.edit_text(
            f"<b>Error generating speech:</b>\n<code>{audio_mime_type}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        # Send the audio file
        # Pyrogram's reply_audio handles uploading.
        # It typically sends as voice if ogg, or audio document otherwise.
        # You can add title, performer, duration if you can get them.
        sent_message = await message.reply_audio(
            audio=file_path,
            caption=f'🗣️: "<i>{script[:100]}{"..." if len(script) > 100 else ""}</i>"',
            parse_mode=ParseMode.HTML,
            # title="Generated Speech", # Optional
            # performer="Gemini AI",    # Optional
        )
        if sent_message:
            await loading_msg.delete()
        else:
            await loading_msg.edit_text("<code>Failed to send the audio file.</code>")

    except Exception as e:
        await loading_msg.edit_text(
            f"<b>Error sending audio:</b>\n<code>{e}</code>", parse_mode=ParseMode.HTML
        )
    finally:
        # Clean up the temporary file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e_rem:
                print(
                    f"Error deleting temp audio file {file_path}: {e_rem}"
                )  # Log this error
