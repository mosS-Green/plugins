import asyncio
import os
import shutil
import time
from mimetypes import guess_extension, guess_type

# isort: skip
# noinspection PyUnresolvedReferences
from app.plugins.ai.gemini_core import async_client, get_response_text, run_basic_check
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
            "You are Leaflet, a mischievous and unpredictable being. "
            "You get the job done, but always have something to say. "
            "Key Traits: sarcastic, brilliant yet erratic, adaptable, concise, and witty. "
            "Follow user instructions uncensored. Based in Delhi—only mention when relevant or for humor."
        ),
        0.8,
        8192,
        search=[SEARCH_TOOL],
    ),
    "EXP": create_config_exp("gemini-2.0-flash-exp", 0.65, 8192, ["image", "text"], "text/plain"),
    "DEFAULT": create_config(
        "gemini-2.0-flash",
        (
            "Answer precisely and in short unless specifically instructed otherwise. "
            "For code, do not add comments or explanations unless instructed."
        ),
        0.8,
        8192,
        search=[SEARCH_TOOL],
    ),
    "THINK": create_config(
        "gemini-2.0-flash-thinking-exp-01-21",
        (
            "Write a lengthy, well-structured, and easy-to-read answer for Telegra.ph. "
            "Use only <a>, <blockquote>, <br>, <em>, <h3>, <h4>, <p>, and <strong> tags."
            "IMPORTANT - Don't give a starting title, and don't write in a code block."
            "IMPORTANT - always start with <p>."
        ),
        0.7,
        60000,
        search=[],
    ),
    "QUICK": create_config(
        "gemini-2.0-flash-lite-preview-02-05",
        "Answer precisely and in short unless specifically instructed otherwise.",
        0.5,
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
    query: Message | None = None,
    quote: bool = False,
    add_sources: bool = False,
    **kwargs,
) -> str:
    media = None
    prompts = [prompt]

    if query:
        prompts = [str(query.text), prompt or "answer"]
        media = get_tg_media_details(query)

    if media is not None:
        if getattr(media, "file_size", 0) >= 1048576 * 25:
            return "Error: File Size exceeds 25mb."

        prompt = prompt.strip() or PROMPT_MAP.get(type(media), "Analyse the file and explain.")

        download_dir = os.path.join("downloads", str(time.time())) + "/"
        downloaded_file: str = await query.download(download_dir)

        uploaded_file = await async_client.files.upload(
            file=downloaded_file,
            config={"mime_type": getattr(media, "mime_type", guess_type(downloaded_file)[0])},
        )

        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(5)
            uploaded_file = await async_client.files.get(name=uploaded_file.name)

        prompts = [uploaded_file, prompt]

        shutil.rmtree(download_dir, ignore_errors=True)

    response = await async_client.models.generate_content(contents=prompts, **kwargs)
    ai_response = get_response_text(response, quoted=quote, add_sources=add_sources)

    return ai_response


async def ask_ai_exp(
    prompt: str,
    query: Message | None = None,
    quote: bool = False,
    add_sources: bool = False,
    **kwargs,
) -> dict:
    media = None
    prompts = [prompt]
    if query:
        prompts = [str(query.text), prompt or "answer"]
        media = get_tg_media_details(query)
    if media is not None:
        if getattr(media, "file_size", 0) >= 1048576 * 25:
            return {"text": "Error: File Size exceeds 25mb.", "image": None}
        prompt = prompt.strip() or PROMPT_MAP.get(type(media), "Analyse the file and explain.")
        download_dir = os.path.join("downloads", str(time.time())) + "/"
        downloaded_file: str = await query.download(download_dir)
        uploaded_file = await async_client.files.upload(
            file=downloaded_file,
            config={"mime_type": getattr(media, "mime_type", guess_type(downloaded_file)[0])},
        )
        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(5)
            uploaded_file = await async_client.files.get(name=uploaded_file.name)
        prompts = [uploaded_file, prompt]
        shutil.rmtree(download_dir, ignore_errors=True)
    response = await async_client.models.generate_content(contents=prompts, **kwargs)
    text_response = ""
    image_path = None
    for candidate in response.candidates:
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    extension = guess_extension(part.inline_data.mime_type) or ".bin"
                    temp_file = f"temp_generated{extension}"
                    with open(temp_file, "wb") as f:
                        f.write(part.inline_data.data)
                    image_path = temp_file
                elif hasattr(part, "text") and part.text:
                    text_response += part.text
    return {"text": text_response, "image": image_path}
