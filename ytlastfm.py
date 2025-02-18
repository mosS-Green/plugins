import json
import asyncio
import aiohttp
import yt_dlp
import os
import tempfile

from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
from pyrogram import filters

from app import Config
from ub_core import BOT, Message, bot
from ub_core.utils import aio

from .text import ask_ai, LEAF
from .yt import get_ytm_link

_bot: BOT = bot.bot


@bot.add_cmd(cmd="fren")
async def init_task(bot=bot, message=None):
    vars = await bot.get_messages(chat_id=Config.LOG_CHAT, message_ids=[4027, 4025])
    lastfm_names, apikey = vars
    global FRENS, API_KEY
    FRENS = json.loads(lastfm_names.text)
    API_KEY = apikey.text.strip()

    if message is not None:
        await message.reply("Done.", del_in=2)


@bot.add_cmd(cmd="st")
async def sn_now_playing(bot: BOT, message: Message):
      
    if not FRENS or not API_KEY:
        return await message.reply("Initialization incomplete.")

    load_msg = await message.reply("<code>...</code>")

    user = message.from_user
    username = FRENS.get(user.username)
    if not username:
        return await load_msg.edit("Username not found.")

    url = (
        f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}"
        f"&api_key={API_KEY}&format=json"
    )
    data = await aio.get_json(url)
    tracks = data.get("recenttracks", {}).get("track", [])
    current_track = next(
        (track for track in tracks if track.get("@attr", {}).get("nowplaying") == "true"),
        None
    )
    if not current_track:
        raise Exception("No track currently playing.")

    artist = current_track.get("artist", {}).get("#text", "Unknown Artist")
    track_name = current_track.get("name", "Unknown Track")

    ytm_link = await asyncio.to_thread(get_ytm_link, f"{track_name} by {artist}")
    song = f"**__[{track_name}]({ytm_link})__**"

    prompts = (
        "Write listening status message based on the vibe of the song."
        f"\n\n{user.first_name} is listening to {song} by __{artist}__."
        "Ensure both track and artist name are used."
        "\n\nIMPORTANT - KEEP FORMAT OF HREF INTACT."
    )

    sentence = await ask_ai(prompt=prompts, **LEAF)


    button = [InlineKeyboardButton(text="Download song", callback_data=f"y_{ytm_link}")]
        
    await load_msg.edit(
        text=sentence,
        parse_mode=ParseMode.MARKDOWN,
        disable_preview=True,
        reply_markup=InlineKeyboardMarkup([button])
    )


def download_audio(url: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(tempfile.gettempdir(), '%(id)s.%(ext)s'),
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


@_bot.on_callback_query(filters=filters.regex("^y_"))
async def song_ytdl(bot: BOT, callback_query: CallbackQuery):

    ytm_link = callback_query.data[2:]
    audio_path, info = await asyncio.to_thread(download_audio, ytm_link)

    await bot.send_audio(
        chat_id=callback_query.message.chat.id,
        audio=audio_path,
        caption=info.get('title', 'Song'),
        reply_to_message_id=callback_query.message.message_id
    )
    os.remove(audio_path)
