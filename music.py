import json
import asyncio
import aiofiles
from app import BOT, Message, bot
from ub_core.utils import aio
from .oai import GPT_API_KEY

CREATE_URL = "https://fresedgpt.space/v1/music/generation"
STATUS_URL = "https://fresedgpt.space/v1/music/status/"

HEADERS = {
    'Authorization': f"'{GPT_API_KEY}'",
    'Content-Type': 'application/json',
}

@bot.add_cmd(cmd="sing")
async def generate_music(bot: BOT, message: Message):
    session = aio.session
    payload = {
        "prompt": message.input,
        "make_instrumental": False,
    }

    try:
        response = await session.post(
          CREATE_URL, headers=HEADERS, json=payload
        )
        response.raise_for_status()
        output = await response.json()
        request_id = output.get("request_id")

        if not request_id:
            await message.reply(
              "Failed to create the task. Please try again."
            )
            return

        status_message = await message.reply(f"Task created. ID: {request_id}")

        while True:
            status_response = await session.get(
              f"{STATUS_URL}{request_id}", headers=HEADERS
            )
            status_response.raise_for_status()
            status_data = await status_response.json()
            status = status_data.get("status")

            if status == "complete":
                for idx, item in enumerate(status_data.get('result', [])[:2]):
                    audio_url = item.get('audio_url')
                    if audio_url:
                        audio_response = await session.get(audio_url)
                        audio_response.raise_for_status()

                        audio_file_path = f"v{idx + 1}.mp3"
                        audio_data = await audio_response.read()

                        async with aiofiles.open(audio_file_path, "wb") as audio_file:
                            await audio_file.write(audio_data)

                        await bot.send_audio(
                          chat_id=message.chat.id, audio=audio_file_path
                        )

                await status_message.edit(
                  f"[Lyrics and details]({STATUS_URL}{request_id})"
                )
                break

            await status_message.edit(f"Status: {status}")
            await asyncio.sleep(15)

    except Exception as e:
        await message.reply(f"An error occurred: {e}")
