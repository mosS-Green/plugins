import os
import tempfile

import yt_dlp
from app import Message, bot
from app.plugins.misc.song import extract_link_from_reply
from pyrogram.enums import ParseMode
from pyrogram.types import InputMediaAudio, InputMediaVideo

import asyncio
from .ai_sandbox.core import ask_ai, MODEL
from app.plugins.ai.gemini.utils import run_basic_check
from .ai_sandbox.functions import get_ytm_link


@bot.add_cmd(cmd="yt")
@run_basic_check
async def ytm_link(bot, message: Message):
    """Finds a YouTube Music link for a song using AI."""
    reply = message.replied
    if reply and reply.media:
        content = ""
    elif reply:
        content = reply.text
    else:
        content = message.input

    message_response = await message.reply("<code>...</code>")

    if "-r" in message.flags or "-raw" in message.flags:
        song_name = content
    else:
        prompts = (
            f"{content}\n\nThe above text/image contains a song name, extract that. "
            "Or guess the song based on description. "
            "If no ovbious song name, then take input as inspiration and give a random song name. "
            "If you can't even suggest any song, reply exactly with 'unknown song'. "
        )
        song_name = await ask_ai(prompt=prompts, query=reply, **MODEL["QUICK"])

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
    """Downloads and uploads YouTube video or audio."""
    reply = message.replied
    link = extract_link_from_reply(reply) or message.input

    if not link:
        return await message.reply("No valid link found.")

    response = await message.reply("<code>Processing...</code>")

    try:
        filename = None
        force_audio = "-a" in message.flags
        force_video = "-v" in message.flags

        is_music_link = "music.youtube.com" in link

        if force_audio or (is_music_link and not force_video):
            filename, info = await ytdl_audio(link)
            is_audio = True
        else:
            filename, info = await ytdl_video(link)
            is_audio = False

        await response.edit("Uploading...")

        if is_audio:
            await response.edit_media(InputMediaAudio(media=filename))
        else:
            await response.edit_media(
                InputMediaVideo(
                    media=filename,
                    caption=info.get("title", ""),
                    parse_mode=ParseMode.HTML,
                )
            )

    except Exception as e:
        await response.edit(f"Process failed: {str(e)}")
        return

    finally:
        if filename and os.path.exists(filename):
            await asyncio.to_thread(os.remove, filename)


@bot.make_async
def ytdl_video(url: str):
    """Downloads YouTube video at 360p max quality."""
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
    """Downloads YouTube audio as MP3."""
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
