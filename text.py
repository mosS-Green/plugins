from pyrogram.enums import ParseMode

from app import BOT, Message, bot
from app.plugins.ai.gemini.utils import run_basic_check

from .models import CMD_MODEL_DICT, ask_ai
from .yt import get_ytm_link, ytdl_upload


@bot.add_cmd(cmd=["r", "rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    """Answers questions using AI with optional persona (rx for Leaflet)."""
    if message.replied:
        loading_msg = await message.replied.reply("<code>...</code>")
    else:
        loading_msg = await message.reply("<code>...</code>")

    ai_text = await ask_ai(message=message, model_name=CMD_MODEL_DICT[message.cmd])

    await loading_msg.edit(
        text=ai_text, parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )


@bot.add_cmd(cmd="f")
@run_basic_check
async def fix(bot: BOT, message: Message):
    """Fixes spelling errors in replied message."""
    message.filtered_input = (
        "\n\nREWRITE THE ABOVE MESSAGE AS IS, "
        "WITH NO CHANGES TO FORMAT AND SYMBOLS ETC."
        "AND ONLY WITH CORRECTION TO SPELLING ERRORS. "
    )
    response = await ask_ai(message=message, model_name=CMD_MODEL_DICT[message.cmd])
    await message.replied.edit(response)


@bot.add_cmd(cmd="yt")
@run_basic_check
async def ytm_link(bot: BOT, message: Message):
    """Finds a YouTube Music link for a song using AI."""
    message_response = await message.reply("<code>...</code>")

    if "-r" in message.flags or "-raw" in message.flags:
        song_name = message.replied.text or message.input
    else:
        message.filtered_input = (
            "The above text/image contains a song name, extract that. "
            "Or guess the song based on description. "
            "If no ovbious song name, then take input as inspiration and give a random song name. "
            "If you can't even suggest any song, reply exactly with 'unknown song'. ",
        )
        song_name = await ask_ai(message=message, model_name=CMD_MODEL_DICT[message.cmd])

    if "unknown song" in song_name.lower() or not song_name.strip():
        await message_response.edit("Couldn't determine the song title.")
        return

    await message_response.edit("<code>......</code>")

    # noinspection PyUnresolvedReferences
    ytm_link_result = await get_ytm_link(song_name)

    if not ytm_link_result:
        await message_response.edit("No search results found.")
        return

    place_holder = await message_response.edit(
        f"__[{song_name}]({ytm_link_result})__",
        parse_mode=ParseMode.MARKDOWN,
        disable_preview=True,
    )

    if "-dl" in message.flags:
        message_response.replied = place_holder
        await ytdl_upload(bot, message_response)
