import json
import os
import time
from datetime import datetime
from pyrogram.enums import ParseMode
from app import BOT, Message, Config


DATA_FILE = "list_reminder_data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


def human_time_ago(timestamp):
    diff = int(time.time() - timestamp)
    if diff < 60:
        return f"{diff}s ago"
    elif diff < 3600:
        return f"{diff // 60}m ago"
    elif diff < 86400:
        return f"{diff // 3600}h ago"
    else:
        return f"{diff // 86400}d ago"


@BOT.add_cmd("lr")
async def list_reminder(bot: BOT, message: Message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_list = data.get(user_id, [])

    inp = getattr(message, "input", None)
    if not inp and message.reply_to_message:
        inp = message.reply_to_message.text

    # Mark item as done if numeric input
    if inp and inp.strip().isdigit():
        idx = int(inp.strip()) - 1
        if 0 <= idx < len(user_list):
            removed = user_list.pop(idx)
            data[user_id] = user_list
            save_data(data)
            await message.reply(
                text=f"✅ Removed item #{idx+1}: <b>{removed['text']}</b>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply("Invalid item number.", del_in=5)
        return

    # Add new item
    if inp:
        item = {
            "text": inp,
            "time": time.time(),
        }
        if message.reply_to_message:
            item["link"] = message.reply_to_message.link

        user_list.append(item)
        data[user_id] = user_list
        save_data(data)
        await message.reply(
            text=f"➕ Added: <b>{inp}</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Show list
    if not user_list:
        await message.reply("📝 Your list is empty.", del_in=6)
        return

    lines = []
    for i, item in enumerate(user_list, 1):
        text = item["text"]
        ago = human_time_ago(item["time"])
        if "link" in item:
            line = f"{i}. <a href='{item['link']}'>{text}</a> <i>({ago})</i>"
        else:
            line = f"{i}. {text} <i>({ago})</i>"
        lines.append(line)

    resp = "<b>Your list:</b>\n" + "\n".join(lines)
    await message.reply(
        text=resp,
        parse_mode=ParseMode.HTML,
    )
