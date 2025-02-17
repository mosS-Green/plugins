import json
import asyncio
import aiohttp
import os
import tempfile
import yt_dlp
from app import Config, bot, Message
from app.modules.aicore import ask_ai, DEFAULT
from app.modules.yt import get_ytm_link
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

async def fetch_json(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception("Error fetching data from last.fm.")
            return await response.json()

@bot.add_cmd(cmd="fren")
async def init_task(bot=bot, message=None):
    global FRENS, API_KEY
    try:
        lastfm_names = await bot.get_messages(chat_id=Config.LOG_CHAT, message_ids=4027)
        apikey = await bot.get_messages(chat_id=Config.LOG_CHAT, message_ids=4025)
        FRENS = json.loads(lastfm_names.text)
        API_KEY = apikey.text.strip()
    except Exception:
        return await message.reply("Initialization error.")
    await message.reply("Initialized.")

@bot.add_cmd(cmd="sn")
async def sn_now_playing(bot, message: Message):
    if not FRENS or not API_KEY:
        return await message.reply("Initialization incomplete.")
    user = message.from_user
    username = FRENS.get(user.username)
    if not username:
        return await message.reply("Username not found.")
    url = f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}&api_key={API_KEY}&format=json"
    try:
        data = await fetch_json(url)
        tracks = data.get("recenttracks", {}).get("track", [])
        current_track = next((track for track in tracks if track.get("@attr", {}).get("nowplaying") == "true"), None)
        if not current_track:
            raise Exception("No track playing.")
        artist = current_track.get("artist", {}).get("#text", "Unknown Artist")
        track_name = current_track.get("name", "Unknown Track")
        song_name = f"{track_name} by {artist}"
        ytm_link = await asyncio.to_thread(get_ytm_link, song_name)
        prompt = f"Generate a short sentence in a chill tone: {user.first_name} is listening to {song_name}. Ensure both track and artist name are used. In this format - **__[{text}]({url})**__, also hyperlink them with {ytm_link}. Don't hyperlink the whole text."
        sentence = await ask_ai(prompt=prompt, **DEFAULT)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Download", callback_data=f"download|{ytm_link}")]])
        await message.reply(sentence, reply_markup=keyboard)
    except Exception as e:
        await message.reply(str(e))

def download_audio(ytm_link: str):
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
        info = ydl.extract_info(ytm_link, download=True)
        path = ydl.prepare_filename(info)
        audio_path = os.path.splitext(path)[0] + ".mp3"
    return audio_path, info

@bot.add_callback_query_handler(callback_data_prefix="Download")
async def download_callback(bot, callback_query: CallbackQuery):
    try:
        _, ytm_link = callback_query.data.split("|", 1)
        await callback_query.answer("Downloading...")
        audio_path, info = await asyncio.to_thread(download_audio, ytm_link)
        await bot.send_audio(
            chat_id=callback_query.message.chat.id,
            audio=audio_path,
            caption=info.get('title', 'Song'),
            reply_to_message_id=callback_query.message.message_id
        )
        os.remove(audio_path)
    except Exception as e:
        await callback_query.answer(str(e))
