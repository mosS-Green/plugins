import os
import base64
import requests

from app import BOT, Message, bot


@bot.add_cmd(cmd=["q"])
async def quote_message(bot: BOT, message: Message):
    reply = message.replied
    if not reply or not reply.text:
        return await message.reply("quote joe mama?")

    user = reply.from_user
    avatar = user.photo.url if user.photo else None

    json_payload = {
        "type": "quote",
        "format": "webp",
        "backgroundColor": "#2D5243",
        "width": 512,
        "height": 768,
        "scale": 2,
        "messages": [
            {
                "entities": [],
                "avatar": True,
                "from": {
                    "id": user.id,
                    "name": user.first_name,
                    "photo": {"url": avatar} if avatar else {},
                },
                "text": reply.text,
            }
        ],
    }

    if message.input == "r":
        original_reply = reply.reply_to
        if original_reply and original_reply.text:
            json_payload["messages"][0]["replyMessage"] = {"text": original_reply.text}

    loading_msg = await message.reply("<code>...</code>")

    try:
        response = requests.post(
            "https://bot.lyo.su/quote/generate", json=json_payload
        ).json()
        image_data = base64.b64decode(response["result"]["image"].encode("utf-8"))
        file_path = "Quotly.png"
        with open(file_path, "wb") as file:
            file.write(image_data)

        await bot.send_sticker(
            chat_id=message.chat.id, sticker=file_path, reply_to_message_id=message.id
        )
        await loading_msg.delete()

    except Exception as e:
        await loading_msg.edit(f"Error: {str(e)}")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
