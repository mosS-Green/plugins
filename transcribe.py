import asyncio

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from ub_core import BOT, Message, bot

from .aicore import ask_ai, MODEL

_bot: BOT = bot.bot


async def _transcribe_with_retry(message: Message, edit_msg: Message):
    for _ in range(2):
        try:
            transcribed_str = await ask_ai(
                prompt="",
                query=message,
                quote=True
                **MODEL["DEFAULT"],
            )
            await edit_msg.edit_text(
                text=transcribed_str, parse_mode=ParseMode.MARKDOWN
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
    await _transcribe_with_retry(
        callback_query.message.reply_to_message, callback_query.message
    )
