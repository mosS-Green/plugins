import os
from ub_core.utils import aio
from openai import AsyncOpenAI
from app import BOT, Message, bot
from pyrogram.enums import ParseMode
import asyncio

GPT4O_MODEL = "gpt-4o"
IMAGE_MODEL = "playground-v3"
IMAGE_SIZE = "1024x1024"
GPT_BASE_URL = "https://fresedgpt.space/v1"
ZUKI_BASE_URL = "https://api.zukijourney.com/v1"
ELECTRON_BASE_URL = "https://api.electronhub.top/v1/"
ZUKI_API_KEYS = [
    "zu-89d98ff1db79a5601658fdbc832f14e5",
    "zu-697462a11e0b0ef7525230309d421cfe"
]
ELECTRON_API_KEY = "ek-L7fg9Cps9nN4AqPXKwLsvn947yjaICwQfIlQisMWRkY6uw2Gz5"
GPT_API_KEY = os.environ.get("FAPI_KEY")

current_zuki_api_key_index = 0

async def send_api_request(client, method, **kwargs):
    try:
        response = await method(**kwargs)
        return response, None
    except Exception as e:
        return None, str(e)

async def generate_text_from_api(client, prompt):
    response, error = await send_api_request(client, client.chat.completions.create, model=GPT4O_MODEL, messages=[{"role": "user", "content": prompt}])
    if response:
        return response.choices[0].message.content, None
    return None, error

async def generate_image_from_api(client, prompt):
    response, error = await send_api_request(client, client.images.generate, model=IMAGE_MODEL, prompt=prompt, size=IMAGE_SIZE)
    if response:
        return response.data[0].url, None
    return None, error

async def send_image_reply(message, image_url, prompt, loading_msg):
    image_file = await aio.in_memory_dl(image_url)
    await message.reply_photo(photo=image_file, caption=f"<blockquote expandable=True><pre language=text>{prompt}</pre></blockquote>")
    await loading_msg.delete()

@bot.add_cmd(cmd="g")
async def gpt(bot: BOT, message: Message):
    if not GPT_API_KEY:
        await message.reply("GPT API key is not set.")
        return
    client = AsyncOpenAI(api_key=GPT_API_KEY, base_url=GPT_BASE_URL)
    prompt = message.input
    loading_msg = await message.reply("...")

    response_text, error = await generate_text_from_api(client, prompt)

    if response_text:
        output_text = f"4o: {response_text}"
        await loading_msg.edit(
            text=f"<blockquote expandable=True><pre language=text>{output_text}</pre></blockquote>",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await loading_msg.edit(f"Error: {error}")

@bot.add_cmd(cmd="i")
async def zuki_image(bot: BOT, message: Message):
    global current_zuki_api_key_index
    api_key = ZUKI_API_KEYS[current_zuki_api_key_index]
    base_url = ZUKI_BASE_URL
    prompt = message.input

    if not prompt:
        current_zuki_api_key_index = (current_zuki_api_key_index + 1) % len(ZUKI_API_KEYS)
        await message.reply(f"API {current_zuki_api_key_index + 1}")
        return

    loading_msg = await message.reply("....")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
    image_url, error = await generate_image_from_api(client, prompt)

    if image_url:
        await send_image_reply(message, image_url, prompt, loading_msg)
    else:
        await loading_msg.edit(f"Error: {error}")

@bot.add_cmd(cmd="ie")
async def electron_image(bot: BOT, message: Message):
    api_key = ELECTRON_API_KEY
    base_url = ELECTRON_BASE_URL
    prompt = message.input

    if not prompt:
        await message.reply("Please provide a prompt to generate an image.")
        return

    loading_msg = await message.reply("....")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
    image_url, error = await generate_image_from_api(client, prompt)

    if image_url:
        await send_image_reply(message, image_url, prompt, loading_msg)
    else:
        await loading_msg.edit(f"Error: {error}")
