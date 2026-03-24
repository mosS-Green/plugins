import asyncio
import random
import time
from collections import defaultdict
from datetime import datetime

from google.genai.client import Client
from google.genai.types import GenerateContentConfig, SafetySetting, ThinkingConfig
from pyrogram import filters
from pyrogram.filters import Filter
from pyrogram.errors import FloodWait
from ub_core.utils.helpers import get_name

from app import BOT, LOGGER, Message, bot, extra_config

from .config import (
    ACTIVE_DURATION,
    ACTIVE_MSG_INTERVAL,
    AUTOBOT_GEMINI_API_KEY,
    CONTEXTUAL_INTERVAL,
    HISTORY_DIR,
    MODEL_LIST,
    PROACTIVE_CHANCE,
    SYSTEM_PROMPT,
    AutobotMessage,
)
from .history import append_model_message, append_user_message

_bot = bot.bot

# ---------------------------------------------------------------------------
# Mutable runtime state
# ---------------------------------------------------------------------------

_enabled_chats: set[int] = set()  # chats where autobot is active (disabled by default)
_passive_chats: set[int] = set()  # chats where autobot only logs passively

# Per-chat counters: {chat_id: {"msg_counter": int, "active_until": float, "active_msg_count": int}}
_chat_state: dict[int, dict] = defaultdict(
    lambda: {"msg_counter": 0, "active_until": 0.0, "active_msg_count": 0, "last_spoke_at": time.time()}
)

_current_model_idx = 0  # index into MODEL_LIST
_requests_since_cycle = 0  # generation requests since the last model cycle
_last_logged_model = None  # last model name written to the log (dedup guard)

_passive_task = None

async def _passive_trigger_loop():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for chat_id in list(_enabled_chats):
            state = _chat_state[chat_id]
            last_spoke = state.get("last_spoke_at", now)
            if now - last_spoke >= 7200:
                state["last_spoke_at"] = time.time()
                try:
                    from .history import load_history
                    history = await load_history(chat_id)
                    if not history:
                        continue
                    
                    response_text = await _generate_response(history, contextual=True)
                    if response_text:
                        await _send_response(
                            chat_id=chat_id,
                            response_text=response_text,
                            reply_to=None,
                        )
                except Exception as e:
                    LOGGER.error(f"Autobot passive trigger error: {e}")

def _ensure_passive_task():
    global _passive_task
    try:
        loop = asyncio.get_running_loop()
        if _passive_task is None or _passive_task.done():
            _passive_task = loop.create_task(_passive_trigger_loop())
    except RuntimeError:
        pass

# ---------------------------------------------------------------------------
# Gemini client & generation config
# ---------------------------------------------------------------------------

_autobot_client = Client(
    api_key=AUTOBOT_GEMINI_API_KEY or extra_config.GEMINI_API_KEY
).aio

SAFETY_OFF = [
    SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="OFF"),
]

AUTOBOT_CONFIG = GenerateContentConfig(
    candidate_count=1,
    system_instruction=SYSTEM_PROMPT,
    temperature=0.8,
    max_output_tokens=1024,
    safety_settings=SAFETY_OFF,
    thinking_config=ThinkingConfig(thinking_budget=0),
    response_mime_type="application/json",
    response_schema=list[AutobotMessage],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_current_model() -> str:
    return MODEL_LIST[_current_model_idx]


def _cycle_model():
    global _current_model_idx, _requests_since_cycle
    _current_model_idx = (_current_model_idx + 1) % len(MODEL_LIST)
    _requests_since_cycle = 0
    LOGGER.info(f"Autobot: cycled model to {_get_current_model()}")


def _sender_name(message) -> str:
    """Extract sender display name using core's get_name helper."""
    if message.from_user:
        return get_name(message.from_user)
    if message.sender_chat:
        return get_name(message.sender_chat)
    return "Unknown"


def _is_reactive(message) -> bool:
    """Check if the message should trigger a direct reply.

    Uses pyrogram's ``message.mentioned`` for @-mentions and replies to the
    bot, plus a keyword check for "reya" (ignoring command prefixes).
    """
    if message.mentioned:
        return True

    text = message.text or message.caption
    if text:
        text_lower = text.lower().strip()
        if "reya" in text_lower:
            return True

    return False


# Pyrogram filter: reactive messages (mentions or "reya" keyword)
_reactive_filter: Filter = filters.create(
    lambda _, __, msg: _is_reactive(msg),
    name="ReactiveFilter",
)


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


async def _generate_response(history: list, contextual: bool = False) -> str | None:
    global _requests_since_cycle, _last_logged_model
    try:
        contents = list(history)

        if contextual:
            from google.genai import types

            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=(
                                "[SYSTEM] evaluate the recent conversation. "
                                "if anything is worth replying to or you have something to say, "
                                "if in the existing chat, there is a good joke to make."
                                "like that's what she said etc., then "
                                "reply naturally. if not, respond with only an empty list: [] to indicate silence."
                            )
                        )
                    ],
                )
            )

        _requests_since_cycle += 1
        if _requests_since_cycle >= 19:
            _cycle_model()

        model_name = _get_current_model()
        if model_name != _last_logged_model:
            _last_logged_model = model_name
            LOGGER.info(f"Autobot using model: {model_name}")

        response = await _autobot_client.models.generate_content(
            contents=contents,
            model=model_name,
            config=AUTOBOT_CONFIG,
        )

        if (
            response.candidates
            and response.candidates[0].content
            and response.candidates[0].content.parts
        ):
            return response.candidates[0].content.parts[0].text

        return None

    except Exception as e:
        LOGGER.error(f"Autobot: generation error: {e}")
        return None


