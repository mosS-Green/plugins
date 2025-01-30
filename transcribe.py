from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from ub_core import BOT, Message, bot
from pyrogram.enums import ParseMode

from app.plugins.ai.media_query import handle_media
from app.plugins.ai.models import MODEL

_bot: BOT = bot.bot


@_bot.on_message(filters=filters.audio | filters.voice)
async def auto_transcribe(bot: BOT, message: Message):
    button = [InlineKeyboardButton(text="Transcribe", callback_data="auto_trs")]
    await message.reply(
        text="Audio File Detected!", reply_markup=InlineKeyboardMarkup([button])
    )


@_bot.on_callback_query(filters=filters.regex("auto_trs"))
async def transcribe(bot: BOT, callback_query: CallbackQuery):
    await callback_query.edit_message_text("transcribing...")
    transcribed_str = await handle_media(prompt="Transcribe this audio. Use ONLY english alphabet to express hindi. Do not translate. Do not write anything extra than the transcription.\n\nIMPORTANT - YOU ARE ONLY ALLOWED TO USE ENGLISH ALPHABET.", media_message=callback_query.message.reply_to_message, model=MODEL)
    await callback_query.edit_message_text(
        text=f"<blockquote expandable=True><pre language=text>{transcribed_str}</pre></blockquote>",
        parse_mode=ParseMode.MARKDOWN,
    )
