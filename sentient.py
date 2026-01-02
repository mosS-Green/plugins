import asyncio
import os
import re
import io
from functools import partial

from app import BOT, Message, bot
from .aicore import MODEL, ask_ai
import ub_core

CONTEXT_FILE = "codebase_context.txt"

IGNORED_DIRS = {
    ".git", "__pycache__", "venv", "env", "node_modules", 
    "downloads", "logs", ".gemini", "cache", ".idea", ".vscode"
}

ALLOWED_EXTS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", 
    ".sh", ".toml", ".ini", ".dockerfile", ".css", ".html", ".js"
}

from pathlib import Path

def _get_codebase_content_sync():
    """
    Synchronous function to walk the codebase and build the context string.
    Designed to be run in an executor to avoid blocking the main loop.
    """
    root_dir = Path(os.getcwd())
    content = ["Analysis of the entire codebase directory structure and file contents:\n"]
    
    # Identify directories to traverse
    dirs_to_walk = [root_dir]
    
    # robustly add ub_core path
    if hasattr(ub_core, "__path__"):
        dirs_to_walk.extend([Path(p) for p in ub_core.__path__])
    elif hasattr(ub_core, "__file__"):
        dirs_to_walk.append(Path(ub_core.__file__).parent)

    processed_files = set()
    
    def recursive_walk(directory):
        if directory.name in IGNORED_DIRS:
            return
            
        try:
            # Sort for deterministic output
            for path in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
                if path.is_dir():
                    if path.name not in IGNORED_DIRS:
                         recursive_walk(path)
                elif path.is_file():
                    if path.suffix in ALLOWED_EXTS or path.name in ("Dockerfile", "Makefile"):
                        if path in processed_files:
                            continue
                        processed_files.add(path)

                        try:
                            rel_path = path.relative_to(root_dir)
                        except ValueError:
                            rel_path = path
                        
                        if str(rel_path) == CONTEXT_FILE:
                            continue
                            
                        try:
                            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                file_content = f.read()
                                content.append(f"\n{'='*20}\nFile: {rel_path}\n{'='*20}\n{file_content}\n")
                        except Exception:
                            continue
        except PermissionError:
            pass

    for start_dir in dirs_to_walk:
        if start_dir.exists():
             recursive_walk(start_dir)
                        
    return "".join(content)

async def build_codebase_index():
    """
    Async wrapper to run the synchronous file walking in a separate thread.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_codebase_content_sync)

async def read_context_file():
    """
    Reads the codebase context file in a non-blocking way.
    """
    loop = asyncio.get_running_loop()
    def _read():
        with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return await loop.run_in_executor(None, _read)

@bot.add_cmd(cmd="ubx")
async def index_codebase(bot: BOT, message: Message):
    status = await message.reply("Indexing codebase...")
    try:
        # Optimization: Non-blocking file operation
        content = await build_codebase_index()
        
        # Write mostly non-blocking (small enough) or use executor if very large
        loop = asyncio.get_running_loop()
        def _write():
            with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
                f.write(content)
        await loop.run_in_executor(None, _write)
        
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
    
    try:
        # Non-blocking read
        codebase_context = await read_context_file()
            
        prompt = message.input
        response = await ask_ai(
            prompt=prompt, 
            query=codebase_context, 
            quote=True,
            **MODEL["DEFAULT"]
        )
        
        await status.edit(response, disable_preview=True)
        
    except Exception as e:
        await status.edit(f"Error: {e}")

@bot.add_cmd(cmd="cook")
async def cook_plugin(bot: BOT, message: Message):
    """
    Generates code based on the codebase context (formerly 'create').
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
        # Non-blocking read
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
        
        # Robust extraction logic
        match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
        if match:
            clean_code = match.group(1).strip()
        else:
            match_generic = re.search(r"```(.*?)```", response, re.DOTALL)
            clean_code = match_generic.group(1).strip() if match_generic else response.strip()

        if len(clean_code) > 4000: # Telegram message limit is 4096
            f = io.BytesIO(clean_code.encode("utf-8"))
            f.name = "plugin.py"
            await message.reply_document(document=f, caption="Here is your cooked plugin.")
            await status.delete()
        else:
            out_text = f"```python\n{clean_code}\n```" if "```python" not in clean_code else clean_code
            await status.edit(out_text, disable_preview=True)
            
    except Exception as e:
        await status.edit(f"Error cooking plugin: {e}")
