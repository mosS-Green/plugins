import os
from ub_core.utils import aio
from openai import OpenAI
from app import BOT, Message, bot
import asyncio

apikey = os.environ.get("FAPI_KEY")

client = OpenAI(api_key = apikey, base_url = "https://fresedgpt.space/v1")

@bot.add_cmd(cmd="g")
async def gpt(bot: BOT, message: Message):
    prompt = message.input

    response = await asyncio.to_thread(client.chat.completions.create,
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    response_text = f"4o: {response.choices[0].message.content}"
    await message.reply(response_text)


@bot.add_cmd(cmd="img")
async def generate_image(bot: BOT, message: Message):
    prompt = message.input

    response = await asyncio.to_thread(client.images.generate,
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024"
    )

    image_url = response.data[0].url
    image_file = await aio.in_memory_dl(image_url)

    await message.reply_photo(photo=image_file)
