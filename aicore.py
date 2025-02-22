import os
import asyncio
import shutil
import time
from mimetypes import guess_type
from google.genai.types import ( # type: ignore
    GenerateContentConfig,
    SafetySetting,
    Tool,
    GoogleSearchRetrieval,
    DynamicRetrievalConfig,
)

from pyrogram.types.messages_and_media import Audio, Photo, Video, Voice
from ub_core.utils import get_tg_media_details # type: ignore

from app import Message # type: ignore
from app.plugins.ai.models import async_client # type: ignore

safety = [
    SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
    SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
    SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
    SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="BLOCK_NONE"),
]


def create_config(model, instruction, temp, tokens, search):
    return {
        "model": model,
        "config": GenerateContentConfig(
            candidate_count=1,
            system_instruction=instruction,
            temperature=temp,
            max_output_tokens=tokens,
            safety_settings=safety,
            tools=search,
        ),
    }


SEARCH_TOOL = Tool(
    google_search=GoogleSearchRetrieval(
        dynamic_retrieval_config=DynamicRetrievalConfig(dynamic_threshold=0.3)
    )
)


model_cfg = {
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

MODEL = model_cfg


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
    prompt: str, query: Message | None = None, quote: bool = False, **kwargs
) -> str:
    media = None
    prompts = [prompt]

    if query:
        prompts = [str(query.text), prompt or "answer"]
        media = get_tg_media_details(query)

    if media is not None:
        if getattr(media, "file_size", 0) >= 1048576 * 25:
            return "Error: File Size exceeds 25mb."

        prompt = prompt.strip() or PROMPT_MAP.get(
            type(media), "Analyse the file and explain."
        )

        download_dir = os.path.join("downloads", str(time.time())) + "/"
        downloaded_file: str = await query.download(download_dir)

        uploaded_file = await async_client.files.upload(
            file=downloaded_file,
            config={
                "mime_type": getattr(media, "mime_type", guess_type(downloaded_file)[0])
            },
        )

        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(5)
            uploaded_file = await async_client.files.get(name=uploaded_file.name)

        prompts = [uploaded_file, prompt]

        shutil.rmtree(download_dir, ignore_errors=True)

    response = await async_client.models.generate_content(**kwargs, contents=prompts)
    ai_response = get_text(response, quoted=quote)

    return ai_response


def get_text(response, quoted: bool = False):
    candidate = response.candidates[0]

    text = "\n".join([part.text for part in candidate.content.parts])

    final_text = text.strip()

    return f"**>\n{final_text}<**" if quoted and "```" not in final_text else final_text
