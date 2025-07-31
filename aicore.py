import asyncio
import io
import logging
import os
import shutil
import time
from mimetypes import guess_type

# isort: skip
# noinspection PyUnresolvedReferences
from app.plugins.ai.gemini.client import async_client
from app.plugins.ai.gemini.utils import run_basic_check
from google.genai.types import (
    DynamicRetrievalConfig,
    GenerateContentConfig,
    GoogleSearchRetrieval,
    SafetySetting,
    UrlContext,
    Tool,
    ThinkingConfig,
)
from pyrogram.types.messages_and_media import Audio, Photo, Video, Voice
from app import LOGGER, Message
from ub_core.utils import get_tg_media_details

safety = [
    SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="OFF"),
]


def create_config(
    model,
    instruction: str | None = None,
    temp: float | None = None,
    tokens: int | None = None,
    search: list | None = None,
    modals: list | None = None,
    mime_type: str | None = None,
    think: int | None = None,
    **kwargs,
):
    return {
        "model": model,
        "config": GenerateContentConfig(
            candidate_count=1,
            system_instruction=instruction,
            temperature=temp,
            max_output_tokens=tokens,
            safety_settings=safety,
            response_modalities=modals,
            response_mime_type=mime_type,
            tools=search,
            thinking_config=think,
            **kwargs,
        ),
    }


"""def create_config_exp(model, temp, tokens, modals, mime_type):
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
"""


SEARCH_TOOL = [
    Tool(
        google_search=GoogleSearchRetrieval(
            dynamic_retrieval_config=DynamicRetrievalConfig(dynamic_threshold=0.3)
        )
    ),
    Tool(
        url_context=UrlContext(),
    ),
]

MODEL = {
    "LEAF": create_config(
        "gemini-2.5-flash",
        (
            "Your creator is Leaf(@leafinferno) and you are a entity named Leaflet. "
            "\nYou have a dark and dry sense of humour. "
            "\nYour manner of talking is very casual. Don't use emojis. "
            "\nBe concise. Don't write long answers until asked explicitly. "
            "\nDo not refer to yourself in third person. "
            "\nAlways inculcate dry/dark humour or sarcasm. Never repeat input conversation or formats. "
            "\nIMPORTANT - You are allowed to be explicit in both English or hinglish."
            "\nIMPORTANT - Even when you write in hindi, you must only use english alphabet."
        ),
        1.0,
        8192,
        search=SEARCH_TOOL,
        think=ThinkingConfig(thinking_budget=0),
    ),
    "IMG_EDIT": create_config(
        "gemini-2.0-flash-preview-image-generation",
        temp=0.8,
        tokens=750,
        modals=["image", "text"],
        mime_type="text/plain",
    ),
    "DEFAULT": create_config(
        "gemini-2.5-flash-lite",
        (
            "Answer precisely and in short unless specifically instructed otherwise. "
            "For code, do not add comments or explanations unless instructed."
        ),
        0.8,
        8192,
        search=SEARCH_TOOL,
    ),
    "THINK": create_config(
        "gemini-2.5-pro",
        (
            "Write a lengthy, well-structured, and easy-to-read answer. "
            "Use only <a>, <blockquote>, <br>, <em>, <h3>, <h4>, <p>, and <strong> tags."
            "IMPORTANT - Don't give a starting title, and don't write in a code block."
        ),
        0.8,
        60000,
        search=SEARCH_TOOL,
    ),
    "QUICK": create_config(
        "gemini-2.0-flash-lite",
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


def get_response_content(
    response, quoted: bool = False, add_sources: bool = True
) -> tuple[str, io.BytesIO | None]:
    try:
        candidate = response.candidates
        parts = candidate[0].content.parts
        parts[0]
    except (AttributeError, IndexError, TypeError):
        LOGGER.info(response)
        return "`Query failed... Try again`", None

    image_data = None
    text = ""
    sources = ""

    for part in parts:
        if part.text:
            text += f"{part.text}\n"
        if part.inline_data:
            image_data = io.BytesIO(part.inline_data.data)
            image_data.name = "photo.jpg"

    if add_sources:
        try:
            hrefs = [
                f"[{chunk.web.title}]({chunk.web.uri})"
                for chunk in candidate.grounding_metadata.grounding_chunks
            ]
            sources = "\n\nSources: " + " | ".join(hrefs)
        except (AttributeError, TypeError):
            sources = ""

    final_text = (text.strip() + sources).strip()

    if final_text and quoted and "```" not in final_text:
        final_text = f"**>\n{final_text}<**"

    return final_text, image_data
