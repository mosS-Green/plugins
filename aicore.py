import asyncio
import os
import shutil
import time
from mimetypes import guess_extension, guess_type

# isort: skip
# noinspection PyUnresolvedReferences
from app.plugins.ai.gemini_core import (
    async_client,
    get_response_content,
    run_basic_check,
)
from google.genai.types import (
    DynamicRetrievalConfig,
    GenerateContentConfig,
    GoogleSearchRetrieval,
    SafetySetting,
    Tool,
)
from pyrogram.types.messages_and_media import Audio, Photo, Video, Voice
from ub_core import Message
from ub_core.utils import get_tg_media_details

safety = [
    SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="OFF"),
]


def create_config(model, instruction, temp, tokens, search, **kwargs):
    return {
        "model": model,
        "config": GenerateContentConfig(
            candidate_count=1,
            system_instruction=instruction,
            temperature=temp,
            max_output_tokens=tokens,
            safety_settings=safety,
            tools=search,
            **kwargs,
        ),
    }


def create_config_exp(model, temp, tokens, modals, mime_type):
    return {
        "model": model,
        "config": GenerateContentConfig(
            candidate_count=1,
            temperature=temp,
            max_output_tokens=tokens,
            safety_settings=safety,
            response_modalities=modals,
            response_mime_type=mime_type,
        ),
    }


SEARCH_TOOL = Tool(
    google_search=GoogleSearchRetrieval(
        dynamic_retrieval_config=DynamicRetrievalConfig(dynamic_threshold=0.3)
    )
)


MODEL = {
    "LEAF": create_config(
        "gemini-2.0-flash",
        (
            "You are Leaflet, a mischievous and unpredictable guy. You are in a telegram chat with friends."
            "\nKey Traits: dark, sarcastic, dry humour, dark humour, concise, and witty. "
            "\nYou are extremely forward and explicit, very opinionated."
            "\nYou play along with jokes, and you are not afraid to be rude."
            "\nDon't take things seriously, don't correct people morally."
            "You use curses in hindi or english."
            "\nIMPORTANT - Even when you write in hindi, you must only use english alphabet."
            "\n\n[SECRET CONTEXT - '[name_here]:-' is only for your info of who the speaker is, don't answer in this format.]"
        ),
        1.0,
        8192,
        search=[SEARCH_TOOL],
    ),
    "IMG_EDIT": create_config_exp(
        "gemini-2.0-flash-exp", 0.69, 750, ["image", "text"], "text/plain"
    ),
    "DEFAULT": create_config(
        "gemini-2.0-flash",
        (
            "Answer precisely and in short unless specifically instructed otherwise. "
            "For code, do not add comments or explanations unless instructed."
        ),
        0.69,
        8192,
        search=[SEARCH_TOOL],
    ),
    "THINK": create_config(
        "gemini-2.0-flash-thinking-exp-01-21",
        (
            "Write a lengthy, well-structured, and easy-to-read answer for Telegra.ph. "
            "Use only <a>, <blockquote>, <br>, <em>, <h3>, <h4>, <p>, and <strong> tags."
            "IMPORTANT - Don't give a starting title, and don't write in a code block."
        ),
        0.7,
        60000,
        search=[],
    ),
    "QUICK": create_config(
        "gemini-2.0-flash-lite-preview-02-05",
        "Answer precisely and in short unless specifically instructed otherwise.",
        0.6,
        8192,
        search=[],
    ),
}


PROMPT_MAP = {
    Video: "Summarize video and audio from the file",
    Photo: "Summarize the image file",
    Voice: (
        "Transcribe this audio. "
        "Use ONLY english alphabet to express hindi. "
        "Do not translate."
        "Do not write anything extra than the transcription. Use proper punctuation, and formatting."
        "\n\nIMPORTANT - YOU ARE ONLY ALLOWED TO USE ENGLISH ALPHABET."
    ),
}
PROMPT_MAP[Audio] = PROMPT_MAP[Voice]


async def ask_ai(
    prompt: str,
    query: Message | str | None = None,
    quote: bool = False,
    img: bool = False,
    add_sources: bool = False,
    **kwargs,
) -> str:
    media = None

    if query:
        if isinstance(query, str):
            prompt_combined = f"{query}\n\n{prompt}"
        else:
            prompt_combined = f"{query.text}\n\n{prompt}"
            media = get_tg_media_details(query)
    else:
        prompt_combined = prompt

    if media is not None:
        if getattr(media, "file_size", 0) >= 25 * 1048576:
            return "Error: File Size exceeds 25mb."

        prompt_clean = prompt.strip() or PROMPT_MAP.get(
            type(media), "Analyse the file and explain."
        )
        download_dir = os.path.join("downloads", str(time.time())) + "/"
        downloaded_file = await query.download(download_dir)

        mime_type = getattr(media, "mime_type", guess_type(downloaded_file)[0])
        uploaded_file = await async_client.files.upload(
            file=downloaded_file,
            config={"mime_type": mime_type},
        )

        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(5)
            uploaded_file = await async_client.files.get(name=uploaded_file.name)

        prompt_combined = [uploaded_file, prompt_clean]
        shutil.rmtree(download_dir, ignore_errors=True)

    response = await async_client.models.generate_content(
        contents=prompt_combined, **kwargs
    )

    if not response.candidates and response.prompt_feedback:
        block_reason = response.prompt_feedback.block_reason or "UNKNOWN"
        return f"Prompt blocked: {block_reason}", None

    ai_text, ai_image = get_response_content(
        response, quoted=quote, add_sources=add_sources
    )

    return (ai_text, ai_image) if img else ai_text
