import asyncio
import json
import os

import pylast
from app import Config
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    LinkPreviewOptions,
)
from ub_core import BOT, Message, bot

from .yt import get_ytm_link, ytdl_audio

_bot: BOT = bot.bot

API_KEY = None
API_SECRET = "b6774b62bca666a84545e7ff4976914a"  # this is constant, no need to fetch
FRENS = {}
lastfm_network = None


@bot.add_cmd(cmd="fren")
async def init_task(bot=bot, message=None):
    msgs = await bot.get_messages(chat_id=Config.LOG_CHAT, message_ids=[4027, 4025])
    lastfm_names, apikey_msg = msgs

    global FRENS, API_KEY, lastfm_network
    FRENS = json.loads(lastfm_names.text)
    API_KEY = apikey_msg.text.strip()

    if API_KEY:
        lastfm_network = pylast.LastFMNetwork(
            api_key=API_KEY,
            api_secret=API_SECRET,
        )

    if message is not None:
        await message.reply("Done.", del_in=2)


async def lastfm_fetch(username):
    """Fetches Last.fm data for a given username using pylast."""
    if not lastfm_network:
        return {"error": "Last.fm API key not initialized."}
    try:
        user = pylast.User(username, lastfm_network)
        now_playing = user.get_now_playing()

        if now_playing:
            track = now_playing
            artist_name = track.artist.name
            track_name = track.title
            c_track = pylast.Track(
                artist=artist_name,
                title=track_name,
                network=lastfm_network,
                username=username,
            )
            play_count = c_track.get_userplaycount()
            is_now_playing = True
            last_played_string = None
        else:
            recent_tracks = user.get_recent_tracks(limit=1)
            if recent_tracks:
                last_played_item = recent_tracks[0]  # Get the pylast.PlayedTrack object
                track = last_played_item.track  # Get the pylast.Track object
                artist_name = track.artist.name
                track_name = track.title
                c_track = pylast.Track(
                    artist=artist_name,
                    title=track_name,
                    network=lastfm_network,
                    username=username,
                )
                play_count = c_track.get_userplaycount()
                is_now_playing = False
                last_played_timestamp = last_played_item.timestamp
                last_played_string = f"<t:{int(last_played_timestamp)}:R>"
            else:
                return {"error": "No track currently playing or recently played."}

        ytm_link = await asyncio.to_thread(
            get_ytm_link, f"{track_name} by {artist_name}"
        )
        return {
            "track_name": track_name,
            "artist_name": artist_name,
            "is_now_playing": is_now_playing,
            "play_count": play_count,
            "ytm_link": ytm_link,
            "last_played_string": last_played_string,
        }

    except pylast.WSError as e:
        return {"error": f"Last.fm API Error: {e}"}
    except pylast.NetworkError as e:
        return {"error": f"Network Error: {e}"}
    except Exception as e:
        return {"error": f"Unknown error: {e}"}


@bot.add_cmd(cmd="st")
async def sn_now_playing(bot: BOT, message: Message):
    load_msg = await message.reply("<code>...</code>")
    user = message.from_user.username
    await fn_now_playing(user, load_msg)


async def fn_now_playing(user: str, load_msg):
    username = FRENS[user]["username"]
    first_name = FRENS[user]["first_name"]

    if not username:
        return await load_msg.edit("u fren, no no")

    lastfm_data = await lastfm_fetch(username)

    if "error" in lastfm_data:
        return await load_msg.edit(lastfm_data["error"])

    track_name = lastfm_data["track_name"]
    artist = lastfm_data["artist_name"]
    is_now_playing = lastfm_data["is_now_playing"]
    play_count = lastfm_data["play_count"]
    ytm_link = lastfm_data["ytm_link"]
    last_played_string = lastfm_data["last_played_string"]

    song = f"**__[{track_name}]({ytm_link})__**"

    if is_now_playing:
        vb = "leafing" if first_name == "Leaf" else "vibing"
        sentence = f"{first_name} is {vb} to {song} by __{artist}__."
    else:
        sentence = f"{first_name} last listened to {song} by __{artist}__."
        if last_played_string:
            sentence += f" ({last_played_string})"

    buttons = [
        InlineKeyboardButton(text="♫", callback_data=f"y_{ytm_link}"),
        InlineKeyboardButton(text=f"{play_count} plays", callback_data=""),
        InlineKeyboardButton(text="↻", callback_data=f"r_{user}"),
    ]

    await load_msg.edit(
        text=sentence,
        parse_mode=ParseMode.MARKDOWN,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=InlineKeyboardMarkup([buttons]),
    )


@_bot.on_callback_query(filters=filters.regex("^y_"))
async def song_ytdl(bot: BOT, callback_query: CallbackQuery):
    ytm_link = callback_query.data[2:]

    audio_path, info = await ytdl_audio(ytm_link)
    sentence = callback_query.message.text

    buttons = [
        InlineKeyboardButton(text=":)", url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ]

    await callback_query.message.edit_media(
        InputMediaAudio(
            media=audio_path,
            caption=sentence,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([buttons]),
        )
    )
    os.remove(audio_path)


@_bot.on_callback_query(filters=filters.regex("^r_"))
async def refresh_nowplaying(bot: BOT, callback_query: CallbackQuery):
    await callback_query.answer("Refreshing...")
    user = callback_query.data[2:]
    load_msg = await callback_query.edit("<code>...</code>")
    await fn_now_playing(user, load_msg)
