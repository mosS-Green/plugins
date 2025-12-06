import io
import os
import asyncio
import aiohttp
from datetime import datetime

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from ub_core import BOT, CustomDB, Message, bot
from ub_core.utils import aio
from PIL import Image, ImageDraw, ImageFont

from .yt import get_ytm_link

# Constants
LASTFM_DB = CustomDB["lastfm_users"]
BASE_URL = "http://ws.audioscrobbler.com/2.0/"
API_KEY = os.getenv("LASTFM_KEY")
API_SECRET = "b6774b62bca666a84545e7ff4976914a"


async def fetch_track_list(username: str) -> str | list[dict]:
    response_data = await aio.get_json(
        url=BASE_URL,
        params={
            "method": "user.getrecenttracks",
            "user": username,
            "api_key": API_KEY,
            "format": "json",
            "limit": 1,
        },
    )

    if not response_data:
        return "failed to fetch information"

    if "error" in response_data:
        return f"Last.fm API Error: {response_data['message']}"

    return response_data.get("recenttracks", {}).get("track", [])


async def fetch_song_play_count(artist: str, track: str, username: str) -> int:
    params = {
        "method": "track.getInfo",
        "api_key": API_KEY,
        "artist": artist,
        "track": track,
        "username": username,
        "format": "json",
    }
    response = await aio.get_json(url=BASE_URL, params=params)

    if not isinstance(response, dict) or "error" in response:
        return 0

    return response.get("track", {}).get("userplaycount", 0)


def format_time(date_time: datetime) -> str:
    now = datetime.now()
    time_diff = now - date_time
    if time_diff.days > 0:
        return f"{time_diff.days}d ago"
    elif time_diff.seconds // 3600 > 0:
        return f"{time_diff.seconds // 3600}h ago"
    elif time_diff.seconds // 60 > 0:
        return f"{time_diff.seconds // 60}m ago"
    else:
        return "just now"


async def get_now_playing_track(username) -> dict | str:
    if not API_KEY:
        return "Last.fm API key not initialized."

    track_list = await fetch_track_list(username=username)

    if isinstance(track_list, str):
        return track_list

    track_info: dict = track_list[0]
    is_now_playing = track_info.get("@attr", {}).get("nowplaying") == "true"
    artist_name = track_info["artist"]["#text"]
    track_name = track_info["name"]
    album_name = track_info.get("album", {}).get("#text", "")
    
    # Get Image
    images = track_info.get("image", [])
    image_url = ""
    if images:
        # Try to get the largest image
        image_url = images[-1].get("#text", "")

    play_count = await fetch_song_play_count(
        artist=artist_name, track=track_name, username=username
    )

    if not is_now_playing and "date" in track_info:
        last_played_time = format_time(
            datetime.fromtimestamp(int(track_info["date"]["uts"]))
        )
    else:
        last_played_time = ""

    return {
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": album_name,
        "image_url": image_url,
        "is_now_playing": is_now_playing,
        "play_count": play_count,
        "last_played_time": last_played_time,
    }


def _generate_image_sync(data: dict, cover_bytes: bytes | None) -> io.BytesIO:
    # Canvas settings
    width, height = 800, 300
    bg_color = (20, 20, 20)
    text_color = (255, 255, 255)
    accent_color = (200, 200, 200)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Load cover art
    cover_size = 260
    if cover_bytes:
        try:
            cover = Image.open(io.BytesIO(cover_bytes)).convert("RGBA")
            cover = cover.resize((cover_size, cover_size), Image.Resampling.LANCZOS)
        except Exception:
            cover = Image.new("RGB", (cover_size, cover_size), (50, 50, 50))
    else:
        cover = Image.new("RGB", (cover_size, cover_size), (50, 50, 50))

    # Paste cover with some padding
    padding = 20
    img.paste(cover, (padding, padding))

    # Text settings
    # Try to load a font, fallback to default
    try:
        # Attempt to use a system font or a specific font if available
        # This is tricky without knowing available fonts. 
        # We'll try a few common ones or fallback to default.
        font_large = ImageFont.truetype("arial.ttf", 48)
        font_medium = ImageFont.truetype("arial.ttf", 32)
        font_small = ImageFont.truetype("arial.ttf", 24)
    except IOError:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw Text
    text_x = padding + cover_size + 30
    text_y = padding + 10

    # Status (Now Playing / Last Played)
    status_text = "NOW PLAYING" if data["is_now_playing"] else f"LAST PLAYED ({data['last_played_time']})"
    draw.text((text_x, text_y), status_text, font=font_small, fill=accent_color)
    
    # Track Name
    text_y += 40
    draw.text((text_x, text_y), data["track_name"], font=font_large, fill=text_color)

    # Artist Name
    text_y += 60
    draw.text((text_x, text_y), data["artist_name"], font=font_medium, fill=accent_color)

    # Album Name (if available)
    if data["album_name"]:
        text_y += 45
        draw.text((text_x, text_y), data["album_name"], font=font_small, fill=accent_color)

    # Play Count
    text_y = height - padding - 30
    draw.text((text_x, text_y), f"Plays: {data['play_count']}", font=font_small, fill=accent_color)

    # Save to buffer
    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    output.name = "status.png"
    return output


@bot.add_cmd(cmd="si")
async def lastfm_image_status(bot: BOT, message: Message):

    user_id = message.from_user.id
    fren_info = await LASTFM_DB.find_one({"_id": user_id})

    if not fren_info:
        await message.reply("You are not logged in to Last.fm. Use /afren to login.")
        return

    username = fren_info.get("lastfm_username")
    if not username:
         await message.reply("Last.fm username not found.")
         return

    load_msg = await message.reply("<code>Generating...</code>")

    try:
        data = await get_now_playing_track(username)
        if isinstance(data, str):
            await load_msg.edit(data)
            return

        # Download cover art
        cover_bytes = None
        if data["image_url"]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(data["image_url"]) as resp:
                        if resp.status == 200:
                            cover_bytes = await resp.read()
            except Exception:
                pass

        # Generate Image
        image_io = await asyncio.to_thread(_generate_image_sync, data, cover_bytes)

        await message.reply_photo(
            photo=image_io,
            caption=f"<b>{data['track_name']}</b> by <i>{data['artist_name']}</i>",
            parse_mode=ParseMode.HTML
        )
        await load_msg.delete()

    except Exception as e:
        await load_msg.edit(f"Error: {e}")
