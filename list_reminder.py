import time
from pyrogram.enums import ParseMode
from app import BOT, Message, CustomDB

# Database Collection
DB = CustomDB["REMINDER_LIST"]


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
    user_id = message.from_user.id

    # Fetch from DB
    user_data = await DB.find_one({"_id": user_id})
    user_list = user_data.get("list", []) if user_data else []

    inp = getattr(message, "input", None)
    if not inp and message.reply_to_message:
        inp = message.reply_to_message.text

    # 1. Remove Item Logic
    if inp and inp.strip().isdigit():
        idx = int(inp.strip()) - 1
        if 0 <= idx < len(user_list):
            removed = user_list.pop(idx)
            # Save to DB
            await DB.add_data({"_id": user_id, "list": user_list})

            await message.reply(
                text=f"✅ Removed item #{idx+1}: <b>{removed['text']}</b>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply("Invalid item number.", del_in=5)
        return

    # 2. Add Item Logic
    if inp:
        item = {
            "text": inp,
            "time": time.time(),
        }
        if message.reply_to_message:
            item["link"] = message.reply_to_message.link

        user_list.append(item)

        # Save to DB
        await DB.add_data({"_id": user_id, "list": user_list})

        await message.reply(
            text=f"➕ Added: <b>{inp}</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    # 3. View List Logic
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
    await message.reply(text=resp, parse_mode=ParseMode.HTML, disable_preview=True)
