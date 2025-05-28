import os
import uuid
import struct

from app import BOT, Message, bot
from pyrogram.enums import ParseMode
from .aicore import async_client, run_basic_check
from mimetypes import guess_type
from google.genai.types import (
    GenerateContentConfig,
    SpeechConfig,
    VoiceConfig,
    MultiSpeakerVoiceConfig,
    SpeakerVoiceConfig,
    PrebuiltVoiceConfig,
)

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


#####-----------------------------------------------------######


async def generate_speech_ai(script: str):
    """
    Generates speech from text using Gemini AI, saves it to a temporary file.
    Returns (file_path, final_mime_type) or (None, error_message).
    Assumes genai is configured (e.g., genai.configure(api_key=...)).
    """
    contents = [{"role": "user", "parts": [{"text": script}]}]

    try:
        # Instantiate the GenerativeModel for TTS
        # The `config` (GenerateContentConfig) is passed to the generate_content method.
        model = "gemini-2.5-flash-preview-tts"
        config = GenerateContentConfig(
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
        )

        # This inner function will run in a separate thread to handle synchronous iteration
        async def get_audio_data_async():
            audio_data_buffer = b""
            captured_mime_type = None

            response_stream = await async_client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,  # Pass the full GenerateContentConfig here
            )

            async for chunk in response_stream:
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
        audio_buffer, output_mime_type = await get_audio_data_async()

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


@bot.add_cmd(cmd=["speak"])
@run_basic_check  # Ensures basic checks (like API key) pass
async def speak_command(bot: BOT, message: Message):
    script = message.input
    if not script:
        await message.reply_text(
            "<code>Please provide some text to speak after the command.</code>"
        )
        return

    loading_msg = await message.reply_text(
        "<code>...</code>", parse_mode=ParseMode.HTML
    )

    file_path, audio_mime_type = await generate_speech_ai(
        script=script,
    )

    if not file_path:  # Error occurred, audio_mime_type here is the error message
        await loading_msg.edit_text(
            f"<b>Error generating speech:</b>\n<code>{audio_mime_type}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        # Send the audio file
        # Pyrogram's reply_audio handles uploading.
        # It typically sends as voice if ogg, or audio document otherwise.
        # You can add title, performer, duration if you can get them.
        sent_message = await message.reply_audio(
            audio=file_path,
            parse_mode=ParseMode.HTML,
            title="Voice",  # Optional
            performer="leaflet",  # Optional
        )
        if sent_message:
            await loading_msg.delete()
        else:
            await loading_msg.edit_text("<code>Failed to send the audio file.</code>")

    except Exception as e:
        await loading_msg.edit_text(
            f"<b>Error sending audio:</b>\n<code>{e}</code>", parse_mode=ParseMode.HTML
        )
    finally:
        # Clean up the temporary file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e_rem:
                print(
                    f"Error deleting temp audio file {file_path}: {e_rem}"
                )  # Log this error
