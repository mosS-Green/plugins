import io
import os
import asyncio
import aiohttp
import io
import os
import asyncio
import aiohttp
from datetime import datetime

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from ub_core import BOT, CustomDB, Message, bot
from ub_core.utils import aio
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .lastfm import fetch_track_list, LASTFM_DB, fetch_song_play_count, format_time
from .yt import get_ytm_link

# Font URLs (Google Fonts - Outfit)
FONT_URLS = {
    "regular": "https://github.com/google/fonts/raw/main/ofl/outfit/Outfit-Regular.ttf",
    "bold": "https://github.com/google/fonts/raw/main/ofl/outfit/Outfit-Bold.ttf",
    "italic": "https://github.com/google/fonts/raw/main/ofl/outfit/Outfit-Medium.ttf", # Using Medium as Italic alternative for now or just standard
}

FONTS_DIR = "fonts"
os.makedirs(FONTS_DIR, exist_ok=True)

async def init_task(bot: BOT = None, message: Message = None):
    async with aiohttp.ClientSession() as session:
        for name, url in FONT_URLS.items():
            path = os.path.join(FONTS_DIR, f"Outfit-{name}.ttf")
            if not os.path.exists(path):
                async with session.get(url) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f:
                            f.write(await resp.read())


def _generate_image_sync(data: dict, cover_bytes: bytes | None, user_name: str) -> io.BytesIO:
    # Canvas settings
    width, height = 800, 300
    
    # 1. Background: Ambient Noise Gradient Blur
    if cover_bytes:
        try:
            # Use cover art as base for ambient background
            bg = Image.open(io.BytesIO(cover_bytes)).convert("RGBA")
            bg = bg.resize((width, height), Image.Resampling.LANCZOS)
            # Heavy blur
            bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
            
            # Darken it significantly for text visibility
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 120))
            bg = Image.alpha_composite(bg, overlay)
        except Exception:
             bg = Image.new("RGB", (width, height), (20, 20, 20))
    else:
        bg = Image.new("RGB", (width, height), (20, 20, 20))

    # Add Noise
    noise = Image.effect_noise((width, height), 15).convert("RGBA")
    # Blend noise (low alpha)
    noise.putalpha(20) 
    bg.paste(noise, (0, 0), noise)
    
    draw = ImageDraw.Draw(bg)

    # 2. Cover Art (Foreground)
    cover_size = 220
    padding = 40
    
    if cover_bytes:
        try:
            cover = Image.open(io.BytesIO(cover_bytes)).convert("RGBA")
            cover = cover.resize((cover_size, cover_size), Image.Resampling.LANCZOS)
        except Exception:
            cover = Image.new("RGB", (cover_size, cover_size), (50, 50, 50))
    else:
        cover = Image.new("RGB", (cover_size, cover_size), (50, 50, 50))
        
    # Add a simple border/shadow effect to cover (optional, keeping it simple for now)
    bg.paste(cover, (padding, (height - cover_size) // 2))

    # 3. Text
    # Fonts
    try:
        font_header = ImageFont.truetype(os.path.join(FONTS_DIR, "Outfit-regular.ttf"), 24)
        font_track = ImageFont.truetype(os.path.join(FONTS_DIR, "Outfit-bold.ttf"), 40)
        font_artist = ImageFont.truetype(os.path.join(FONTS_DIR, "Outfit-italic.ttf"), 28)
    except IOError:
        # Fallback
        font_header = ImageFont.load_default()
        font_track = ImageFont.load_default()
        font_artist = ImageFont.load_default()

    text_x = padding + cover_size + 40
    text_y = 60
    text_color = (255, 255, 255)
    accent_color = (220, 220, 220)

    # Line 1: "{Name} is vibing to"
    action = "is vibing to" if data["is_now_playing"] else f"was vibing to"
    header_text = f"{user_name} {action}"
    draw.text((text_x, text_y), header_text, font=font_header, fill=accent_color)
    
    # Line 2: Track Name (Bold)
    text_y += 40
    # Truncate if too long
    track_text = data["track_name"]
    if len(track_text) > 25:
        track_text = track_text[:25] + "..."
    draw.text((text_x, text_y), track_text, font=font_track, fill=text_color)

    # Line 3: by Artist (Italic)
    text_y += 55
    artist_text = f"by {data['artist_name']}"
    draw.text((text_x, text_y), artist_text, font=font_artist, fill=accent_color)

    # Save
    output = io.BytesIO()
    bg.save(output, format="PNG")
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
    user_name = fren_info.get("name", message.from_user.first_name)
    
    if not username:
         await message.reply("Last.fm username not found.")
         return

    load_msg = await message.reply("<code>...</code>")

    try:
        # Fetch raw track list to get image_url and other details
        track_list_raw = await fetch_track_list(username=username)

        if isinstance(track_list_raw, str):
            await load_msg.edit(track_list_raw)
            return
        
        if not track_list_raw:
            await load_msg.edit("No recent tracks found.")
            return

        track_info: dict = track_list_raw[0]
        
        # Extract necessary data for image generation
        is_now_playing = track_info.get("@attr", {}).get("nowplaying") == "true"
        artist_name = track_info["artist"]["#text"]
        track_name = track_info["name"]
        
        images = track_info.get("image", [])
        image_url = ""
        if images:
            image_url = images[-1].get("#text", "") # Get largest image

        # The play_count and last_played_time are not directly available in the raw track_list[0]
        # and would require another API call (track.getInfo) or a more complex parsing.
        # For now, we'll use placeholder or omit if not critical for image generation.
        # Assuming the image generation only needs track_name, artist_name, is_now_playing, and image_url.
        # If play_count and last_played_time are needed for the image, they would need to be fetched.
        # However, the image generation function `_generate_image_sync` does not use `play_count` or `last_played_time`.
        # The caption and buttons do use `play_count`.
        # To get `play_count`, we need to call `fetch_song_play_count` which is now in `lastfm.py`.

        play_count = await fetch_song_play_count(
            artist=artist_name, track=track_name, username=username
        )

        last_played_time = ""
        if not is_now_playing and "date" in track_info:
            last_played_time = format_time(
                datetime.fromtimestamp(int(track_info["date"]["uts"]))
            )

        data = {
            "track_name": track_name,
            "artist_name": artist_name,
            "album_name": track_info.get("album", {}).get("#text", ""), # Album name is not used in image, but good to have
            "image_url": image_url,
            "is_now_playing": is_now_playing,
            "play_count": play_count,
            "last_played_time": last_played_time,
        }

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
        image_io = await asyncio.to_thread(_generate_image_sync, data, cover_bytes, user_name)

        # Buttons
        yt_shortcode = ""
        try:
            # Use the imported function to get ytm_link
            # noinspection PyUnresolvedReferences
            ytm_link = await get_ytm_link(f"{track_name} by {artist_name}")
            if ytm_link:
                yt_shortcode = ytm_link.split("=")[1]
        except IndexError:
            yt_shortcode = ""

        buttons = [
            InlineKeyboardButton(
                text="♫",
                callback_data=f"y_{yt_shortcode}|{data['play_count']}|{user_id}",
            ),
            InlineKeyboardButton(
                text=f"{data['play_count']} plays", callback_data="-_-"
            ),
            InlineKeyboardButton(text="↻", callback_data=f"r_{user_id}"),
        ]

        await message.reply_photo(
            photo=image_io,
            caption=f"<b>{data['track_name']}</b> by <i>{data['artist_name']}</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([buttons])
        )
        await load_msg.delete()

    except Exception as e:
        await load_msg.edit(f"Error: {e}")
