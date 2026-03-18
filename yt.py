import asyncio
import os
import tempfile

import yt_dlp
from pyrogram.enums import ParseMode
from pyrogram.types import InputMediaAudio, InputMediaVideo

from app import Message, bot
from app.plugins.misc.song import extract_link_from_reply


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


@bot.make_async
def get_ytm_link(song_name: str) -> str | None:
    """Searches YouTube Music and returns link for a song."""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "format": "bestaudio/best",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f"ytsearch:{song_name}"
        info = ydl.extract_info(search_query, download=False)
        if info.get("entries"):
            video = info["entries"][0]
            video_id = video.get("id")
            if video_id:
                return f"https://music.youtube.com/watch?v={video_id}"
    return None
