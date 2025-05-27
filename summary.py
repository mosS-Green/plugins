from app import BOT, Message, bot
from pyrogram.enums import ParseMode

from .aicore import MODEL, ask_ai, run_basic_check


@bot.add_cmd(cmd="sm")
@run_basic_check
async def summ(bot: BOT, message: Message):
    reply = message.replied

    reply_id = reply.id
    latest_id = message.id

    messages = await bot.get_messages(
        chat_id=message.chat.id, message_ids=range(reply_id, latest_id + 1)
    )

    chat_lines = []
    for msg in messages:
        if msg.text and (msg.from_user or msg.sender_chat):
            sender_name = (
                msg.from_user.first_name
                if msg.from_user
                else (msg.sender_chat.title if msg.sender_chat else "Unknown")
            )
            chat_lines.append(f"[{sender_name}]: {msg.text}")

    if not chat_lines:
        await message.reply("No text messages found in the replied range to summarize.")
        return

    chat_history = "\n\n".join(chat_lines)

    user_instruction = (
        message.input
        if message.input
        else "[use markdown] Summarize the following group chat, ensure to detail each thread of conversation:"
    )
    full_prompt = f"{user_instruction}\n\n[Conversation Start]\n{chat_history}\n[Conversation End]"

    load_msg = await message.reply("<code>...</code>")

    content = await ask_ai(prompt=full_prompt, quote=True, **MODEL["DEFAULT"])

    await load_msg.edit(
        text=content, parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )
