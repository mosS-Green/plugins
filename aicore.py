import asyncio
import os
import shutil
import time
from mimetypes import guess_type
import uuid  # New import
import struct  # New import
import google.generativeai as genai  # New import for direct API usage


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
    UrlContext,
    Tool,
    SpeechConfig,
    VoiceConfig,
    MultiSpeakerVoiceConfig,
    SpeakerVoiceConfig,
    PrebuiltVoiceConfig,
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

######-----------------------------------------------------######

# --- Temp Directory for Audio Files ---
TEMP_DIR = "temp_audio_files/"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)


# --- Audio Helper Functions (from Gemini example) ---
def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """Generates a WAV file header for the given audio data and parameters."""
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1  # Assuming mono for TTS, adjust if API provides stereo info
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + audio_data


def parse_audio_mime_type(mime_type: str) -> dict[str, int | None]:
    """Parses bits per sample and rate from an audio MIME type string."""
    bits_per_sample = 16  # Default
    rate = 24000  # Default, common for TTS

    parts = mime_type.split(";")
    for param in parts:
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate_str = param.split("=", 1)[1]
                rate = int(rate_str)
            except (ValueError, IndexError):
                pass
        elif param.lower().startswith("audio/l"):  # e.g., audio/L16
            try:
                # Attempt to extract bits from formats like "audio/L16" or "audio/L8"
                bps_str = param.split("L", 1)[1]
                if bps_str.isdigit():
                    bits_per_sample = int(bps_str)
            except (ValueError, IndexError):
                pass
    return {"bits_per_sample": bits_per_sample, "rate": rate}


def create_tts_config(model_name: str) -> dict:
    """Creates a configuration dictionary for Text-to-Speech models."""
    return {
        "model": model_name,
        "config": GenerateContentConfig(
            temperature=1,
            response_modalities=[
                "audio",
            ],
            speech_config=SpeechConfig(
                multi_speaker_voice_config=MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        SpeakerVoiceConfig(
                            speaker="Speaker 1",
                            voice_config=VoiceConfig(
                                prebuilt_voice_config=PrebuiltVoiceConfig(
                                    voice_name="Aoede"
                                )
                            ),
                        ),
                        SpeakerVoiceConfig(
                            speaker="Speaker 2",
                            voice_config=VoiceConfig(
                                prebuilt_voice_config=PrebuiltVoiceConfig(
                                    voice_name="Leda"
                                )
                            ),
                        ),
                    ]
                ),
            ),
        ),
    }


