import os
import tempfile

import yt_dlp
from app import Message, bot
from app.plugins.misc.song import extract_link_from_reply
from pyrogram.enums import ParseMode
from pyrogram.types import InputMediaAudio, InputMediaVideo

from .aicore import MODEL, ask_ai, run_basic_check
from .ai_sandbox.functions import get_ytm_link


@bot.add_cmd(cmd="yt")
@run_basic_check
async def ytm_link(bot, message: Message):
    reply = message.replied
    if reply and reply.media:
        content = ""
    elif reply:
        content = reply.text
    else:
        content = message.input

    message_response = await message.reply("<code>...</code>")

    prompts = (
        f"{content}\n\nThe above text/image contains a song name, extract that. "
        "Or guess the song based on description. Use search for getting the name. Reply only with song name and artist. "
        "If no ovbious song name, then take input as inspiration and give a random song name. "
        "If you can't even suggest any song, reply with 'unknown song'. "
    )
    song_name = await ask_ai(prompt=prompts, query=reply, **MODEL["DEFAULT"])

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


@bot.add_cmd(cmd="ytdl")
async def ytdl_upload(bot, message: Message):
    reply = message.replied
    link = extract_link_from_reply(reply) or message.input

    if not link:
        return await message.reply("No valid link found.")

    response = await message.reply("<code>Processing...</code>")

    try:
        if "music.youtube.com" in link:
            filename, info = await ytdl_audio(link)
        else:
            filename, info = await ytdl_video(link)
    except Exception:
        return await response.edit("Download failed.")

    await response.edit("Uploading...")

    if "music.youtube.com" in link:
        await response.edit_media(InputMediaAudio(media=filename))

    else:
        await response.edit_media(
            InputMediaVideo(
                media=filename, caption=info.get("title", ""), parse_mode=ParseMode.HTML
            )
        )

    os.remove(filename)


@bot.make_async
def ytdl_video(url: str):
    o = {
        "format": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(tempfile.gettempdir(), "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(o) as ydl:
        info = ydl.extract_info(url, download=True)
        fn = ydl.prepare_filename(info)
    return fn, info


@bot.make_async
def ytdl_audio(url: str):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tempfile.gettempdir(), "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        audio_path = os.path.splitext(path)[0] + ".mp3"
    return audio_path, info
