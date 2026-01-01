import os
from app import BOT, Message, bot
from .aicore import MODEL, ask_ai

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
    
    for root, dirs, files in os.walk(root_dir):
        # Filter directories
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTS or file == "Dockerfile" or file == "Makefile":
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, root_dir)
                
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
            model="1.5-pro", # Defaulting to Pro for large context if available, otherwise fallback will handle it
            **MODEL["DEFAULT"] # Use default configuration but inject context
        )
        
        await status.edit(response, disable_preview=True)
        
    except Exception as e:
        await status.edit(f"Error: {e}")
