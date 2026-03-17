import json
import os

import aiofiles

from .config import HISTORY_DIR, MAX_HISTORY_SIZE

os.makedirs(HISTORY_DIR, exist_ok=True)


def _history_path(chat_id: int) -> str:
    return os.path.join(HISTORY_DIR, f"{chat_id}.json")


async def load_history(chat_id: int) -> list[dict]:
    path = _history_path(chat_id)
    if not os.path.exists(path):
        return []
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    except (json.JSONDecodeError, Exception):
        return []


async def save_history(chat_id: int, history: list[dict]):
    async with aiofiles.open(_history_path(chat_id), "w", encoding="utf-8") as f:
        await f.write(json.dumps(history, ensure_ascii=False, indent=2))


def _ensure_alternating(history: list[dict]) -> list[dict]:
    """Merge consecutive same-role entries."""
    if not history:
        return history

    merged = [history[0]]
    for entry in history[1:]:
        if entry["role"] == merged[-1]["role"]:
            prev_text = merged[-1]["parts"][0]["text"] if merged[-1]["parts"] else ""
            curr_text = entry["parts"][0]["text"] if entry["parts"] else ""
            merged[-1] = {
                "role": entry["role"],
                "parts": [{"text": f"{prev_text}\n{curr_text}"}],
            }
        else:
            merged.append(entry)
    return merged


def _trim_history(history: list[dict]) -> list[dict]:
    if len(history) > MAX_HISTORY_SIZE:
        history = history[-MAX_HISTORY_SIZE:]
        while history and history[0]["role"] != "user":
            history = history[1:]
    return history


async def append_user_message(chat_id: int, text: str) -> list[dict]:
    history = await load_history(chat_id)
    history.append({"role": "user", "parts": [{"text": text}]})
    history = _ensure_alternating(history)
    history = _trim_history(history)
    await save_history(chat_id, history)
    return history


async def append_model_message(chat_id: int, text: str) -> list[dict]:
    history = await load_history(chat_id)
    history.append({"role": "model", "parts": [{"text": text}]})
    history = _ensure_alternating(history)
    history = _trim_history(history)
    await save_history(chat_id, history)
    return history


def clear_history(chat_id: int):
    path = _history_path(chat_id)
    if os.path.exists(path):
        os.remove(path)
