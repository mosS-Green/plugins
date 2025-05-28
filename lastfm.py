import os
from datetime import datetime

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputMediaAudio,
    InputTextMessageContent,
    LinkPreviewOptions,
    User,
)
from ub_core import BOT, CustomDB, Message, bot
from ub_core.core.handlers.dispatcher import make_custom_object
from ub_core.core.types import CallbackQuery, InlineResult
from ub_core.utils import aio, extract_user_data

from .yt import get_ytm_link, ytdl_audio

_bot: BOT = bot.bot

LASTFM_DB = CustomDB["lastfm_users"]
FRENS = set()
INLINE_CACHE: set[int] = set()

BASE_URL = "http://ws.audioscrobbler.com/2.0/"
API_KEY = os.getenv("LASTFM_KEY")
API_SECRET = "b6774b62bca666a84545e7ff4976914a"  # this is constant, no need to fetch


@bot.add_cmd(cmd="fren")
async def init_task(_=bot, message=None):
    async for u in LASTFM_DB.find():
        FRENS.add(u["_id"])

    if message is not None:
        await message.reply("Done.", del_in=2)


@bot.add_cmd(cmd="afren")
async def add_fren(bot: BOT, message: Message):
    response = await message.reply("Extracting User info...")

    user, lastfm_username = await message.extract_user_n_reason()

    if not isinstance(user, User):
        await response.edit("unable to extract user info.")
        return

    if not lastfm_username:
        await response.edit("LasfFM username not found.")
        return

    await LASTFM_DB.add_data(
        {"_id": user.id, **extract_user_data(user), "lastfm_username": lastfm_username}
    )
    FRENS.add(user.id)
    await response.edit(f"#LASTFM\n{user.mention} added to frens.")
    await response.log()


@bot.add_cmd(cmd="dfren")
async def add_fren(bot: BOT, message: Message):
    response = await message.reply("Extracting User info...")

    user, _ = await message.extract_user_n_reason()

    if isinstance(user, User):
        user_id = user.id
        name = user.first_name
    else:
        user_id = int(message.input.strip())
        name = user_id

    FRENS.discard(user_id)

    deleted = await LASTFM_DB.delete_data(id=user_id)

    if deleted:
        resp_str = f"{name} no longer fren."
    else:
        resp_str = f"{name} was never a fren."

    await response.edit(resp_str)
    if deleted:
        await response.log()


@bot.add_cmd(cmd="vfren")
async def add_fren(bot: BOT, message: Message):
    output: str = ""
    total = 0

    async for user in LASTFM_DB.find():
        total += 1
        output += f"\n<b>• {user['name']}</b>"

        if "-id" in message.flags:
            output += f"\n  ID: <code>{user['_id']}</code>"

    if not total:
        await message.reply("You don't have any frens.")
        return

    output: str = f"List of <b>{total}</b> FRENS:\n{output}"
    await message.reply(output, del_in=30, block=True)


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
        return f"{time_diff.days} days ago"
    elif time_diff.seconds // 3600 > 0:
        return f"{time_diff.seconds // 3600} hours ago"
    elif time_diff.seconds // 60 > 0:
        return f"{time_diff.seconds // 60} minutes ago"
    else:
        return "just now"


async def get_now_playing_track(username) -> dict[str, str] | str:
    """Fetches Last.fm data for a given username using the Last.fm API directly."""
    if not API_KEY:
        return "Last.fm API key not initialized."

    track_list = await fetch_track_list(username=username)

    if isinstance(track_list, str):
        return track_list

    track_info: dict = track_list[0]
    is_now_playing = track_info.get("@attr", {}).get("nowplaying") == "true"
    artist_name = track_info["artist"]["#text"]
    track_name = track_info["name"]
    play_count = await fetch_song_play_count(
        artist=artist_name, track=track_name, username=username
    )

    if not is_now_playing and "date" in track_info:
        last_played_time = format_time(
            datetime.fromtimestamp(int(track_info["date"]["uts"]))
        )
    else:
        last_played_time = ""

    # noinspection PyUnresolvedReferences
    ytm_link = await get_ytm_link(f"{track_name} by {artist_name}")

    return {
        "song_href_html": f"<b><i><a href='{ytm_link}'>{track_name}</a></b></i>",
        "song_href_md": f"**__[{track_name}]({ytm_link})__**",
        "track_name": track_name,
        "artist_name": artist_name,
        "is_now_playing": is_now_playing,
        "play_count": play_count,
        "ytm_link": ytm_link,
        "last_played_time": last_played_time,
    }


