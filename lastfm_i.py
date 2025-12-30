import io
import os
import asyncio
import aiohttp
import random
from datetime import datetime

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from ub_core import BOT, CustomDB, Message, bot
from ub_core.utils import aio
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .lastfm import fetch_track_list, LASTFM_DB, fetch_song_play_count, format_time
from .yt import get_ytm_link

def _generate_default_cover(size: int) -> Image.Image:
    # 6 Tasteful Darker Colors
    colors = [
        "#0E1621", # Darker Charcoal Blue
        "#0A2E19", # Darker Emerald
        "#26122E", # Darker Midnight Violet
        "#330F0B", # Darker Burnt Crimson
        "#0B2230", # Darker Ocean
        "#11181F"  # Darker Slate
    ]
    color = random.choice(colors)
    
    # Square is pure black
    img = Image.new("RGBA", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Disc (The Ring) -> Colored
    cx, cy = size // 2, size // 2
    r_disc = int(size * 0.42)
    draw.ellipse((cx - r_disc, cy - r_disc, cx + r_disc, cy + r_disc), fill=color)
    
    # Inner Label (Hole) -> Black to match background and form a ring
    r_label = int(r_disc * 0.4)
    draw.ellipse((cx - r_label, cy - r_label, cx + r_label, cy + r_label), fill=(0, 0, 0))

    return img

def _generate_image_sync(data: dict, cover_bytes: bytes | None, user_name: str) -> io.BytesIO:
    # Canvas settings
    width, height = 800, 300
    cover_size = 220
    
    # Determine Cover Image
    cover_image = None
    if cover_bytes:
        try:
            cover_image = Image.open(io.BytesIO(cover_bytes)).convert("RGBA")
        except Exception:
            pass

    if not cover_image:
        cover_image = _generate_default_cover(cover_size)

    # 1. Background: Ambient Noise Gradient Blur
    bg = cover_image.copy()
    if bg.mode != "RGBA":
        bg = bg.convert("RGBA")
        
    bg = bg.resize((width, height), Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
    
    # Darken it significantly for text visibility
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 120))
    bg = Image.alpha_composite(bg, overlay)
    
    # Add Noise
    noise = Image.effect_noise((width, height), 15).convert("RGBA")
    # Blend noise (low alpha)
    noise.putalpha(20) 
    bg.paste(noise, (0, 0), noise)
    
    draw = ImageDraw.Draw(bg)

    # 2. Cover Art (Foreground)
    padding = 40
    
    # Reuse cover_image, ensure size
    cover_final = cover_image.resize((cover_size, cover_size), Image.Resampling.LANCZOS)
    
    # Paste Cover
    bg.paste(cover_final, (padding, (height - cover_size) // 2), cover_final if cover_final.mode == "RGBA" else None)

    # 3. Text
    # Fonts - Using default font with size scaling (Pillow >= 10.0.0)
    try:
        font_header = ImageFont.load_default(size=24)
        font_track = ImageFont.load_default(size=48)
        font_artist = ImageFont.load_default(size=32)
    except TypeError:
        # Fallback for older Pillow versions that don't support size in load_default
        # We can't easily scale the bitmap default font, so we might be stuck with small text
        # unless we load a system font. Let's try a common linux path just in case.
        try:
            font_header = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            font_track = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_artist = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", 32)
        except IOError:
             font_header = ImageFont.load_default()
             font_track = ImageFont.load_default()
             font_artist = ImageFont.load_default()

    text_x = padding + cover_size + 40
    text_y = 50
    text_color = (255, 255, 255)
    accent_color = (220, 220, 220)

    # Line 1: "{Name} is vibing to"
    action = "is vibing to" if data["is_now_playing"] else f"was vibing to"
    header_text = f"{user_name} {action}"
    draw.text((text_x, text_y), header_text, font=font_header, fill=accent_color)
    
    # Line 2: Track Name (Bold)
    text_y += 45
    # Truncate if too long
    track_text = data["track_name"]
    if len(track_text) > 20:
        track_text = track_text[:20] + "..."
    draw.text((text_x, text_y), track_text, font=font_track, fill=text_color)

    # Line 3: by Artist (Italic)
    text_y += 75
    artist_text = f"by {data['artist_name']}"
    draw.text((text_x, text_y), artist_text, font=font_artist, fill=accent_color)

    # Save
    output = io.BytesIO()
    bg.save(output, format="PNG")
    output.seek(0)
    output.name = "status.png"
    return output


def _convert_to_sticker_sync(image_io: io.BytesIO) -> io.BytesIO:
    image_io.seek(0)
    img = Image.open(image_io)
    img.thumbnail((512, 512))
    sticker_io = io.BytesIO()
    img.save(sticker_io, format="WEBP")
    sticker_io.seek(0)
    sticker_io.name = "sticker.webp"
    return sticker_io


@bot.add_cmd(cmd=["si", "sti"])
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

        # Check for default last.fm placeholders (The "Star" image)
        if "2a96cbd8b46e442fc41c2b86b821562f" in image_url:
            image_url = ""

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

        if message.cmd == "sti":
             sticker_io = await asyncio.to_thread(_convert_to_sticker_sync, image_io)
             # Send as new message (not reply)
             await message.reply_sticker(
                sticker=sticker_io,
                reply_markup=InlineKeyboardMarkup([buttons]),
                quote=False
            )
             await load_msg.delete()
        else:
            from pyrogram.types import InputMediaPhoto
            await load_msg.edit_media(
                media=InputMediaPhoto(media=image_io),
                reply_markup=InlineKeyboardMarkup([buttons])
            )

    except Exception as e:
        await load_msg.edit(f"Error: {e}")
