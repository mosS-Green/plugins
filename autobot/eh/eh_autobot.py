import asyncio
import os
import random
import re
import time
from collections import defaultdict
from datetime import datetime

from openai import AsyncOpenAI
from pyrogram import filters
from ub_core.utils.helpers import get_name

from app import LOGGER, bot

from app.modules.autobot.config import (
    ACTIVE_DURATION,
    ACTIVE_MSG_INTERVAL,
    AUTOBOT_GEMINI_API_KEY,
    BOT_USERNAME,
    CONTEXTUAL_INTERVAL,
    HISTORY_DIR,
    MODEL_LIST,
    PROACTIVE_CHANCE,
    SYSTEM_PROMPT,
    AutobotMessage,
)
from app.modules.autobot.history import append_model_message, append_user_message

_bot = bot.bot

# ---------------------------------------------------------------------------
# Mutable runtime state
# ---------------------------------------------------------------------------

_eh_enabled_chats: set[int] = set()

_chat_state: dict[int, dict] = defaultdict(
    lambda: {"msg_counter": 0, "active_until": 0.0, "active_msg_count": 0}
)

# ---------------------------------------------------------------------------
# OpenAI (Electron Hub) client & config
# ---------------------------------------------------------------------------

ELECTRON_API_KEY = os.getenv("ELECTRON_API_KEY")
ELECTRON_BASE_URL = "https://api.electronhub.ai/v1/"
MODEL_TEXT = "gemini-2.5-flash-lite"

_eh_client = AsyncOpenAI(
    api_key=ELECTRON_API_KEY, base_url=ELECTRON_BASE_URL, timeout=60.0
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sender_name(message) -> str:
    """Extract sender display name using core's get_name helper."""
    if message.from_user:
        return get_name(message.from_user)
    if message.sender_chat:
        return get_name(message.sender_chat)
    return "Unknown"


def _is_reactive(message) -> bool:
    if message.mentioned:
        return True

    text = message.text or message.caption
    if text:
        text_lower = text.lower().strip()
        if "reya" in text_lower:
            return True

    return False


def _format_for_openai(history: list, contextual: bool = False) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        role = "assistant" if msg.role == "model" else "user"
        text = msg.parts[0].text if msg.parts else ""
        messages.append({"role": role, "content": text})

    if contextual:
        messages.append(
            {
                "role": "user",
                "content": (
                    "[SYSTEM] evaluate the recent conversation. "
                    "if anything is worth replying to or you have something to say, "
                    "if in the existing chat, there is a good joke to make."
                    "like that's what she said etc., then "
                    "reply naturally. if not, respond with only an empty list: [] to indicate silence."
                ),
            }
        )

    return messages


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


async def _generate_response(history: list, contextual: bool = False) -> str | None:
    try:
        messages = _format_for_openai(history, contextual=contextual)

        LOGGER.info(f"EH Autobot using model: {MODEL_TEXT}")

        response = await _eh_client.chat.completions.create(
            model=MODEL_TEXT,
            messages=messages,
            temperature=0.9,
            max_tokens=1024,
        )

        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content

        return None

    except Exception as e:
        LOGGER.error(f"EH Autobot: generation error: {e}")
        return None


# ---------------------------------------------------------------------------
# Response dispatch
# ---------------------------------------------------------------------------


async def _send_response(chat_id: int, response_text: str, reply_to: int | None = None):
    import re
    from pydantic import TypeAdapter, ValidationError
    from pyrogram.types import ReplyParameters
    from pyrogram.errors import FloodWait

    response_text = response_text.strip()
    if response_text.startswith("```"):
        response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
        response_text = re.sub(r"\n?```$", "", response_text)
        response_text = response_text.strip()

    try:
        adapter = TypeAdapter(list[AutobotMessage])
        response_data = adapter.validate_json(response_text)
    except ValidationError as e:
        LOGGER.error(f"EH Autobot: JSON validation error: {e}\nRaw output: {response_text}")
        await append_model_message(chat_id, response_text.strip())
        return

    if not response_data:
        # Empty list, nothing to send
        await append_model_message(chat_id, response_text.strip())
        return

    for i, msg_data in enumerate(response_data):
        is_thought = msg_data.is_thought
        text = msg_data.text
        reply_to_id = msg_data.reply_to_id or reply_to

        if not text:
            continue

        if is_thought:
            await bot.log_text(f"reya thought: {text}", type="autobot")
            continue

        try:
            kwargs = {
                "chat_id": chat_id,
                "text": text,
            }
            if reply_to_id:
                kwargs["reply_parameters"] = ReplyParameters(message_id=int(reply_to_id))

            await _bot.send_message(**kwargs)

            if i < len(response_data) - 1:
                await asyncio.sleep(random.uniform(0.5, 2.0))

        except FloodWait as e:
            await asyncio.sleep(e.value)
            await _bot.send_message(**kwargs)

        except Exception as e:
            LOGGER.error(f"EH Autobot: send error: {e}")

    await append_model_message(chat_id, response_text.strip())


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------


@_bot.on_message(filters=~filters.service & (filters.text | filters.caption))
async def eh_autobot_handler(_bot_client, message):
    chat_id = message.chat.id

    if chat_id not in _eh_enabled_chats:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    if message.from_user and message.from_user.is_self:
        return

    now = datetime.now()
    state = _chat_state[chat_id]

    sender_name = _sender_name(message)

    user_text = text
    if message.reply_to_message:
        quoted = message.reply_to_message.text or message.reply_to_message.caption or ""
        if quoted:
            quote_sender = _sender_name(message.reply_to_message)
            user_text = f'[quoting {quote_sender}: "{quoted}"] {text}'

    history = await append_user_message(
        chat_id=chat_id,
        msg_id=message.id,
        dt=now,
        sender_name=sender_name,
        text=user_text,
    )

    state["msg_counter"] += 1
    should_reply = False
    is_contextual = False
    reply_to_id = None

    if _is_reactive(message):
        should_reply = True
        reply_to_id = message.id
        state["msg_counter"] = 0

    elif random.randint(1, 100) <= PROACTIVE_CHANCE:
        should_reply = True
        state["active_until"] = time.time() + ACTIVE_DURATION
        state["active_msg_count"] = 0
        state["msg_counter"] = 0
        reply_to_id = None

    elif time.time() < state["active_until"]:
        state["active_msg_count"] += 1
        if state["active_msg_count"] >= ACTIVE_MSG_INTERVAL:
            should_reply = True
            state["active_msg_count"] = 0
            reply_to_id = None

    if not should_reply and state["msg_counter"] >= CONTEXTUAL_INTERVAL:
        state["msg_counter"] = 0
        should_reply = True
        is_contextual = True
        reply_to_id = None

    if not should_reply:
        return

    response_text = await _generate_response(history, contextual=is_contextual)

    if not response_text:
        return

    await _send_response(
        chat_id=chat_id,
        response_text=response_text,
        reply_to=reply_to_id,
    )
