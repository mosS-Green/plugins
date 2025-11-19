import os
import uuid
import struct
import io
from mimetypes import guess_type

from app import BOT, Message, bot
from pyrogram.enums import ParseMode
from .aicore import async_client, run_basic_check

from google.genai.types import (
    GenerateContentConfig,
    SpeechConfig,
    VoiceConfig,
    PrebuiltVoiceConfig,
)

# --- Constants ---
TEMP_DIR = "temp_audio_files/"
os.makedirs(TEMP_DIR, exist_ok=True)

# --- Audio Helper Functions ---
def parse_audio_mime_type(mime_type: str) -> dict:
    """Parses bits per sample and rate from an audio MIME type string."""
    bits_per_sample = 16
    rate = 24000
    
    parts = mime_type.split(";")
    for param in parts:
        param = param.strip().lower()
        if param.startswith("rate="):
            try:
                rate = int(param.split("=", 1)[1])
            except (ValueError, IndexError):
                pass
        elif param.startswith("audio/l"):
            try:
                # Extract bits from "audio/L16", "audio/L8"
                bps_str = param.split("l", 1)[1]
                if bps_str.isdigit():
                    bits_per_sample = int(bps_str)
            except (ValueError, IndexError):
                pass
    return {"bits_per_sample": bits_per_sample, "rate": rate}

def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """Generates a WAV file header and prepends it to raw audio data."""
    params = parse_audio_mime_type(mime_type)
    bits_per_sample = params["bits_per_sample"]
    sample_rate = params["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", chunk_size, b"WAVE", b"fmt ", 16, 1, num_channels,
        sample_rate, byte_rate, block_align, bits_per_sample, b"data", data_size
    )
    return header + audio_data

async def generate_speech_ai(script: str):
    """
    Generates speech from text using Gemini AI.
    """
    # Single voice configuration (Aoede)
    config = GenerateContentConfig(
        response_modalities=["audio"],
        speech_config=SpeechConfig(
            voice_config=VoiceConfig(
                prebuilt_voice_config=PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
    )

    contents = [{"role": "user", "parts": [{"text": script}]}]
    
    audio_buffer = b""
    captured_mime = None

    try:
        response_stream = await async_client.models.generate_content_stream(
            model="gemini-2.5-flash-preview-tts",
            contents=contents,
            config=config,
        )

        async for chunk in response_stream:
            if not chunk.candidates or not chunk.candidates[0].content.parts:
                continue
            
            part = chunk.candidates[0].content.parts[0]
            if part.inline_data and part.inline_data.data:
                audio_buffer += part.inline_data.data
                if not captured_mime:
                    captured_mime = part.inline_data.mime_type

        if not audio_buffer:
            return None, "No audio received."

        captured_mime = captured_mime or "audio/ogg"
        
        # Determine file extension
        ext = guess_type(captured_mime)[0]
        if ext:
            ext = "." + ext.split("/")[-1]
        
        final_data = audio_buffer
        final_mime = captured_mime

        # Convert raw PCM (or unknown types) to WAV for compatibility
        if not ext or ext == ".bin" or "audio/l" in captured_mime.lower():
            try:
                final_data = convert_to_wav(audio_buffer, captured_mime)
                ext = ".wav"
                final_mime = "audio/wav"
            except Exception:
                ext = ".ogg" # Fallback

        file_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}{ext}")
        
        with open(file_path, "wb") as f:
            f.write(final_data)

        return file_path, final_mime

    except Exception as e:
        return None, str(e)

@bot.add_cmd(cmd=["speak"])
@run_basic_check
async def speak_command(bot: BOT, message: Message):
    msg_input = message.input or ""
    reply = message.reply_to_message
    
    final_script = ""
    
    # Loading indicator
    status_msg = await message.reply_text("<code>...</code>", parse_mode=ParseMode.HTML)

    try:
        # Case 1: Reply to a text file
        if reply and reply.document:
            if reply.document.file_size > 50 * 1024: # 50KB limit check
                await status_msg.edit_text("File too large (max 50KB).")
                return

            # Download to memory
            file_bytes = await reply.download(in_memory=True)
            file_content = file_bytes.getvalue().decode("utf-8", errors="ignore").strip()
            
            if msg_input:
                # Instructions provided with command
                final_script = f"({msg_input}):\n{file_content}"
            else:
                # No instructions, just read file
                final_script = file_content
        
        # Case 2: Direct text input
        elif msg_input:
            final_script = msg_input
            
        else:
            await status_msg.edit_text("<code>Provide text or reply to a text file.</code>")
            return

        # Generate Audio
        file_path, result_mime = await generate_speech_ai(final_script)

        if not file_path:
            await status_msg.edit_text(f"<b>Error:</b>\n<code>{result_mime}</code>")
            return

        # Send Audio
        await message.reply_audio(
            audio=file_path,
            title="AI Voice",
            performer="Gemini",
            parse_mode=ParseMode.HTML
        )
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"<b>Error:</b>\n<code>{e}</code>")
        
    finally:
        # Cleanup
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
