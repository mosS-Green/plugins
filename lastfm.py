import json
import os
from datetime import datetime

import pylast  # type: ignore
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
    ChosenInlineResult,
)
from ub_core import BOT, Message, bot  # type: ignore
from ub_core.core.types import CallbackQuery  # type: ignore

from app import Config  # type: ignore
from .yt import get_ytm_link, ytdl_audio

_bot: BOT = bot.bot

API_KEY = None
API_SECRET = "b6774b62bca666a84545e7ff4976914a"  # this is constant, no need to fetch
FRENS = {}
lastfm_network: pylast.LastFMNetwork | None = None


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
                last_played_datetime = datetime.fromtimestamp(
                    int(last_played_timestamp)
                )
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
            else:
                return {"error": "No track currently playing or recently played."}

        ytm_link = await get_ytm_link(f"{track_name} by {artist_name}")
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
    user = message.from_user.username
    await send_now_playing(bot, message, user)


async def parse_lastfm_json(username):
    lastfm_data = await lastfm_fetch(username)

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
    update: Message | CallbackQuery | ChosenInlineResult,
    user: str = None,
    inline_message_id=None,
):
    username = FRENS[user]["username"]
    first_name = FRENS[user]["first_name"]
    if not username:
        return await update.edit("u fren, no no")

    if isinstance(update, Message):
        load_msg = await update.reply("<code>...</code>")
    elif isinstance(update, CallbackQuery):
        load_msg = await update.edit("<code>...</code>")
    elif isinstance(update, ChosenInlineResult):
        load_msg = await bot.edit_inline_text(
            inline_message_id=inline_message_id, text="<code>...</code>"
        )
    else:
        load_msg = None

    song, artist, is_now_playing, play_count, ytm_link, last_played_string = (
        await parse_lastfm_json(username)
    )

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

    if load_msg and (isinstance(update, Message) or isinstance(update, CallbackQuery)):
        await load_msg.edit(
            text=sentence,
            parse_mode=ParseMode.MARKDOWN,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=markup,
        )
    elif isinstance(update, ChosenInlineResult):  # For inline query, edit inline text
        await bot.edit_inline_text(
            inline_message_id=inline_message_id,
            text=sentence,
            parse_mode=ParseMode.MARKDOWN,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=markup,
        )


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
                input_message_content=InputTextMessageContent("..."),
                reply_markup=InlineKeyboardMarkup([buttons]),
            )
        ]
    await inline_query.answer(results=result, cache_time=0, is_personal=True)


@_bot.on_chosen_inline_result(group=4)
async def chosen_np_inline(client: BOT, chosen_inline_result: ChosenInlineResult):
    user = chosen_inline_result.from_user.username
    inline_message_id = chosen_inline_result.inline_message_id
    await send_now_playing(
        client, chosen_inline_result, user, inline_message_id=inline_message_id
    )
