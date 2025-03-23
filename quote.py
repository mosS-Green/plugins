import os
import base64
import requests

from app import BOT, Message, bot


def upload_to_tph(file_path):
    url = "https://telegra.ph/upload"
    with open(file_path, "rb") as f:
        response = requests.post(url, files={"file0": f}).json()
    if isinstance(response, list) and len(response) > 0 and "src" in response[0]:
        return "https://telegra.ph" + response[0]["src"]
    return None


@bot.add_cmd(cmd=["q"])
async def quote_message(bot: BOT, message: Message):
    reply = message.replied
    if not reply or not reply.text:
        return await message.reply("quote joe mama?")

    loading_msg = await message.reply("<code>...</code>")

    if message.input == "r":
        og_reply = reply.reply_to_message
        reply_user = og_reply.from_user
        og_reply_quote = {
            "from": {
                "id": reply_user.id,
                "name": reply_user.first_name,
                "photo": {},
            },
            "text": og_reply.text if og_reply and og_reply.text else "",
        }

    user = reply.from_user
    avatar = None
    if user.photo:
        avatar_file_path = await bot.download_media(user.photo.small_file_id)
        avatar = upload_to_tph(avatar_file_path)
        if os.path.exists(avatar_file_path):
            os.remove(avatar_file_path)

    json_payload = {
        "type": "quote",
        "format": "webp",
        "backgroundColor": "#163930",
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
                "replyMessage": og_reply_quote if message.input == "r" else {},
            }
        ],
    }

    try:
        response = requests.post(
            "https://bot.lyo.su/quote/generate", json=json_payload
        ).json()
        image_data = base64.b64decode(response["result"]["image"].encode("utf-8"))
        file_path = "Quotly.webp"
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
