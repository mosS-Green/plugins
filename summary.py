from app import BOT, Message, bot
from pyrogram.enums import ParseMode

from .ai_sandbox.core import ask_ai, MODEL
from app.plugins.ai.gemini.utils import run_basic_check


@bot.add_cmd(cmd="sm")
@run_basic_check
async def summ(bot: BOT, message: Message):
    """Summarizes chat messages using AI."""
    limit = 200  # Default sanity limit
    count = 0
    start_msg_id = None

    # 1. Determine Fetch Strategy
    if message.input and message.input.isdigit():
        # Case: Count argument provided (.sm 50)
        count = int(message.input)
        if count > 500:
            count = 500  # Hard cap
    elif message.replied:
        # Case: Reply range
        start_msg_id = message.replied.id
    else:
        # Case: Invalid usage
        await message.reply(
            "Reply to the start message or provide a number (e.g., .sm 50)."
        )
        return

    wait_msg = await message.reply("<code>Reading history...</code>")

    chat_lines = []

    # 2. Fetch Messages Iterator
    # If count is specified, we fetch the last N messages
    if count:
        async for msg in bot.get_chat_history(chat_id=message.chat.id, limit=count):
            if not msg.text and not msg.caption:
                continue

            sender_name = "Unknown"
            if msg.from_user:
                sender_name = msg.from_user.first_name
            elif msg.sender_chat:
                sender_name = msg.sender_chat.title

            content = (msg.text or msg.caption).replace("\n", " ")
            chat_lines.append(f"[{sender_name}]: {content}")

        # Reverse to chronological order as history returns newest first
        chat_lines.reverse()

    # If using reply range
    elif start_msg_id:
        # We iterate history from current message backwards until we hit start_msg_id
        # or hit the sanity limit.
        temp_lines = []
        found_start = False

        async for msg in bot.get_chat_history(chat_id=message.chat.id, limit=limit):
            # Stop if we went past the start message (in case ID check fails, which is rare)
            if msg.id < start_msg_id:
                break

            if not msg.text and not msg.caption:
                # Still check for break condition even if no text
                if msg.id == start_msg_id:
                    found_start = True
                    break
                continue

            sender_name = "Unknown"
            if msg.from_user:
                sender_name = msg.from_user.first_name
            elif msg.sender_chat:
                sender_name = msg.sender_chat.title

            content = (msg.text or msg.caption).replace("\n", " ")
            line = f"[{sender_name}]: {content}"
            temp_lines.append(line)

            if msg.id == start_msg_id:
                found_start = True
                break

        if not found_start:
            # If we didn't find the start message within limit, let user know
            # But still summarize what we got
            await wait_msg.edit(f"Range too large, summarized last {limit} messages.")

        # Reverse to get chronological order
        chat_lines = temp_lines[::-1]

    if not chat_lines:
        await wait_msg.edit("No text content found to summarize.")
        return

    chat_history = "\n".join(chat_lines)
    await wait_msg.edit("<code>Thinking...</code>")

    # 3. Prompt Construction & Flags
    base_instruction = "Summarize the following group chat conversation [use markdown]:"

    model_config = MODEL["DEFAULT"]

    if "-x" in message.flags:
        model_config = MODEL["LEAF"]  # Leaflet persona
    elif "-t" in message.flags:
        base_instruction = (
            "Provide a TL;DR (Too Long, Didn't Read) summary. Be extremely concise."
        )

    full_prompt = (
        f"{base_instruction}\n\n[Start of Chat]\n{chat_history}\n[End of Chat]"
    )

    if message.input and not message.input.isdigit():
        if not count:
            full_prompt = f"{message.input}\n\nContext:\n{chat_history}"

    content = await ask_ai(prompt=full_prompt, quote=True, **model_config)

    await wait_msg.edit(
        text=content, parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )
