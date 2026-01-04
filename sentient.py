import asyncio
import glob
import io
import os
import re
from pathlib import Path

import aiofiles
from app import BOT, Message, bot
from .ai_sandbox.prompts import DEV_PROMPTS
from .ai_sandbox.core import ask_ai, MODEL
from app.plugins.ai.gemini.utils import run_basic_check
import ub_core
from ub_core.utils import run_shell_cmd
from app.plugins.ai.gemini import AIConfig

CONTEXT_FILE = "codebase_context.txt"
MAX_CONCURRENT_READS = 50


async def read_file_async(
    path: Path, root_dir: Path, semaphore: asyncio.Semaphore
) -> str:
    """
    Reads a single file asynchronously with a semaphore.
    """
    async with semaphore:
        try:
            try:
                rel_path = path.relative_to(root_dir)
            except ValueError:
                rel_path = path

            # Skip the context file itself
            if str(rel_path) == CONTEXT_FILE:
                return ""

            async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = await f.read()
                return f"\n{'='*20}\nFile: {rel_path}\n{'='*20}\n{content}\n"
        except Exception:
            return ""


async def build_codebase_index():
    """
    Asynchronously builds the codebase index using glob.
    Scans ub_core and app/ recursively.
    """
    root_dir = os.getcwd()
    scan_dirs = ["app/", "ub_core/"]

    if hasattr(ub_core, "ub_core_dirname"):
        ub_core_path = ub_core.ub_core_dirname
        if os.path.exists(ub_core_path):
            scan_dirs = ["app/", ub_core_path]

    all_files = []

    for directory in scan_dirs:
        dir_path = (
            directory if os.path.isabs(directory) else os.path.join(root_dir, directory)
        )
        files = glob.glob(f"{dir_path}/**/*.py", recursive=True)
        all_files.extend(files)

    final_files = sorted([Path(f) for f in all_files], key=lambda p: str(p).lower())
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_READS)
    tasks = [read_file_async(file, Path(root_dir), semaphore) for file in final_files]
    results = await asyncio.gather(*tasks)

    header = "Analysis of the entire codebase directory structure and file contents:\n"
    return header + "".join(results)


async def read_context_file():
    """Reads the context file asynchronously."""
    async with aiofiles.open(CONTEXT_FILE, "r", encoding="utf-8") as f:
        return await f.read()


async def ensure_index():
    """Builds codebase index if it doesn't exist."""
    if not os.path.exists(CONTEXT_FILE):
        content = await build_codebase_index()
        async with aiofiles.open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            await f.write(content)


@bot.add_cmd(cmd="ubx")
async def index_codebase(bot: BOT, message: Message):
    """Builds and saves the codebase index file."""
    status = await message.reply("Indexing codebase...")
    try:
        content = await build_codebase_index()

        async with aiofiles.open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            await f.write(content)

        caption = f"Codebase indexed successfully.\nSize: {len(content)} characters."

        if message.input and "-u" in message.input:
            await message.reply_document(document=CONTEXT_FILE, caption=caption)
            await status.delete()
        else:
            await status.edit(caption)

    except Exception as e:
        await status.edit(f"Indexing failed: {e}")


@bot.add_cmd(cmd="ub")
async def query_codebase(bot: BOT, message: Message):
    """Queries the AI about the indexed codebase."""
    if not message.input:
        await message.reply("Ask a question about the codebase.")
        return

    await ensure_index()
    status = await message.reply("Thinking...")
    codebase_context = await read_context_file()
    kwargs = AIConfig.get_kwargs(flags=message.flags)
    response = await ask_ai(
        prompt=message.input, query=codebase_context, quote=True, **kwargs
    )
    await status.edit(response, disable_preview=True)


@bot.add_cmd(cmd="dbg")
async def debug_logs(bot: BOT, message: Message):
    """Analyzes recent logs with AI assistance."""
    text = await run_shell_cmd(cmd="tail -n 50 logs/app_logs.txt")
    status = await message.reply("Reading...")
    await ensure_index()

    try:
        context = await read_context_file()
        text += f"\n\n=== Codebase Context ===\n{context}"
    except Exception:
        pass

    extra_input = f"\n\nUser Input: {message.input}" if message.input else ""
    prompt = f"{DEV_PROMPTS['DEBUG']}{extra_input}"
    kwargs = AIConfig.get_kwargs(flags=message.flags)
    ai_response = await ask_ai(prompt=prompt, query=text, quote=True, **kwargs)
    await message.reply(ai_response)


@bot.add_cmd(cmd="cook")
async def cook_plugin(bot: BOT, message: Message):
    """
    Generates code based on the codebase context.
    """
    input_text = message.input
    reply_text = message.replied.text if message.replied else ""
    request_content = f"{input_text}\n{reply_text}".strip()

    if not request_content:
        await message.reply("Give me an idea to cook.")
        return

    await ensure_index()
    status = await message.reply("Cooking...")

    try:
        codebase_context = await read_context_file()

        if "-py" in message.flags:
            system_prompt = DEV_PROMPTS["PY_EXEC"]
        else:
            system_prompt = DEV_PROMPTS["COOK"]

        full_prompt = f"{system_prompt}{request_content}"

        response = await ask_ai(
            prompt=full_prompt, query=codebase_context, **MODEL["THINK"]
        )

        match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
        if match:
            clean_code = match.group(1).strip()
        else:
            match_generic = re.search(r"```(.*?)```", response, re.DOTALL)
            clean_code = (
                match_generic.group(1).strip() if match_generic else response.strip()
            )

        if len(clean_code) > 4000:
            f = io.BytesIO(clean_code.encode("utf-8"))
            f.name = "plugin.py"
            await message.reply_document(
                document=f, caption="Here is your cooked plugin."
            )
            await status.delete()
        else:
            out_text = (
                f"```python\n{clean_code}\n```"
                if "```python" not in clean_code
                else clean_code
            )
            await status.edit(out_text, disable_preview=True)

    except Exception as e:
        await status.edit(f"Error cooking plugin: {e}")
