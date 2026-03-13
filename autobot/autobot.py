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
    MODEL_LIST,
    AUTOBOT_GEMINI_API_KEY,
    HISTORY_FILE,
)
from .history import (
    append_user_message,
    append_model_message,
)

# Bot agent reference
_bot = bot.bot

# --- State ---
_msg_counter = 0  # messages since last contextual check
_active_until = 0.0  # timestamp when active mode expires
_active_msg_count = 0  # messages since last active-mode reply
_autobot_enabled = True  # whether the bot is globally enabled
_current_model_idx = 0  # index in MODEL_LIST
_requests_since_cycle = 0  # count requests to auto-cycle
_target_chat_id = _DEFAULT_TARGET_CHAT_ID  # mutable target chat
_last_logged_model = None  # track last logged model to avoid spam

# Autobot specific client — use dedicated key or fall back to default
_autobot_client = Client(
    api_key=AUTOBOT_GEMINI_API_KEY or extra_config.GEMINI_API_KEY
).aio

# --- Model Config ---
SAFETY_OFF = [
    SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="OFF"),
]

AUTOBOT_MODEL = "gemini-2.5-flash"
AUTOBOT_CONFIG = GenerateContentConfig(
    candidate_count=1,
    system_instruction=SYSTEM_PROMPT,
    temperature=0.9,
    max_output_tokens=1024,
    safety_settings=SAFETY_OFF,
    thinking_config=ThinkingConfig(thinking_budget=0),
)


def _get_current_model() -> str:
    """Get the current model from the MODEL_LIST."""
    return MODEL_LIST[_current_model_idx]


def _cycle_model():
    """Cycle to the next model in the list."""
    global _current_model_idx, _requests_since_cycle
    _current_model_idx = (_current_model_idx + 1) % len(MODEL_LIST)
    _requests_since_cycle = 0
    LOGGER.info(f"Autobot: cycled model to {_get_current_model()}")


# Regex to match <REPLY:MSG_ID> at the start of response
_REPLY_PATTERN = re.compile(r"^<REPLY:(\d+)>\s*")


def _get_sender_name(message) -> str:
    """Extract sender name from message."""
    if message.from_user:
        return message.from_user.first_name or "Unknown"
    if message.sender_chat:
        return message.sender_chat.title or "Unknown"
    return "Unknown"


def _is_reactive(message) -> bool:
    """Check if message directly mentions the bot or replies to it."""
    text_to_check = message.text or message.caption
    if text_to_check:
        text_lower = text_to_check.lower().strip()
        if f"@{BOT_USERNAME}" in text_lower or "reya" in text_lower:
            return True

    # Reply to bot's own message
    if message.reply_to_message:
        reply_from = message.reply_to_message.from_user
        if (
            reply_from
            and reply_from.username
            and reply_from.username.lower() == BOT_USERNAME.lower()
        ):
            return True

    return False


async def _generate_response(history: list, contextual: bool = False) -> str | None:
    """Send history to Gemini and get a response."""
    global _requests_since_cycle, _last_logged_model
    try:
        contents = list(history)

        if contextual:
            # Add contextual analysis prompt
            from google.genai import types

            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text="[SYSTEM] evaluate the recent conversation. "
                            "if anything is worth replying to or you have something to say, "
                            "reply naturally. if not, respond with only <THINK> followed by a brief thought."
                        )
                    ],
                )
            )

        # Auto-cycle model if reached limit
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


async def _send_response(chat_id: int, response_text: str, reply_to: int | None = None):
    """Parse response for REPLY/THINK/SPLIT delimiters and send."""
    from pyrogram.types import ReplyParameters

    full_response = response_text.strip()

    # 1. Check for <REPLY:MSG_ID> — overrides any passed-in reply_to
    reply_match = _REPLY_PATTERN.match(full_response)
    if reply_match:
        reply_to = int(reply_match.group(1))
        full_response = full_response[reply_match.end() :].strip()

    # 2. Split out internal thoughts
    if THINK_DELIMITER in full_response:
        parts = full_response.split(THINK_DELIMITER, 1)
        sendable = parts[0].strip()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if SPLIT_DELIMITER in rest:
            thought_part, after_thought = rest.split(SPLIT_DELIMITER, 1)
            thought = thought_part.strip()
            if sendable:
                sendable += f" {SPLIT_DELIMITER} {after_thought.strip()}"
            else:
                sendable = after_thought.strip()
        else:
            thought = rest
    else:
        sendable = full_response
        thought = ""

    # Store full response (including thoughts) in history
    await append_model_message(response_text.strip())

    # If nothing to send (pure thought), we're done
    if not sendable:
        if thought:
            LOGGER.info(f"Autobot thought: {thought[:100]}")
        return

    # 3. Split into multiple messages
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

            # Random delay between multi-texts
            if i < len(messages) - 1:
                await asyncio.sleep(random.uniform(0.5, 2.0))

        except Exception as e:
            LOGGER.error(f"Autobot: send error: {e}")


@_bot.on_message(
    filters=filters.chat(_DEFAULT_TARGET_CHAT_ID)
    & ~filters.service
    & (filters.text | filters.caption)
)
async def autobot_handler(_bot_client, message):
    """Main message handler for autobot."""
    global _msg_counter, _active_until, _active_msg_count

    # Skip if not the current target chat (may have been changed via -id)
    if message.chat.id != _target_chat_id:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    if not _autobot_enabled:
        return

    now = datetime.now()

    # 1. If this is the bot's own message, store as model role and stop
    if message.from_user and message.from_user.is_self:
        await append_model_message(text)
        return

    sender_name = _get_sender_name(message)

    # 2. Build user text — quote reya's original message if this is a reply to her
    user_text = text
    if (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.username
        and message.reply_to_message.from_user.username.lower() == BOT_USERNAME.lower()
    ):
        quoted = message.reply_to_message.text or message.reply_to_message.caption or ""
        if quoted:
            user_text = f'[quoting reya: "{quoted}"] {text}'

    # 3. Append incoming message to history as user role
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

    # 4. Evaluate triggers (priority order)

    # Reactive: 100% trigger
    if _is_reactive(message):
        should_reply = True
        reply_to_id = message.id
        _msg_counter = 0

    # Proactive: random chance
    elif random.randint(1, 100) <= PROACTIVE_CHANCE:
        should_reply = True
        # Activate active mode
        _active_until = time.time() + ACTIVE_DURATION
        _active_msg_count = 0
        _msg_counter = 0
        reply_to_id = None  # can drop independent text

    # Active mode: reply every N messages
    elif time.time() < _active_until:
        _active_msg_count += 1
        if _active_msg_count >= ACTIVE_MSG_INTERVAL:
            should_reply = True
            _active_msg_count = 0
            reply_to_id = None

    # Contextual: every N messages
    if not should_reply and _msg_counter >= CONTEXTUAL_INTERVAL:
        _msg_counter = 0
        should_reply = True
        is_contextual = True
        reply_to_id = None

    if not should_reply:
        return

    # 3. Generate response
    response_text = await _generate_response(history, contextual=is_contextual)

    if not response_text:
        return

    # 4. Send response
    await _send_response(
        chat_id=_target_chat_id,
        response_text=response_text,
        reply_to=reply_to_id,
    )


@bot.add_cmd(cmd="ry")
async def reya_cmd(bot: BOT, message: Message):
    """
    CMD: RY
    INFO: Control the autobot.
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
