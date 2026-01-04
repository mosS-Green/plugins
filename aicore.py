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
    Content,
    Part,
    FunctionResponse,
)
from pyrogram.types.messages_and_media import Audio, Photo, Video, Voice
from app import LOGGER, Message
from ub_core.utils import get_tg_media_details
from app.modules.ai_sandbox.tools import MUSIC_TOOL, LIST_TOOL
from app.modules.ai_sandbox.functions import execute_function

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
    """Creates a model configuration dict for Gemini API calls."""
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


SEARCH_TOOL = [
    Tool(
        google_search=GoogleSearchRetrieval(
            dynamic_retrieval_config=DynamicRetrievalConfig(dynamic_threshold=0.6)
        )
    ),
    Tool(
        url_context=UrlContext(),
    ),
]

from .prompts import SYSTEM_PROMPTS

MODEL = {
    "LEAF": create_config(
        "gemini-3-flash-preview",
        SYSTEM_PROMPTS["LEAF"],
        1.0,
        8192,
        search=[],
        think=ThinkingConfig(thinking_budget=0),
    ),
    "FUNC": create_config(
        "gemini-flash-latest",
        SYSTEM_PROMPTS["FUNC"],
        0.8,
        8192,
        search=[MUSIC_TOOL, LIST_TOOL],
        think=ThinkingConfig(thinking_budget=0),
    ),
    "DEFAULT": create_config(
        "gemini-flash-latest",
        SYSTEM_PROMPTS["DEFAULT"],
        1.0,
        8192,
        search=SEARCH_TOOL,
        think=ThinkingConfig(thinking_budget=0),
    ),
    "THINK": create_config(
        "gemini-3-flash-preview",
        SYSTEM_PROMPTS["THINK"],
        0.8,
        60000,
        search=[],
    ),
    "QUICK": create_config(
        "gemini-flash-lite-latest",
        SYSTEM_PROMPTS["QUICK"],
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
        "\n\nIMPORTANT - ROMANISE ALL LANGUAGES TO ENGLISH ALPHABET."
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
    """Sends a prompt to the AI model and returns the response text."""
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

    # Initial Prompt
    contents = [prompt_combined]

    # Turn 1
    response = await async_client.models.generate_content(contents=contents, **kwargs)

    if not response.candidates and response.prompt_feedback:
        block_reason = response.prompt_feedback.block_reason or "UNKNOWN"
        return f"Prompt blocked: {block_reason}", None

    # Check for function call
    try:
        part = response.candidates[0].content.parts[0]
    except (AttributeError, IndexError):
        part = None

    if part and part.function_call:
        # Execute function
        return await execute_function(part)

    ai_text, ai_image = await get_response_content(
        response, quoted=quote, add_sources=add_sources
    )

    return (ai_text, ai_image) if img else ai_text


async def get_response_content(
    response, quoted: bool = False, add_sources: bool = True
) -> tuple[str, io.BytesIO | None]:
    """Extracts text and image data from a Gemini API response."""
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
