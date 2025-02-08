from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from ub_core import BOT, Message, bot
from pyrogram.enums import ParseMode

from google.genai.chats import AsyncChat
from app.plugins.ai.media_query import handle_media
from app.plugins.ai.models import (
    Settings,
    async_client,
    get_response_text,
    run_basic_check,
)
import asyncio

_bot: BOT = bot.bot

async def _transcribe_with_retry(message: Message, edit_msg: Message):
    for _ in range(2):
        try:
            transcribed_str = await handle_media(
                prompt="Transcribe this audio. Use ONLY english alphabet to express hindi. Do not translate. Do not write anything extra than the transcription.\n\nIMPORTANT - YOU ARE ONLY ALLOWED TO USE ENGLISH ALPHABET.",
                media_message=message, 
                **Settings.get_kwargs()
        )
            await edit_msg.edit_text(
                text=f"<blockquote expandable=True><pre language=text>{transcribed_str}</pre></blockquote>",
            )
            return True
        except Exception:
            await asyncio.sleep(3)
    await edit_msg.edit_text("Error")
    return False


@_bot.on_message(filters=filters.audio | filters.voice)
async def auto_transcribe(bot: BOT, message: Message):
    if message.chat.id == -1001875925090:
        edit_msg = await message.reply("transcribing...")
        await _transcribe_with_retry(message, edit_msg)
    else:
        button = [InlineKeyboardButton(text="Transcribe", callback_data="auto_trs")]
        await message.reply(
            text="Audio File Detected!", reply_markup=InlineKeyboardMarkup([button])
        )


@_bot.on_callback_query(filters=filters.regex("auto_trs"))
async def transcribe(bot: BOT, callback_query: CallbackQuery):
    await callback_query.edit_message_text("transcribing...")
    await _transcribe_with_retry(callback_query.message.reply_to_message, callback_query.message)
