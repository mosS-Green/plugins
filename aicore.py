import copy
import json
import asyncio
import os
import shutil
import time
from mimetypes import guess_type

from pyrogram.types.messages_and_media import Audio, Photo, Video, Voice
from ub_core.utils import get_tg_media_details

from app import BOT, Config, Message, bot
from app.plugins.ai.models import Settings


THINK_CONFIG = copy.deepcopy(Settings.CONFIG)
THINK_CONFIG.system_instruction = (
    "Write a lengthy, well-structured, and easy-to-read answer."
    "You are writing on Telegra.ph, which allows only <a>, <blockquote>, <br>, <em>,"
    "<figure>, <h3>, <h4>, <img>, <p>, and <strong> elements."
    "Use these tags properly, and only write the body part as it is rendered automatically."
)
THINK_CONFIG.temperature = 0.7
THINK_CONFIG.max_output_tokens = 60000

THINK = {"model": "gemini-2.0-flash-thinking-exp-01-21", "config": THINK_CONFIG}
QUICK = {"model": "gemini-2.0-flash-lite-preview-02-05", "config": THINK_CONFIG}


PROMPT_MAP = {
    Video: "Summarize video and audio from the file",
    Photo: "Summarize the image file",
    Voice: (
        "Transcribe this audio. "
        "Use ONLY english alphabet to express hindi. "
        "Do not translate."
        "Do not write anything extra than the transcription. Use proper punctuation, and formatting."
        "\n\nIMPORTANT - YOU ARE ONLY ALLOWED TO USE ENGLISH ALPHABET."
    ),
}
PROMPT_MAP[Audio] = PROMPT_MAP[Voice]


@bot.add_cmd(cmd="fh")
async def init_task(bot=bot, message=None):
    past_message_id = int(os.environ.get("PAST_MESSAGE_ID"))

    past_message = await bot.get_messages(
        chat_id=Config.LOG_CHAT, message_ids=past_message_id
    )

    json_data = json.loads(past_message.text)

    LEAF_MODEL = copy.deepcopy(Settings)
    LEAF_CONFIG = LEAF_MODEL.CONFIG
    LEAF_CONFIG.system_instruction = json_data["text"]
    LEAF_CONFIG.temperature = 0.8
    LEAF_CONFIG.max_output_tokens = 8192

    global LEAF
    LEAF = {"model": LEAF_MODEL.MODEL,"config": LEAF_CONFIG}
    
    if message is not None:
        await message.reply("Done.", del_in=2)


async def ask_ai(prompt: str, query: Message | None, quote: bool = False, **kwargs) -> str:
    media = None
    prompts = [prompt]

    if query:
        prompts = [str(query.text), prompt or "answer"]
        media = get_tg_media_details(query)    

    if media is not None:
        if getattr(media, "file_size", 0) >= 1048576 * 25:
            return "Error: File Size exceeds 25mb."

        prompt = prompt.strip() or PROMPT_MAP.get(
            type(media), "Analyse the file and explain."
        )

        download_dir = os.path.join("downloads", str(time.time())) + "/"
        downloaded_file: str = await query.download(download_dir)

        uploaded_file = await async_client.files.upload(
            file=downloaded_file,
            config={
            "mime_type": getattr(media, "mime_type", guess_type(downloaded_file)[0])
            },
        )

        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(5)
            uploaded_file = await async_client.files.get(name=uploaded_file.name)

        prompts = [uploaded_file, prompt]
        
        shutil.rmtree(download_dir, ignore_errors=True)
            
    response = await async_client.models.generate_content(**kwargs, contents=prompts)
    ai_response = get_text(response, quoted=quote)
    
    return ai_response


def get_text(response, quoted: bool = False):
    candidate = response.candidates[0]
  
    text = "\n".join([part.text for part in candidate.content.parts])
  
    final_text = text.strip()
  
    return f"**>\n{final_text}<**" if quoted and "```" not in final_text else final_text
