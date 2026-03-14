import asyncio
import random
import re
import time
from datetime import datetime

from pyrogram import filters
from google.genai.client import Client
from google.genai.types import GenerateContentConfig, SafetySetting, ThinkingConfig

from app import BOT, Config, LOGGER, Message, bot, extra_config

from .config import (
    TARGET_CHAT_ID as _DEFAULT_TARGET_CHAT_ID,
    BOT_USERNAME,
    SYSTEM_PROMPT,
    PROACTIVE_CHANCE,
    ACTIVE_DURATION,
    ACTIVE_MSG_INTERVAL,
    CONTEXTUAL_INTERVAL,
    SPLIT_DELIMITER,
    THINK_DELIMITER,
    REPLY_DELIMITER,
    NULL_DELIMITER,
    MODEL_LIST,
    AUTOBOT_GEMINI_API_KEY,
    HISTORY_FILE,
)
from .history import (
    append_user_message,
    append_model_message,
)

_bot = bot.bot

# ---------------------------------------------------------------------------
# Mutable runtime state
# ---------------------------------------------------------------------------

_msg_counter = 0  # messages received since the last contextual check
_active_until = 0.0  # epoch timestamp when active mode expires
_active_msg_count = 0  # messages received since the last active-mode reply
_autobot_enabled = True  # global on/off toggle
_current_model_idx = 0  # index into MODEL_LIST
_requests_since_cycle = 0  # generation requests since the last model cycle
_target_chat_id = _DEFAULT_TARGET_CHAT_ID  # runtime-overridable target chat
_last_logged_model = None  # last model name written to the log (dedup guard)

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
    temperature=0.9,
    max_output_tokens=1024,
    safety_settings=SAFETY_OFF,
    thinking_config=ThinkingConfig(thinking_budget=0),
)

# Compiled regex for the <REPLY:MSG_ID> prefix at the start of a response.
_REPLY_PATTERN = re.compile(r"^<REPLY:(\d+)>\s*")

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


def _get_sender_name(message) -> str:
    if message.from_user:
        return message.from_user.first_name or "Unknown"
    if message.sender_chat:
        return message.sender_chat.title or "Unknown"
    return "Unknown"


def _is_reactive(message) -> bool:
    text_to_check = message.text or message.caption
    if text_to_check:
        text_lower = text_to_check.lower().strip()
        if f"@{BOT_USERNAME}" in text_lower or "reya" in text_lower:
            return True

    if message.reply_to_message:
        reply_from = message.reply_to_message.from_user
        if (
            reply_from
            and reply_from.username
            and reply_from.username.lower() == BOT_USERNAME.lower()
        ):
            return True

    return False


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
                                "reply naturally. if not, respond with only <NULL> followed by a brief thought."
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
                # A <SPLIT> inside a <THINK> block promotes text after it to sendable.
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

    await append_model_message(response_text.strip())

    if thought:
        LOGGER.info(f"Autobot thought: {thought}")

    if not sendable:
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
            LOGGER.error(f"Autobot: send error: {e}")


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------


@_bot.on_message(filters=~filters.service & (filters.text | filters.caption))
async def autobot_handler(_bot_client, message):
    global _msg_counter, _active_until, _active_msg_count

    if message.chat.id != _target_chat_id:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    if not _autobot_enabled:
        return

    now = datetime.now()

    # The bot's own outgoing messages are recorded as model role; no reply needed.
    if message.from_user and message.from_user.is_self:
        await append_model_message(text)
        return

    sender_name = _get_sender_name(message)

    # When the sender is replying to another message, prepend a quote so the
    # model has the full conversational context without needing to scroll back.
    user_text = text
    if message.reply_to_message:
        quoted = message.reply_to_message.text or message.reply_to_message.caption or ""
        if quoted:
            quote_sender = _get_sender_name(message.reply_to_message)
            user_text = f'[quoting {quote_sender}: "{quoted}"] {text}'

    history = await append_user_message(
        msg_id=message.id,
        dt=now,
        sender_name=sender_name,
        text=user_text,
    )

    _msg_counter += 1
    should_reply = False
    is_contextual = False
    reply_to_id = None

    # --- Trigger evaluation (highest to lowest priority) ---

    if _is_reactive(message):
        should_reply = True
        reply_to_id = message.id
        _msg_counter = 0

    elif random.randint(1, 100) <= PROACTIVE_CHANCE:
        should_reply = True
        _active_until = time.time() + ACTIVE_DURATION
        _active_msg_count = 0
        _msg_counter = 0
        reply_to_id = None

    elif time.time() < _active_until:
        _active_msg_count += 1
        if _active_msg_count >= ACTIVE_MSG_INTERVAL:
            should_reply = True
            _active_msg_count = 0
            reply_to_id = None

    if not should_reply and _msg_counter >= CONTEXTUAL_INTERVAL:
        _msg_counter = 0
        should_reply = True
        is_contextual = True
        reply_to_id = None

    if not should_reply:
        return

    response_text = await _generate_response(history, contextual=is_contextual)

    if not response_text:
        return

    await _send_response(
        chat_id=_target_chat_id,
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
    FLAGS: -r to cycle model, -c to clear history, -id to set target chat
    USAGE: ,ry | ,ry -r | ,ry -c | ,ry -id
    """
    global _autobot_enabled, _target_chat_id

    if "-r" in message.flags:
        _cycle_model()
        await message.reply(f"cycled to: {_get_current_model()}")
        return

    if "-c" in message.flags:
        import aiofiles

        async with aiofiles.open(HISTORY_FILE, "w", encoding="utf-8") as f:
            await f.write("[]")
        await message.reply("history cleared.")
        return

    if "-id" in message.flags:
        _target_chat_id = message.chat.id
        await message.reply(f"target chat set to: {_target_chat_id}")
        return

    _autobot_enabled = not _autobot_enabled
    state_str = "on" if _autobot_enabled else "off"
    await message.reply(f"autobot is now {state_str}")
