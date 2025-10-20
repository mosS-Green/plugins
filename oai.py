from app import BOT, Message, bot
from openai import AsyncOpenAI, APITimeoutError
from pyrogram.enums import ParseMode
from pyrogram.types import InputMediaPhoto
from ub_core.utils import aio
import base64
import re
import io
import asyncio

ELECTRON_API_KEY = "ek-jSL9SVU403NW4hEN3BCeiZwpnrxbYk0sFT1dcosdiyykp6bHxW"
ELECTRON_BASE_URL = "https://api.electronhub.ai/v1/"
MODEL_IMAGE = "gemini-2.5-flash-image"
MODEL_TEXT = "gpt-5-mini:free"

def parse_ai_output(choice):
    content = getattr(choice.message, "content", "")
    if not content:
        return "", None
    img_match = re.search(r'<img[^>]+src="([^"]+)"', content)
    image_url = img_match.group(1) if img_match else None
    text_only = re.sub(r"<[^>]+>", "", content).strip()
    return text_only, image_url

async def generate(client: AsyncOpenAI, prompt: str, image_file: io.BytesIO = None, model: str = MODEL_IMAGE, text_only=False):
    user_content = [{"type": "text", "text": prompt}]
    if image_file:
        image_file.seek(0)
        image_bytes = image_file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_b64}"
            }
        })
    try:
        if model == MODEL_TEXT:
            resp = await client.responses.create(model=model, input=user_content)
            text = resp.output_text.strip() if hasattr(resp, "output_text") else None
            return text, None, None
        else:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_content}],
            )
            if resp.choices:
                text, img_url = parse_ai_output(resp.choices[0])
                return text, img_url, None
            else:
                return None, None, "AI returned an empty response."
    except APITimeoutError:
        return None, None, "The request to the AI timed out. Please try again."
    except Exception as e:
        return None, None, str(e)

@bot.add_cmd(cmd="i")
async def electron_gemini(bot: BOT, message: Message):
    prompt = message.input
    if not prompt:
        await message.reply("Please provide a prompt")
        return
    wait_message = await message.reply("Generating...")
    image_file = None
    if message.reply_to_message and message.reply_to_message.photo:
        image_file = await message.reply_to_message.download(in_memory=True)
    client = AsyncOpenAI(
        api_key=ELECTRON_API_KEY,
        base_url=ELECTRON_BASE_URL,
        timeout=60.0
    )
    text, image_url, error = await generate(client, prompt, image_file, model=MODEL_IMAGE)
    if error:
        await wait_message.edit(f"Error:\n`{error}`")
        return
    if image_url:
        try:
            await wait_message.edit_media(
                media=InputMediaPhoto(
                    media=image_url,
                    caption=f"**>\n{text}<**",
                    parse_mode=ParseMode.MARKDOWN,
                )
            )
        except Exception as e:
            await wait_message.edit(f"Failed to send image: `{e}`\n\n{text}")
    elif text:
        await wait_message.edit(f"Prompt: `{prompt}`\n\nResponse: {text}", parse_mode=ParseMode.MARKDOWN)
    else:
        await wait_message.edit("The AI returned an empty response.")

@bot.add_cmd(cmd="g")
async def gpt5_text(bot: BOT, message: Message):
    prompt = message.input
    if not prompt:
        await message.reply("Please provide a prompt")
        return
    wait_message = await message.reply("Thinking...")
    image_file = None
    if message.reply_to_message and message.reply_to_message.photo:
        image_file = await message.reply_to_message.download(in_memory=True)
    client = AsyncOpenAI(
        api_key=ELECTRON_API_KEY,
        base_url=ELECTRON_BASE_URL,
        timeout=60.0
    )
    try:
        text, _, error = await asyncio.wait_for(
            generate(client, prompt, image_file, model=MODEL_TEXT, text_only=True),
            timeout=45.0
        )
    except asyncio.TimeoutError:
        await wait_message.edit("The request took too long. Try again later.")
        return
    if error:
        await wait_message.edit(f"Error:\n`{error}`")
        return
    await wait_message.edit(f"Prompt: `{prompt}`\n\nResponse: {text}", parse_mode=ParseMode.MARKDOWN)
