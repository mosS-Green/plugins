from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from ub_core import BOT, Message, bot

from app.plugins.ai.media_query import handle_audio
from .models import MEDIA_MODEL

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
    transcribed_str = await handle_audio(prompt="Transcribe this audio. Use english alphabet to express hindi. Do not translate. Do not write anything extra than the transcription. Have good formatting.", message=callback_query.message.reply_to_message)
    await callback_query.edit_message_text(transcribed_str)
