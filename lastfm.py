import json
import os
import re
import aiohttp
from datetime import datetime

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    LinkPreviewOptions,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    ChosenInlineResult as InlineResultUpdate,  # used by our InlineResult wrapper
)
from ub_core import BOT, Message, bot  # type: ignore
from ub_core.core.types import CallbackQuery, InlineResult  # type: ignore

from app import Config  # type: ignore
from app.modules.yt import get_ytm_link, ytdl_audio

_bot: BOT = bot.bot

API_KEY = None
API_SECRET = "b6774b62bca666a84545e7ff4976914a"  # this is constant, no need to fetch
FRENS = {}
BASE_URL = "http://ws.audioscrobbler.com/2.0/"


@bot.add_cmd(cmd="fren")
async def init_task(bot=bot, message=None):
    msgs = await bot.get_messages(chat_id=Config.LOG_CHAT, message_ids=[4027, 4025])
    lastfm_names, apikey_msg = msgs

    global FRENS, API_KEY
    FRENS = json.loads(lastfm_names.text)
    API_KEY = apikey_msg.text.strip()

    if message is not None:
        await message.reply("Done.", del_in=2)


async def lastfm_fetch(username):
    """Fetches Last.fm data for a given username using the Last.fm API directly."""
    if not API_KEY:
        return {"error": "Last.fm API key not initialized."}

    try:
        async with aiohttp.ClientSession() as session:
            # First check what the user is currently playing
            params = {
                "method": "user.getrecenttracks",
                "user": username,
                "api_key": API_KEY,
                "format": "json",
                "limit": 1,
            }

            async with session.get(BASE_URL, params=params) as response:
                if response.status != 200:
                    return {"error": f"Last.fm API Error: HTTP {response.status}"}

                data = await response.json()

                if "error" in data:
                    return {"error": f"Last.fm API Error: {data['message']}"}

                track_list = data.get("recenttracks", {}).get("track", [])
                if not track_list:
                    return {"error": "No track currently playing or recently played."}

                track = track_list[0]
                is_now_playing = (
                    "@attr" in track and track["@attr"].get("nowplaying") == "true"
                )
                artist_name = track["artist"]["#text"]
                track_name = track["name"]

                # Get play count for this track
                params = {
                    "method": "track.getInfo",
                    "api_key": API_KEY,
                    "artist": artist_name,
                    "track": track_name,
                    "username": username,
                    "format": "json",
                }

                async with session.get(BASE_URL, params=params) as track_response:
                    if track_response.status != 200:
                        play_count = "0"  # Default if we can't fetch play count
                    else:
                        track_data = await track_response.json()
                        if "error" in track_data:
                            play_count = "0"
                        else:
                            play_count = track_data.get("track", {}).get(
                                "userplaycount", "0"
                            )

                last_played_string = None
                if not is_now_playing and "date" in track:
                    last_played_timestamp = int(track["date"]["uts"])
                    last_played_datetime = datetime.fromtimestamp(last_played_timestamp)
                    now = datetime.now()
                    time_diff = now - last_played_datetime

                    if time_diff.days > 0:
                        last_played_string = f"{time_diff.days} days ago"
                    elif time_diff.seconds // 3600 > 0:
                        last_played_string = f"{time_diff.seconds // 3600} hours ago"
                    elif time_diff.seconds // 60 > 0:
                        last_played_string = f"{time_diff.seconds // 60} minutes ago"
                    else:
                        last_played_string = "just now"

                ytm_link = await get_ytm_link(f"{track_name} by {artist_name}")
                return {
                    "track_name": track_name,
                    "artist_name": artist_name,
                    "is_now_playing": is_now_playing,
                    "play_count": play_count,
                    "ytm_link": ytm_link,
                    "last_played_string": last_played_string,
                }

    except aiohttp.ClientError as e:
        return {"error": f"Network Error: {e}"}
    except Exception as e:
        return {"error": f"Unknown error: {e}"}


async def parse_lastfm_json(username):
    lastfm_data = await lastfm_fetch(username)

    if "error" in lastfm_data:
        return None, None, None, None, None, None

    track_name = lastfm_data["track_name"]
    artist = lastfm_data["artist_name"]
    is_now_playing = lastfm_data["is_now_playing"]
    play_count = f"{lastfm_data['play_count']} plays"
    ytm_link = lastfm_data["ytm_link"]
    last_played_string = lastfm_data["last_played_string"]

    song = f"**__[{track_name}]({ytm_link})__**"
    return song, artist, is_now_playing, play_count, ytm_link, last_played_string


