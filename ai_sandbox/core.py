import asyncio
import io
import shutil
import time
import os
from mimetypes import guess_type
from app import LOGGER, Message
from ub_core.utils import get_tg_media_details
from app.plugins.ai.gemini.client import async_client
from app.modules.ai_sandbox.functions import execute_function
from .models import MODEL
from .prompts import PROMPT_MAP


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