# ---------------------------------------------------------------------------
# Response dispatch
# ---------------------------------------------------------------------------


async def _send_response(chat_id: int, response_text: str, reply_to: int | None = None):
    from pydantic import TypeAdapter, ValidationError
    from pyrogram.types import ReplyParameters

    try:
        adapter = TypeAdapter(list[AutobotMessage])
        response_data = adapter.validate_json(response_text)
    except ValidationError as e:
        LOGGER.error(
            f"Autobot: JSON validation error: {e}\nRaw output: {response_text}"
        )
        await append_model_message(chat_id, response_text.strip())
        return

    if not response_data:
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
                kwargs["reply_parameters"] = ReplyParameters(
                    message_id=int(reply_to_id)
                )

            await _bot.send_message(**kwargs)

            if i < len(response_data) - 1:
                await asyncio.sleep(random.uniform(0.5, 2.0))

        except FloodWait as e:
            await asyncio.sleep(e.value)
            await _bot.send_message(**kwargs)

        except Exception as e:
            LOGGER.error(f"Autobot: send error: {e}")

    # Cache the full model response after sending
    await append_model_message(chat_id, response_text.strip())


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Common: build user_text and append to history
# ---------------------------------------------------------------------------


async def _ingest_message(message) -> tuple[list, dict]:
    """Append the incoming message to history and return (history, state)."""
    chat_id = message.chat.id
    now = datetime.now()
    state = _chat_state[chat_id]
    text = message.text or message.caption or ""
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
    return history, state


# ---------------------------------------------------------------------------
# Handler 1: Reactive (mentions / "reya" keyword) — always replies
# ---------------------------------------------------------------------------


@_bot.on_message(
    filters=~filters.service
    & (filters.text | filters.caption)
    & _reactive_filter,
    group=0,
)
async def autobot_reactive_handler(_bot_client, message):
    chat_id = message.chat.id

    is_enabled = chat_id in _enabled_chats
    is_passive = chat_id in _passive_chats

    _ensure_passive_task()

    if not is_enabled and not is_passive:
        return

    if message.from_user and message.from_user.is_self:
        return

    history, state = await _ingest_message(message)
    state["msg_counter"] = 0

    if not is_enabled:
        return

    response_text = await _generate_response(history)
    if not response_text:
        return

    state["last_spoke_at"] = time.time()

    await _send_response(
        chat_id=chat_id,
        response_text=response_text,
        reply_to=message.id,
    )


# ---------------------------------------------------------------------------
# Handler 2: Proactive / Active / Contextual — fires on all other messages
# ---------------------------------------------------------------------------


@_bot.on_message(
    filters=~filters.service
    & (filters.text | filters.caption)
    & ~_reactive_filter,
    group=1,
)
async def autobot_handler(_bot_client, message):
    chat_id = message.chat.id

    is_enabled = chat_id in _enabled_chats
    is_passive = chat_id in _passive_chats

    _ensure_passive_task()

    if not is_enabled and not is_passive:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    if message.from_user and message.from_user.is_self:
        return

    history, state = await _ingest_message(message)

    if not is_enabled:
        return

    state["msg_counter"] += 1
    should_reply = False
    is_contextual = False
    reply_to_id = None

    # --- Trigger evaluation ---

    if random.randint(1, 100) <= PROACTIVE_CHANCE:
        should_reply = True
        state["active_until"] = time.time() + ACTIVE_DURATION
        state["active_msg_count"] = 0
        state["msg_counter"] = 0

    elif time.time() < state["active_until"]:
        state["active_msg_count"] += 1
        if state["active_msg_count"] >= ACTIVE_MSG_INTERVAL:
            should_reply = True
            state["active_msg_count"] = 0

    if not should_reply and state["msg_counter"] >= CONTEXTUAL_INTERVAL:
        state["msg_counter"] = 0
        should_reply = True
        is_contextual = True

    if not should_reply:
        return

    response_text = await _generate_response(history, contextual=is_contextual)

    if not response_text:
        return

    state["last_spoke_at"] = time.time()

    await _send_response(
        chat_id=chat_id,
        response_text=response_text,
        reply_to=reply_to_id,
    )


# ---------------------------------------------------------------------------
# Control command
# ---------------------------------------------------------------------------


@bot.add_cmd(cmd="ry")
async def reya_cmd(bot: BOT, message: Message):
    """
    CMD: RY
    INFO: Runtime control panel for the Autobot plugin.
    FLAGS: -r to cycle model, -c to clear history, -p to toggle passive logging
    USAGE: ,ry | ,ry -r | ,ry -c | ,ry -p
    """

    if "-r" in message.flags:
        _cycle_model()
        await message.reply(f"cycled to: {_get_current_model()}")
        return

    if "-c" in message.flags:
        import os

        chat_id = message.chat.id
        history_path = os.path.join(HISTORY_DIR, f"{chat_id}.pkl")
        if os.path.exists(history_path):
            os.remove(history_path)
        await message.reply("history cleared.")
        return

    chat_id = message.chat.id

    _ensure_passive_task()

    if "-p" in message.flags:
        if chat_id in _passive_chats:
            _passive_chats.discard(chat_id)
            await message.reply("passive logging off.")
        else:
            _passive_chats.add(chat_id)
            await message.reply("passive logging on.")
        return

    if chat_id in _enabled_chats:
        _enabled_chats.discard(chat_id)
        msg_text = "autobot is now off"
        if chat_id in _passive_chats:
            msg_text += " (passive logging continues)"
        await message.reply(msg_text)
    else:
        _enabled_chats.add(chat_id)
        msg_text = "autobot is now on"
        if chat_id in _passive_chats:
            msg_text += " (passive logging active)"
        await message.reply(msg_text)
