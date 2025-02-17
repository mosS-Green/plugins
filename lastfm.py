import json
import asyncio
import aiohttp

from app import Config, bot, Message
from app.modules.aicore import ask_ai, DEFAULT
from .yt import get_ytm_link

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
        return await message.reply("Error during initialization.")
    await message.reply("Initialization successful.")

@bot.add_cmd(cmd="sn")
async def sn_now_playing(bot, message: Message):
    if not FRENS or not API_KEY:
        return await message.reply("Initialization incomplete.")
    
    user = message.from_user
    username = FRENS.get(user.username)
    if not username:
        return await message.reply("Username not found.")
    
    url = (
        f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}"
        f"&api_key={API_KEY}&format=json"
    )
    try:
        data = await fetch_json(url)
        tracks = data.get("recenttracks", {}).get("track", [])
        current_track = next(
            (track for track in tracks if track.get("@attr", {}).get("nowplaying") == "true"),
            None
        )
        if not current_track:
            raise Exception("No track currently playing.")
        
        artist = current_track.get("artist", {}).get("#text", "Unknown Artist")
        track_name = current_track.get("name", "Unknown Track")

        song_name = f"{track_name} by {artist}"
        ytm_link = await asyncio.to_thread(get_ytm_link_from_song, song_name)
        
        prompt = (
            f"Generate a short sentence in a chill tone: {user.first_name} is listening to "
            f"{song_name}. Ensure both track and artist name are used."
            "In this format - **__[{text}]({url})**__,"
            f"also hyperlink them with {ytm_link}"
            "Don't hyperlink the whole text."
        )
        sentence = await ask_ai(prompt=prompt, **DEFAULT)
        await message.reply(sentence)
    except Exception as e:
        await message.reply(str(e))