async def send_now_playing(
    bot: BOT,
    message: Message | CallbackQuery | InlineResult,
    user: str = None,
):
    # Use .reply for all message types
    load_msg = await message.reply("<code>...</code>")

    if user not in FRENS:
        await load_msg.edit("ask Leaf wen?")
        return

    username = FRENS[user]["username"]
    first_name = FRENS[user]["first_name"]
    if not username:
        await load_msg.edit("ask Leaf wen?")
        return

    parsed_data = await parse_lastfm_json(username)
    if not parsed_data[0]:  # Check if parsing returned None
        await load_msg.edit(f"Error fetching data for {username}")
        return

    song, artist, is_now_playing, play_count, ytm_link, last_played_string = parsed_data

    if is_now_playing:
        vb = "leafing" if first_name == "Leaf" else "vibing"
        sentence = f"{first_name} is {vb} to {song} by __{artist}__."
    else:
        sentence = f"{first_name} last listened to {song} by __{artist}__."
        if last_played_string:
            sentence += f" ({last_played_string})"

    buttons = [
        InlineKeyboardButton(text="♫", callback_data=f"y_{ytm_link}"),
        InlineKeyboardButton(text=play_count, callback_data="nice"),
        InlineKeyboardButton(text="↻", callback_data=f"r_{user}"),
    ]
    markup = InlineKeyboardMarkup([buttons])

    await load_msg.edit(
        text=sentence,
        parse_mode=ParseMode.MARKDOWN,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=markup,
    )


@bot.add_cmd(cmd="st")
async def sn_now_playing(bot: BOT, message: Message):
    user = message.from_user.username
    await send_now_playing(bot, message, user)


@_bot.on_callback_query(filters=filters.regex("^y_"))
async def song_ytdl(bot: BOT, callback_query: CallbackQuery):
    ytm_link = callback_query.data[2:]
    sentence = callback_query.message.text.markdown if callback_query.message else ""
    user = callback_query.message.reply_markup.inline_keyboard[0][-1].callback_data[2:]
    play_count = callback_query.message.reply_markup.inline_keyboard[0][1].text

    await callback_query.edit("<code>abra...</code>")

    audio_path, info = await ytdl_audio(ytm_link)

    buttons = [
        InlineKeyboardButton(text=play_count, callback_data=f"w_{user}"),
        InlineKeyboardButton(text="↻", callback_data=f"r_{user}"),
    ]

    load_msg = await callback_query.edit("<code>kadabra...</code>")

    await load_msg.edit_message_media(
        InputMediaAudio(
            media=audio_path,
            caption=sentence,
            parse_mode=ParseMode.MARKDOWN,
        ),
        reply_markup=InlineKeyboardMarkup([buttons]),
    )
    os.remove(audio_path)


@_bot.on_callback_query(filters=filters.regex("^r_"))
async def refresh_nowplaying(bot: BOT, callback_query: CallbackQuery):
    user = callback_query.data[2:]
    if user in FRENS:
        await send_now_playing(bot, callback_query, user)
    else:
        await callback_query.answer("ask Leaf wen?", show_alert=True)


@_bot.on_inline_query(group=4)
async def inline_now_playing(bot: BOT, inline_query: InlineQuery):
    user = inline_query.from_user.username
    buttons = [InlineKeyboardButton(text="Status", callback_data=f"r_{user}")]
    if user not in FRENS:
        result = [
            InlineQueryResultArticle(
                title="Ask leaf wen?",
                input_message_content=InputTextMessageContent("u fren, no no"),
            )
        ]
    else:
        result = [
            InlineQueryResultArticle(
                title="Now Playing",
                input_message_content=InputTextMessageContent("Now Playing..."),
                reply_markup=InlineKeyboardMarkup([buttons]),
            )
        ]
    await inline_query.answer(results=result, cache_time=0, is_personal=True)


def regex_empty_query_filter(_, __, InlineResultUpdate):
    return re.fullmatch(r"^\s*$", InlineResultUpdate.query) is not None


@_bot.on_chosen_inline_result(filters=filters.create(regex_empty_query_filter))
async def chosen_inline_handler(bot: BOT, chosen_result: InlineResultUpdate):
    inline_result = InlineResult(chosen_result)
    user = inline_result.from_user.username
    await send_now_playing(_bot, inline_result, user)
