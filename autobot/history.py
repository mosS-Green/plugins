import json
import os
from datetime import datetime

import aiofiles
from google.genai import types

from .config import HISTORY_FILE, HISTORY_SEED_MSG_ID, LOG_CHAT


def _content_to_dict(content: types.Content) -> dict:
    """Serialize a types.Content to a simple dict."""
    text = ""
    if content.parts:
        text = content.parts[0].text or ""
    return {"role": content.role, "text": text}


def _dict_to_content(d: dict) -> types.Content:
    """Deserialize a dict back to types.Content."""
    return types.Content(
        role=d["role"],
        parts=[types.Part.from_text(text=d["text"])],
    )


async def load_history() -> list[types.Content]:
    """Load conversation history from file."""
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        async with aiofiles.open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return [_dict_to_content(d) for d in data]
    except (json.JSONDecodeError, KeyError, Exception):
        return []


async def save_history(history: list[types.Content]):
    """Save conversation history to file."""
    data = [_content_to_dict(c) for c in history]
    async with aiofiles.open(HISTORY_FILE, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


def _ensure_alternating(history: list[types.Content]) -> list[types.Content]:
    """Ensure history alternates user/model roles (Gemini API requirement).
    Consecutive same-role messages get merged."""
    if not history:
        return history

    merged = [history[0]]
    for entry in history[1:]:
        if entry.role == merged[-1].role:
            # Merge text into previous
            prev_text = merged[-1].parts[0].text if merged[-1].parts else ""
            curr_text = entry.parts[0].text if entry.parts else ""
            merged[-1] = types.Content(
                role=entry.role,
                parts=[types.Part.from_text(text=f"{prev_text}\n{curr_text}")],
            )
        else:
            merged.append(entry)

    return merged


async def append_user_message(
    msg_id: int, dt: datetime, sender_name: str, text: str
) -> list[types.Content]:
    """Append a user message with metadata to history and save."""
    history = await load_history()

    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M")
    formatted = f"{msg_id} | {date_str} {time_str} | [{sender_name}] {text}"

    history.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=formatted)],
        )
    )

    history = _ensure_alternating(history)
    await save_history(history)
    return history


async def append_model_message(text: str) -> list[types.Content]:
    """Append a model response to history and save."""
    history = await load_history()

    history.append(
        types.Content(
            role="model",
            parts=[types.Part.from_text(text=text)],
        )
    )

    history = _ensure_alternating(history)
    await save_history(history)
    return history


async def seed_from_log(bot_client):
    """Seed history from a txt document in LOG chat on first run."""
    if os.path.exists(HISTORY_FILE):
        history = await load_history()
        if history:
            return

    if not LOG_CHAT or HISTORY_SEED_MSG_ID == "xyz123":
        # Placeholder not replaced or no log chat, create empty history
        await save_history([])
        return

    try:
        msg_id = int(HISTORY_SEED_MSG_ID)
        message = await bot_client.get_messages(chat_id=LOG_CHAT, message_ids=msg_id)

        if message and message.document:
            # Download the txt file and read its content
            file_path = await message.download()
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = await f.read()
            os.remove(file_path)

            if content.strip():
                initial = [
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=content.strip())],
                    )
                ]
                await save_history(initial)
                return

        # Fallback: if it's a text message instead
        if message and message.text:
            initial = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=message.text)],
                )
            ]
            await save_history(initial)
            return

        await save_history([])
    except Exception:
        await save_history([])
