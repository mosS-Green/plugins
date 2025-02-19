import yt_dlp
import os
import asyncio
import re
import tempfile

from app import bot, Message
from pyrogram.enums import ParseMode

from .aicore import ask_ai, MODEL, run_basic_check
from app.plugins.misc.song import extract_link_from_reply


def get_ytm_link(song_name: str) -> str:
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': True,
        'format': 'bestaudio/best',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f"ytsearch:{song_name}"
        info = ydl.extract_info(search_query, download=False)
        if info.get('entries'):
            video = info['entries'][0]
            video_id = video.get('id')
            if video_id:
                return f"https://music.youtube.com/watch?v={video_id}"
    return None



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
        "If you are unable to guess, just reply with 'Unknown Song'."
    )
    song_name = await ask_ai(prompt=prompts, query=reply, **MODEL["DEFAULT"])

    if "unknown song" in song_name.lower() or not song_name.strip():
        await message_response.edit("Couldn't determine the song title.")
        return

    await message_response.edit("<code>......</code>")

    ytm_link_result = await asyncio.to_thread(get_ytm_link, song_name)
    if not ytm_link_result:
        await message_response.edit("No search results found.")

    await message_response.edit(
        f"__[{song_name}]({ytm_link_result})__",
        parse_mode=ParseMode.MARKDOWN,
        disable_preview=True,
    )




@bot.add_cmd(cmd="ytdl")
async def ytdl_upload(bot, message: Message):
    reply = message.replied
    link = extract_link_from_reply(reply) or message.input

    if not link:
        return await message.reply("No valid link found.")

    response = await message.reply("<code>Processing...</code>")


    try:
        if 'music.youtube.com' in link:
            filename, info = await asyncio.to_thread(ytdl_audio, link)
        else:
            filename, info = await asyncio.to_thread(ytdl_video, link)
    except Exception:
        return await response.edit("Download failed.")

    await response.edit("Uploading...")

    if 'music.youtube.com' in link:
        await bot.send_audio(
            chat_id=message.chat.id,
            audio=filename,
            caption=info.get("title", "No Title Found"),
            parse_mode=ParseMode.HTML,
        )
    else:
        await bot.send_video(
            chat_id=message.chat.id,
            video=filename,
            caption=info.get("title", "No Title Found"),
            parse_mode=ParseMode.HTML,
        )

    finally:
        os.remove(filename)

    await response.delete()


def ytdl_video(url: str):
    o = {
        'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
        'merge_output_format': 'mp4',
        'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(o) as ydl:
        info = ydl.extract_info(url, download=True)
        fn = ydl.prepare_filename(info)
    return fn, info


def ytdl_audio(url: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        audio_path = os.path.splitext(path)[0] + ".mp3"
    return audio_path, info
