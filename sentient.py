import asyncio
import os
import re
import io
from pathlib import Path
from functools import partial

import aiofiles
from app import BOT, Message, bot
from .aicore import MODEL, ask_ai, run_basic_check
import ub_core
from ub_core.utils import run_shell_cmd
from app.plugins.ai.gemini import AIConfig

CONTEXT_FILE = "codebase_context.txt"

IGNORED_DIRS = {
    ".git", "__pycache__", "venv", "env", "node_modules", 
    "downloads", "logs", ".gemini", "cache", ".idea", ".vscode"
}

ALLOWED_EXTS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", 
    ".sh", ".toml", ".ini", ".dockerfile", ".css", ".html", ".js"
}

# Semaphore to prevent "Too many open files" errors during massive parallel reads
MAX_CONCURRENT_READS = 50

async def read_file_async(path: Path, root_dir: Path, semaphore: asyncio.Semaphore) -> str:
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
    Asynchronously builds the codebase index using pathlib and asyncio.gather.
    """
    root_dir = Path(os.getcwd())
    
    # Resolve paths to scan
    search_dirs = [root_dir]
    
    # Handle ub_core path - simpler check as requested
    if hasattr(ub_core, "__path__"):
        search_dirs.extend([Path(p) for p in ub_core.__path__])
    elif hasattr(ub_core, "__file__"):
        search_dirs.append(Path(ub_core.__file__).parent)

    all_files = []
    processed_paths = set()
    
    for directory in search_dirs:
        if not directory.exists():
            continue
            
        # Use rglob for recursive globbing - efficient iterator
        # We manually filter IGNORED_DIRS since rglob doesn't support exclusion patterns natively during traversal
        for path in directory.rglob("*"):
            if path.is_file():
                # Check for ignored directories in path parts
                # This is efficient enough for typical project sizes
                if any(part in IGNORED_DIRS for part in path.parts):
                    continue
                
                if path.suffix in ALLOWED_EXTS or path.name in ("Dockerfile", "Makefile"):
                    if path in processed_paths:
                        continue
                    processed_paths.add(path)
                    all_files.append(path)

    # Sort files for deterministic output
    all_files.sort(key=lambda p: p.name.lower())

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_READS)
    
    # Create tasks for all files
    tasks = [read_file_async(file, root_dir, semaphore) for file in all_files]
    
    # Run all reads in parallel
    results = await asyncio.gather(*tasks)
    
    header = "Analysis of the entire codebase directory structure and file contents:\n"
    return header + "".join(results)

async def read_context_file():
    """Reads the context file asynchronously."""
    async with aiofiles.open(CONTEXT_FILE, "r", encoding="utf-8") as f:
        return await f.read()

@bot.add_cmd(cmd="ubx")
async def index_codebase(bot: BOT, message: Message):
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
    if not message.input:
        await message.reply("Ask a question about the codebase.")
        return

    if not os.path.exists(CONTEXT_FILE):
        await message.reply("Codebase index not found. Run `ubx` first.")
        return

    status = await message.reply("Thinking...")
    
    codebase_context = await read_context_file()
        
    kwargs = AIConfig.get_kwargs(flags=message.flags)

    prompt = message.input
    response = await ask_ai(
        prompt=prompt, 
        query=codebase_context, 
        quote=True,
        **kwargs
    )
        
    await status.edit(response, disable_preview=True)
        

@bot.add_cmd(cmd="dbg")
async def debug_logs(bot: BOT, message: Message):
    text = await run_shell_cmd(cmd=f"tail -n 50 logs/app_logs.txt")

    status = await message.reply("Reading...")
    
    if not os.path.exists(CONTEXT_FILE):
        await message.reply("Codebase index not found. Run `ubx` first.")
        return

    try:
        context = await read_context_file()
        text += f"\n\n=== Codebase Context ===\n{context}"
    except Exception:
        pass

    extra_input = f"\n\nUser Input: {message.input}" if message.input else ""
    prompt = f"Analyze these logs and very concisely tell me what the issue was. Say No issues if none detected. Use the provided codebase context to identify specific files/plugins involved. Ignore the sqlite3 errors.{extra_input}"
    
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

    if not os.path.exists(CONTEXT_FILE):
        await message.reply("Codebase index not found. Run `ubx` first.")
        return

    status = await message.reply("Cooking...")
    
    try:
        codebase_context = await read_context_file()

        system_prompt = (
            "You are an expert Python developer for this specific Telegram bot codebase.\n"
            "Analyze the provided codebase context to understand the project's structure, coding style, import patterns, and available utilities.\n"
            "Create a COMPLETE, working Python plugin based on the user's request, adhering strictly to the existing codebase conventions.\n\n"
            "Guidelines:\n"
            "1. **Imports**: Use `app` and `ub_core` imports correctly as seen in the codebase.\n"
            "2. **Decorators**: Use `@bot.add_cmd(cmd='command_name')` for registering commands.\n"
            "3. **Style**: Match the existing coding style (naming conventions, error handling, etc.).\n"
            "4. **Output Format**: STRICTLY output ONLY the code inside a single ```python ... ``` block. No conversational text.\n"
            "\nUser Request:\n"
        )
        
        full_prompt = f"{system_prompt}{request_content}"

        response = await ask_ai(
            prompt=full_prompt, 
            query=codebase_context,
            **MODEL["THINK"]
        )
        
        match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
        if match:
            clean_code = match.group(1).strip()
        else:
            match_generic = re.search(r"```(.*?)```", response, re.DOTALL)
            clean_code = match_generic.group(1).strip() if match_generic else response.strip()

        if len(clean_code) > 4000: 
            f = io.BytesIO(clean_code.encode("utf-8"))
            f.name = "plugin.py"
            await message.reply_document(document=f, caption="Here is your cooked plugin.")
            await status.delete()
        else:
            out_text = f"```python\n{clean_code}\n```" if "```python" not in clean_code else clean_code
            await status.edit(out_text, disable_preview=True)
            
    except Exception as e:
        await status.edit(f"Error cooking plugin: {e}")