async def get_fren_info(user_id) -> dict:
    return await LASTFM_DB.find_one({"_id": user_id}) or {}


@bot.add_cmd(cmd="st")
@_bot.on_chosen_inline_result(
    filters=filters.create(
        lambda _, __, u: u.from_user and u.from_user.id in INLINE_CACHE
    )
)
async def send_now_playing(
    bot: BOT, update: Message | CallbackQuery | InlineResult, user_id: int = None
):
    update = make_custom_object(update)

    user_id = user_id or update.from_user.id

    if user_id not in FRENS:
        if isinstance(update, CallbackQuery):
            await update.answer(text="ask Leaf wen?", show_alert=True)
        else:
            await update.reply("ask Leaf wen?")
        return

    INLINE_CACHE.discard(user_id)

    load_msg = await update.reply("<code>...</code>")

    fren_info = await get_fren_info(user_id)
    username = fren_info["lastfm_username"]
    first_name = fren_info["name"]

    parsed_data = await get_now_playing_track(username)

    if isinstance(parsed_data, str):
        await load_msg.edit(parsed_data)
        return

    action_name = "leafing" if first_name == "Leaf" else "vibing"
    action_type = "is" if parsed_data["is_now_playing"] else "was"
    sentence = (
        f"{first_name} "
        f"{action_type} "
        f"{action_name} "
        f"to {parsed_data['song_href_md']} "
        f"by __{parsed_data['artist_name']}__."
    )

    if parsed_data["last_played_time"]:
        sentence += f" ({parsed_data['last_played_time']})"

    try:
        yt_shortcode = parsed_data["ytm_link"].split("=")[1]
    except IndexError:
        yt_shortcode = ""

    buttons = [
        InlineKeyboardButton(
            text="♫",
            callback_data=f"y_{yt_shortcode}|{parsed_data['play_count']}|{user_id}",
        ),
        InlineKeyboardButton(
            text=f"{parsed_data['play_count']} plays", callback_data="-_-"
        ),
        InlineKeyboardButton(text="↻", callback_data=f"r_{user_id}"),
    ]

    markup = InlineKeyboardMarkup([buttons])

    await load_msg.edit(
        text=sentence,
        parse_mode=ParseMode.MARKDOWN,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=markup,
    )


@_bot.on_callback_query(filters=filters.regex("^y_"))
async def song_ytdl(bot: BOT, callback_query: CallbackQuery):
    await callback_query.edit("<code>Uploa...wait for it...</code>")

    shortcode, play_count, user_id = callback_query.data[2:].split("|")

    caption = callback_query.message.text.html if callback_query.message else None

    audio_path, info = await ytdl_audio(
        f"https://music.youtube.com/watch?v={shortcode}"
    )

    await callback_query.edit("<code>ding! Uploading.</code>")

    buttons = [
        InlineKeyboardButton(text=f"{play_count} plays", callback_data=f"-_-"),
        InlineKeyboardButton(text="↻", callback_data=f"r_{user_id}"),
    ]
    await callback_query.edit_media(
        media=InputMediaAudio(
            caption=caption,
            media=audio_path,
            parse_mode=ParseMode.HTML,
            thumb=await aio.thumb_dl(info.get("thumbnail")),
        ),
        reply_markup=InlineKeyboardMarkup([buttons]),
    )
    os.remove(audio_path)


@_bot.on_callback_query(filters=filters.regex("^r_"))
async def refresh_nowplaying(bot: BOT, callback_query: CallbackQuery):
    user_id = int(callback_query.data[2:])
    await send_now_playing(bot, callback_query, user_id)


@_bot.on_inline_query(filters=filters.create(lambda _, __, iq: not iq.query), group=4)
async def inline_now_playing(bot: BOT, inline_query: InlineQuery):
    user_id = inline_query.from_user.id
    if user_id not in FRENS:
        result = [
            InlineQueryResultArticle(
                title="Ask leaf wen?",
                input_message_content=InputTextMessageContent("u fren, no no"),
            )
        ]
    else:
        INLINE_CACHE.add(user_id)
        buttons = [InlineKeyboardButton(text="Status", callback_data=f"r_{user_id}")]
        result = [
            InlineQueryResultArticle(
                title="Now Playing",
                input_message_content=InputTextMessageContent("Now Playing..."),
                reply_markup=InlineKeyboardMarkup([buttons]),
            )
        ]

    await inline_query.answer(results=result, cache_time=0, is_personal=True)
