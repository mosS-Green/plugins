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
    SYSTEM_PROMPT,
    PROACTIVE_CHANCE,
    ACTIVE_DURATION,
    ACTIVE_MSG_INTERVAL,
    CONTEXTUAL_INTERVAL,
    SPLIT_DELIMITER,
    THINK_DELIMITER,
    NULL_DELIMITER,
)
from .eh_history import (
    append_user_message,
    append_model_message,
)

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

_REPLY_PATTERN = re.compile(r"^<REPLY:(\d+)>\s*")


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


def _format_for_openai(history: list[dict], contextual: bool = False) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        role = "assistant" if msg["role"] == "model" else "user"
        messages.append({"role": role, "content": msg["text"]})

    if contextual:
        messages.append(
            {
                "role": "user",
                "content": (
                    "[SYSTEM] evaluate the recent conversation. "
                    "if anything is worth replying to or you have something to say, "
                    "if in the existing chat, there is a good joke to make."
                    "like that's what she said etc., then "
                    "reply naturally. if not, respond with only <NULL> followed by a brief thought."
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
    from pyrogram.types import ReplyParameters

    full_response = response_text.strip()

    reply_match = _REPLY_PATTERN.match(full_response)
    if reply_match:
        reply_to = int(reply_match.group(1))
        full_response = full_response[reply_match.end() :].strip()

    is_null = False
    if full_response.startswith(NULL_DELIMITER):
        full_response = full_response[len(NULL_DELIMITER) :].strip()
        is_null = True

    thoughts = []
    if THINK_DELIMITER in full_response:
        segments = full_response.split(THINK_DELIMITER)
        sendable_parts = []
        for idx, seg in enumerate(segments):
            if idx % 2 == 0:
                sendable_parts.append(seg)
            else:
                if SPLIT_DELIMITER in seg:
                    think_text, after_split = seg.split(SPLIT_DELIMITER, 1)
                    thoughts.append(think_text.strip())
                    sendable_parts.append(after_split)
                else:
                    thoughts.append(seg.strip())

        sendable = SPLIT_DELIMITER.join(sendable_parts).strip()
        thought = " | ".join(t for t in thoughts if t)
    else:
        sendable = full_response
        thought = ""

    if is_null:
        sendable = ""

    if thought:
        LOGGER.info(f"EH Autobot thought: {thought}")

    if not sendable:
        await append_model_message(chat_id, response_text.strip())
        return

    messages = [m.strip() for m in sendable.split(SPLIT_DELIMITER) if m.strip()]

    for i, msg_text in enumerate(messages):
        try:
            if i == 0 and reply_to:
                await _bot.send_message(
                    chat_id=chat_id,
                    text=msg_text,
                    reply_parameters=ReplyParameters(message_id=reply_to),
                )
            else:
                await _bot.send_message(
                    chat_id=chat_id,
                    text=msg_text,
                )

            if i < len(messages) - 1:
                await asyncio.sleep(random.uniform(0.5, 2.0))

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
