import json
import asyncio
import os

from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
from pyrogram import filters

from app import Config
from ub_core import BOT, Message, bot
from ub_core.utils import aio

from .aicore import ask_ai, MODEL
from .yt import get_ytm_link, ytdl_audio, ytdl_video

_bot: BOT = bot.bot


@bot.add_cmd(cmd="fren")
async def init_task(bot=bot, message=None):
    msgs = await bot.get_messages(chat_id=Config.LOG_CHAT, message_ids=[4027, 4025])
    lastfm_names, apikey = msgs

    global FRENS, API_KEY
    FRENS = json.loads(lastfm_names.text)
    API_KEY = apikey.text.strip()

    if message is not None:
        await message.reply("Done.", del_in=2)


@bot.add_cmd(cmd="st")
async def sn_now_playing(bot: BOT, message: Message):
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
        (
            track
            for track in tracks
            if track.get("@attr", {}).get("nowplaying") == "true"
        ),
        None,
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
    sentence = await ask_ai(prompt=prompts, **MODEL["QUICK"])

    buttons = [
        InlineKeyboardButton(text="♫", callback_data=f"y_{ytm_link_result}"),
        InlineKeyboardButton(text="▷", callback_data=f"v_{ytm_link_result}"),
        InlineKeyboardButton(text="↻", callback_data="r_refresh")
    ]
    
    await load_msg.edit(
        text=sentence,
        parse_mode=ParseMode.MARKDOWN,
        disable_preview=True,
        reply_markup=InlineKeyboardMarkup([buttons])
    )


@_bot.on_callback_query(filters=filters.regex("^y_"))
async def song_ytdl(bot: BOT, callback_query: CallbackQuery):
    ytm_link = callback_query.data[2:]

    audio_path, info = await asyncio.to_thread(ytdl_audio, ytm_link)
    
    await bot.send_audio(
        chat_id=callback_query.message.chat.id,
        audio=audio_path,
        caption=info.get("title", "Song"),
    )
    os.remove(audio_path)
    await callback_query.answer()


@_bot.on_callback_query(filters=filters.regex("^v_"))
async def video_ytdl(bot: BOT, callback_query: CallbackQuery):
    link = callback_query.data[2:]
    video_path, info = await asyncio.to_thread(ytdl_video, link)
    await bot.send_video(
        chat_id=callback_query.message.chat.id,
        video=video_path,
        caption=info.get('title', 'Video'),
        parse_mode=ParseMode.HTML,
    )
    os.remove(video_path)
    await callback_query.answer()


@_bot.on_callback_query(filters=filters.regex("^r_"))
async def refresh_nowplaying(bot: BOT, callback_query: CallbackQuery):
    await callback_query.answer()
    await sn_now_playing(bot, callback_query.message)
