import asyncio
import glob
import mimetypes
import os
import shutil
import time
from io import BytesIO

import google.generativeai as genai
from google.ai import generativelanguage as glm
from ub_core.utils import run_shell_cmd

from app import BOT, Message, bot
from app.plugins.ai.media_query import PHOTO_EXTS, VIDEO_EXTS, AUDIO_EXTS, download_file, handle_video
from .models import MEDIA_MODEL, get_response_text

@bot.add_cmd(cmd="vx")
async def video_to_text(bot: BOT, message: Message):
    """
    CMD: vx
    INFO: Convert Video info to text.
    USAGE: .vx [reply to video file] summarise the video file.
    """
    prompt = message.input
    reply = message.replied
    message_response = await message.reply("...")

    if not (prompt and reply and (reply.video or reply.animation)):
        await message_response.edit("Reply to a video and give a prompt.")
        return

    ai_response_text = await handle_video(prompt, reply)
    await message_response.edit(ai_response_text)


async def handle_audio(prompt: str, message: Message, model: genai.GenerativeModel):
    audio = message.document or message.audio or message.voice
    file_name = getattr(audio, "file_name", "audio.aac")

    file_path, download_dir = await download_file(file_name, message)
    file_response = genai.upload_file(path=file_path)

    response = await model.generate_content_async([prompt, file_response])
    response_text = get_response_text(response)

    genai.delete_file(name=file_response.name)
    shutil.rmtree(file_path, ignore_errors=True)

    return response_text


async def handle_photo(prompt: str, message: Message, model: genai.GenerativeModel):
    file = await message.download(in_memory=True)

    mime_type, _ = mimetypes.guess_type(file.name)
    if mime_type is None:
        mime_type = "image/unknown"

    image_blob = glm.Blob(mime_type=mime_type, data=file.getvalue())
    response = await model.generate_content_async([prompt, image_blob])
    return get_response_text(response)
