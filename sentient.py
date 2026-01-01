import os
from app import BOT, Message, bot
from .aicore import MODEL, ask_ai
import ub_core


CONTEXT_FILE = "codebase_context.txt"
IGNORED_DIRS = {
    ".git", "__pycache__", "venv", "env", "node_modules", 
    "downloads", "logs", ".gemini", "cache"
}
ALLOWED_EXTS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", 
    ".sh", ".toml", ".ini", ".dockerfile"
}


def get_codebase_content():
    root_dir = os.getcwd()
    content = ["Analysis of the entire codebase directory structure and file contents:\n"]
    
    # Identify directories to traverse: Root and ub_core
    dirs_to_walk = [root_dir]
    
    if hasattr(ub_core, "__path__"):
        for p in ub_core.__path__:
             dirs_to_walk.append(p)
    elif hasattr(ub_core, "__file__"):
        dirs_to_walk.append(os.path.dirname(ub_core.__file__))

    processed_files = set()

    for start_dir in dirs_to_walk:
        for root, dirs, files in os.walk(start_dir):
            # Filter directories
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in ALLOWED_EXTS or file == "Dockerfile" or file == "Makefile":
                    file_path = os.path.join(root, file)
                    
                    # Avoid duplicates if ub_core is inside root
                    if file_path in processed_files:
                        continue
                    processed_files.add(file_path)

                    rel_path = os.path.relpath(file_path, root_dir) # Keep path relative to CWD for clarity
                    
                    # Skip the context file itself
                    if rel_path == CONTEXT_FILE:
                        continue
                        
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            file_content = f.read()
                            content.append(f"\n{'='*20}\nFile: {rel_path}\n{'='*20}\n{file_content}\n")
                    except Exception:
                        pass
                        
    return "".join(content)

@bot.add_cmd(cmd="ubx")
async def index_codebase(bot: BOT, message: Message):
    status = await message.reply("Indexing codebase...")
    try:
        content = get_codebase_content()
        with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        await status.edit(f"Codebase indexed successfully.\nSize: {len(content)} characters.")
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
        with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
            codebase_context = f.read()
            
        prompt = message.input
        # Leverage Gemini's large context window
        response = await ask_ai(
            prompt=prompt, 
            query=codebase_context, 
            quote=True,
            **MODEL["DEFAULT"] # Use default configuration but inject context
        )
        
        await status.edit(response, disable_preview=True)
        
    except Exception as e:
        await status.edit(f"Error: {e}")


@bot.add_cmd(cmd="create")
async def create_plugin(bot: BOT, message: Message):
    input_text = message.input
    reply_text = message.replied.text if message.replied else ""
    
    request_content = f"{input_text}\n{reply_text}".strip()
    
    if not request_content:
        await message.reply("Give me an idea for a plugin.")
        return

    if not os.path.exists(CONTEXT_FILE):
        await message.reply("Codebase index not found. Run `ubx` first.")
        return

    status = await message.reply("Cooking...")
    
    try:
        with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
            codebase_context = f.read()

        system_prompt = (
            "You are an expert Python developer for this specific Telegram bot codebase.\n"
            "Create a COMPLETE, working Python plugin based on the user's request.\n"
            "Follow these strict rules:\n"
            "1. Use 'app' and 'ub_core' imports as seen in the codebase context.\n"
            "2. Use the '@bot.add_cmd' decorator for commands.\n"
            "3. STRICTLY output the code inside a single ```python ... ``` block.\n"
            "4. Do NOT include any text, explanations, or markdown outside the code block.\n"
            "5. Keep comments minimal but useful.\n"
            "\nUser Request:\n"
        )
        
        full_prompt = f"{system_prompt}{request_content}"

        response = await ask_ai(
            prompt=full_prompt, 
            query=codebase_context,
            **MODEL["THINK"]
        )
        
        # Robust extraction
        import re
        match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
        if match:
            clean_code = match.group(1).strip()
        else:
             # Fallback: check for generic block or just assume content is code if prompt was strict
            match_generic = re.search(r"```(.*?)```", response, re.DOTALL)
            if match_generic:
                clean_code = match_generic.group(1).strip()
            else:
                clean_code = response.strip()

        if len(clean_code) > 2096:
            # Send as file - RAW CODE
            import io
            f = io.BytesIO(clean_code.encode("utf-8"))
            f.name = "plugin.py"
            await message.reply_document(document=f, caption="Here is your cooked plugin.")
            await status.delete()
        else:
            # Send as text - FORMATED BLOCK
            # Check if it already has blocks (in case we fell back to full response that had them but regex failed mysteriously, or avoiding double wrapping)
            if "```python" not in clean_code:
                 out_text = f"```python\n{clean_code}\n```"
            else:
                 out_text = clean_code
                 
            await status.edit(out_text, disable_preview=True)
            
    except Exception as e:
        await status.edit(f"Error generating plugin: {e}")
