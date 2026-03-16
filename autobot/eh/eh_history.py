import json
import os
from datetime import datetime

import aiofiles

from app.modules.autobot.config import HISTORY_DIR, MAX_HISTORY_SIZE

os.makedirs(HISTORY_DIR, exist_ok=True)


def _chat_history_path(chat_id: int) -> str:
    return os.path.join(HISTORY_DIR, f"{chat_id}.json")


async def load_history(chat_id: int) -> list[dict]:
    path = _chat_history_path(chat_id)
    if not os.path.exists(path):
        return []

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return data
    except (json.JSONDecodeError, KeyError, Exception):
        return []


async def save_history(chat_id: int, history: list[dict]):
    async with aiofiles.open(_chat_history_path(chat_id), "w", encoding="utf-8") as f:
        await f.write(json.dumps(history, ensure_ascii=False, indent=2))


def _ensure_alternating(history: list[dict]) -> list[dict]:
    if not history:
        return history

    merged = [history[0].copy()]
    for entry in history[1:]:
        if entry["role"] == merged[-1]["role"]:
            prev_text = merged[-1].get("text", "")
            curr_text = entry.get("text", "")
            merged[-1]["text"] = f"{prev_text}\n{curr_text}"
        else:
            merged.append(entry.copy())

    return merged


def _trim_history(history: list[dict]) -> list[dict]:
    if len(history) > MAX_HISTORY_SIZE:
        history = history[-MAX_HISTORY_SIZE:]
        while history and history[0]["role"] != "user":
            history = history[1:]
    return history


async def append_user_message(
    chat_id: int, msg_id: int, dt: datetime, sender_name: str, text: str
) -> list[dict]:
    history = await load_history(chat_id)

    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M")
    formatted = f"{msg_id} | {date_str} {time_str} | [{sender_name}] {text}"

    history.append({"role": "user", "text": formatted})

    history = _ensure_alternating(history)
    history = _trim_history(history)
    await save_history(chat_id, history)
    return history


async def append_model_message(chat_id: int, text: str) -> list[dict]:
    history = await load_history(chat_id)

    history.append({"role": "model", "text": text})

    history = _ensure_alternating(history)
    history = _trim_history(history)
    await save_history(chat_id, history)
    return history
