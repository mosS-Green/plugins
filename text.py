from app import BOT, Message, bot
from openai import AsyncOpenAI, APITimeoutError
from pyrogram.enums import ParseMode
from pyrogram.types import InputMediaPhoto
from ub_core.utils import aio
import base64
import re
import io
import asyncio

# --- Configuration ---
ELECTRON_API_KEY = "ek-jSL9SVU403NW4hEN3BCeiZwpnrxbYk0sFT1dcosdiyykp6bHxW"
ELECTRON_BASE_URL = "https://api.electronhub.ai/v1/"
MODEL_IMAGE = "gemini-2.5-flash-image"
MODEL_TEXT = "gpt-5-mini:free"

# System instruction to guide the text model's behavior
SYSTEM_PROMPT = "You are a helpful assistant. Keep your answers concise and to the point unless the user specifically asks for a detailed or long-form response."

# --- Reusable API Client ---
client = AsyncOpenAI(
    api_key=ELECTRON_API_KEY,
    base_url=ELECTRON_BASE_URL,
    timeout=60.0
)

# --- Helper Functions ---
def parse_ai_output(choice):
    """Parses content, specifically looking for img tags from ElectronHub/Gemini models."""
    content = getattr(choice.message, "content", "")
    if not content:
        return "", None
    
    img_match = re.search(r'<img[^>]+src="([^"]+)"', content)
    image_url = img_match.group(1) if img_match else None
    
    text_only = re.sub(r"<[^>]+>", "", content).strip()
    return text_only, image_url

async def generate(prompt: str, image_file: io.BytesIO = None, model: str = MODEL_IMAGE, system_prompt: str = None):
    """Unified generation function using Chat Completions API."""
    messages = []
    
    # Add system prompt if provided
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
        
    # Construct User Content (text and optional image)
    user_content = [{"type": "text", "text": prompt}]
    if image_file:
        image_file.seek(0)
        image_bytes = image_file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
        })
    messages.append({"role": "user", "content": user_content})

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
        )
        
        if resp.choices:
            text, img_url = parse_ai_output(resp.choices[0])
            return text, img_url, None
        else:
            return None, None, "AI returned an empty response."

    except APITimeoutError:
        return None, None, "The request to the AI timed out."
    except Exception as e:
        return None, None, f"API Error: {str(e)}"

# --- Telegram Bot Commands ---

@bot.add_cmd(cmd="i")
async def electron_gemini(bot: BOT, message: Message):
    """Image generation/analysis command."""
    prompt = message.input
    if not prompt:
        await message.reply("Please provide a prompt.")
        return
        
    wait_message = await message.reply("Generating...")
    
    image_file = None
    if message.reply_to_message and message.reply_to_message.photo:
        image_file = await message.reply_to_message.download(in_memory=True)
        
    text, image_url, error = await generate(prompt, image_file, model=MODEL_IMAGE)
    
    if error:
        await wait_message.edit(f"**Error:**\n`{error}`")
        return

    if image_url:
        try:
            await wait_message.edit_media(
                media=InputMediaPhoto(
                    media=image_url,
                    caption=f"**Response:**\n{text}"[:1024], # Caption has a 1024 char limit
                    parse_mode=ParseMode.MARKDOWN,
                )
            )
        except Exception as e:
            await wait_message.edit(f"**Generated Image** (Upload failed: `{e}`)\n\n{text}")
    elif text:
        formatted_resp = f"**Prompt:** `{prompt}`\n\n**Response:** {text}"
        await wait_message.edit(formatted_resp, parse_mode=ParseMode.MARKDOWN)
    else:
        await wait_message.edit("The AI returned an empty response.")


@bot.add_cmd(cmd="g")
async def gpt5_text(bot: BOT, message: Message):
    """Text generation command with context support and conciseness instruction."""
    prompt_input = message.input
    reply = message.reply_to_message
    
    context_text = ""
    if reply and (reply.text or reply.caption):
        context_text = reply.text or reply.caption

    if not prompt_input and not context_text:
        await message.reply("Please provide a prompt or reply to a text message.")
        return

    # Construct the final prompt for the AI
    if context_text and prompt_input:
        final_prompt = f"Based on the following context:\n\"\"\"\n{context_text}\n\"\"\"\n\nPerform this instruction: {prompt_input}"
    else:
        final_prompt = prompt_input or context_text

    wait_message = await message.reply("Thinking...")
    
    image_file = None
    if reply and reply.photo:
        image_file = await reply.download(in_memory=True)

    try:
        text, _, error = await asyncio.wait_for(
            generate(final_prompt, image_file, model=MODEL_TEXT, system_prompt=SYSTEM_PROMPT),
            timeout=45.0
        )
    except asyncio.TimeoutError:
        await wait_message.edit("The request took too long. Please try again.")
        return

    if error:
        await wait_message.edit(f"**Error:**\n`{error}`")
        return

    # Format the response to be sent back to Telegram
    display_prompt = prompt_input if prompt_input else "Replied Message"
    formatted_resp = f"**Prompt:** `{display_prompt}`\n\n{text}"
    
    await wait_message.edit(formatted_resp, parse_mode=ParseMode.MARKDOWN)
