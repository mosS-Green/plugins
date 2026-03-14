import json
import os
from datetime import datetime

import aiofiles
from google.genai import types

from .config import HISTORY_FILE, MAX_HISTORY_SIZE


def _content_to_dict(content: types.Content) -> dict:
    text = ""
    if content.parts:
        text = content.parts[0].text or ""
    return {"role": content.role, "text": text}


def _dict_to_content(d: dict) -> types.Content:
    return types.Content(
        role=d["role"],
        parts=[types.Part.from_text(text=d["text"])],
    )


async def load_history() -> list[types.Content]:
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        async with aiofiles.open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return [_dict_to_content(d) for d in data]
    except (json.JSONDecodeError, KeyError, Exception):
        return []


async def save_history(history: list[types.Content]):
    data = [_content_to_dict(c) for c in history]
    async with aiofiles.open(HISTORY_FILE, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


def _ensure_alternating(history: list[types.Content]) -> list[types.Content]:
    if not history:
        return history

    merged = [history[0]]
    for entry in history[1:]:
        if entry.role == merged[-1].role:
            prev_text = merged[-1].parts[0].text if merged[-1].parts else ""
            curr_text = entry.parts[0].text if entry.parts else ""
            merged[-1] = types.Content(
                role=entry.role,
                parts=[types.Part.from_text(text=f"{prev_text}\n{curr_text}")],
            )
        else:
            merged.append(entry)

    return merged


def _trim_history(history: list[types.Content]) -> list[types.Content]:
    if len(history) > MAX_HISTORY_SIZE:
        history = history[-MAX_HISTORY_SIZE:]
        while history and history[0].role != "user":
            history = history[1:]
    return history


async def append_user_message(
    msg_id: int, dt: datetime, sender_name: str, text: str
) -> list[types.Content]:
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
    history = _trim_history(history)
    await save_history(history)
    return history


async def append_model_message(text: str) -> list[types.Content]:
    history = await load_history()

    history.append(
        types.Content(
            role="model",
            parts=[types.Part.from_text(text=text)],
        )
    )

    history = _ensure_alternating(history)
    history = _trim_history(history)
    await save_history(history)
    return history
