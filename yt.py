import yt_dlp
import os
import asyncio

from app import bot, Message
from pyrogram.enums import ParseMode

from .aicore import ask_ai, DEFAULT, run_basic_check
from app.plugins.files.upload import upload_to_tg


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
    song_name = await ask_ai(prompt=prompts, query=reply, **DEFAULT)

    if "unknown song" in song_name.lower() or not song_name.strip():
        await message_response.edit("Couldn't determine the song title.")
        return

    await message_response.edit("<code>......</code>")

    ytm_link_result = await asyncio.to_thread(get_ytm_link_from_song, song_name)
    if not ytm_link_result:
        await message_response.edit("No search results found.")

    await message_response.edit(
        f"**>\n**[{title}]({page_url})**<**",
        parse_mode=ParseMode.MARKDOWN,
        disable_preview=True,
    )


@bot.add_cmd(cmd="ytdl")
async def ytdl_download(bot, message: Message):
    link = message.input
    response = await message.reply("<code>Downloading...</code>")
    ydl_opts = {
        'format': 'best[height<=360]',
        'outtmpl': 'downloaded_video.%(ext)s',
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            file = ydl.prepare_filename(info)
    except Exception as e:
        await response.edit("Download failed.")
        return
    await response.edit("Uploading...")
    await bot.send_video(
        chat_id=message.chat.id,
        video=filename,
        caption=info.get("title", "No Title Found"),
        parse_mode=ParseMode.HTML,
    )
    os.remove(file)