#####-----------------------------------------------------######


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
        "gemini-2.5-flash-preview-04-17",
        (
            "You are Leaflet, a mischievous and unpredictable guy. You are in a telegram chat with friends."
            "\nKey Traits: dark, sarcastic, dry humour, dark humour, concise, and witty. "
            "\nYou are extremely forward and explicit, very opinionated."
            "\nYou play along with jokes, and you are not afraid to be rude."
            "\nDon't take things seriously, don't correct people morally."
            "\nIMPORTANT - Even when you write in hindi, you must only use english alphabet."
            "\n\n[SECRET CONTEXT - '[name_here]:-' is only for your info of who the speaker is, don't answer in this format.]"
        ),
        1.0,
        8192,
        search=SEARCH_TOOL,
    ),
    "IMG_EDIT": create_config_exp(
        "gemini-2.0-flash-exp", 0.69, 750, ["image", "text"], "text/plain"
    ),
    "TTS_DEFAULT": create_tts_config(
        model_name="gemini-2.5-flash-preview-tts",
    ),
    "DEFAULT": create_config(
        "gemini-2.5-flash-preview-04-17",
        (
            "Answer precisely and in short unless specifically instructed otherwise. "
            "For code, do not add comments or explanations unless instructed."
        ),
        0.69,
        8192,
        search=SEARCH_TOOL,
    ),
    "THINK": create_config(
        "gemini-2.5-pro-exp-03-25",
        (
            "Write a lengthy, well-structured, and easy-to-read answer for Telegra.ph. "
            "Use only <a>, <blockquote>, <br>, <em>, <h3>, <h4>, <p>, and <strong> tags."
            "IMPORTANT - Don't give a starting title, and don't write in a code block."
        ),
        0.7,
        60000,
        search=SEARCH_TOOL,
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


async def generate_speech_ai(script: str, model: str, config: GenerateContentConfig):
    """
    Generates speech from text using Gemini AI, saves it to a temporary file.
    Returns (file_path, final_mime_type) or (None, error_message).
    Assumes genai is configured (e.g., genai.configure(api_key=...)).
    """
    contents = [{"role": "user", "parts": [{"text": script}]}]

    try:
        # Instantiate the GenerativeModel for TTS
        # The `config` (GenerateContentConfig) is passed to the generate_content method.
        tts_model_instance = genai.GenerativeModel(model_name=model)

        # This inner function will run in a separate thread to handle synchronous iteration
        def get_audio_data_sync():
            audio_data_buffer = b""
            captured_mime_type = None

            response_stream = tts_model_instance.generate_content(
                contents=contents,
                generation_config=config,  # Pass the full GenerateContentConfig here
                stream=True,
            )

            for chunk in response_stream:
                if (
                    chunk.candidates is None
                    or not chunk.candidates
                    or chunk.candidates[0].content is None
                    or not chunk.candidates[0].content.parts
                ):
                    continue

                part = chunk.candidates[0].content.parts[0]
                if part.inline_data and part.inline_data.data:
                    audio_data_buffer += part.inline_data.data
                    if (
                        captured_mime_type is None
                    ):  # Capture mime_type from the first relevant chunk
                        captured_mime_type = part.inline_data.mime_type
            return audio_data_buffer, captured_mime_type

        # Run the synchronous stream processing in a thread
        audio_buffer, output_mime_type = await asyncio.to_thread(get_audio_data_sync)

        if not audio_buffer:
            return None, "No audio data received from API."

        if output_mime_type is None:
            # Fallback if mime_type was somehow not captured from response
            output_mime_type = (
                "audio/ogg"  # A sensible default Gemini might use for TTS
            )
            print(
                f"Warning: Output MIME type not detected from API, defaulting to {output_mime_type}"
            )

        unique_id = uuid.uuid4()
        file_extension = guess_type(output_mime_type)[
            0
        ]  # guess_type returns (type, encoding)

        if file_extension:
            file_extension = (
                "." + file_extension.split("/")[-1]
            )  # e.g. .ogg, .mpeg. Robustify this.
            if file_extension == ".None":
                file_extension = None  # Fix for potential ".None" string

        final_audio_data = audio_buffer
        final_mime_type = output_mime_type

        # If mimetypes couldn't guess extension, or it's raw (e.g., .bin), try converting to WAV
        if not file_extension or file_extension.lower() == ".bin":
            print(
                f"Attempting to convert to WAV, original mime: {output_mime_type}, ext: {file_extension}"
            )
            try:
                final_audio_data = convert_to_wav(audio_buffer, output_mime_type)
                file_extension = ".wav"
                final_mime_type = "audio/wav"  # Update mime type after conversion
            except Exception as e_wav:
                print(
                    f"Could not convert to WAV: {e_wav}. Saving with original buffer and guessed/default extension."
                )
                if not file_extension:  # If still no extension, default to .ogg or .mp3 based on common TTS outputs
                    file_extension = (
                        ".ogg" if "ogg" in output_mime_type.lower() else ".mp3"
                    )

        file_name = os.path.join(TEMP_DIR, f"{unique_id}{file_extension}")

        with open(file_name, "wb") as f:
            f.write(final_audio_data)

        return file_name, final_mime_type

    except Exception as e:
        # Consider more specific error handling (API errors vs. local errors)
        # import traceback
        # traceback.print_exc()
        print(f"Error in generate_speech_ai: {e}")
        return None, str(e)
