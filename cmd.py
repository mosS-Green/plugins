import os

from app import BOT, Config, Message, bot
from pyrogram.enums import ParseMode
from ub_core.utils import run_shell_cmd, wrap_in_block_quote
from app.plugins.ai.gemini.query import question


async def init_task(bot=bot, message=None):
    Config.CMD_DICT["eu"] = Config.CMD_DICT["extupdate"]
    Config.CMD_DICT["ry"] = Config.CMD_DICT["reply"]


@BOT.add_cmd(cmd="ch")
async def plugin_info(bot: BOT, message: Message):
    """Shows the source file for a given command."""
    cmd = message.filtered_input
    cmd_obj = Config.CMD_DICT.get(cmd)

    if not cmd_obj:
        await message.reply("cmd not found", del_in=8)
        return

    plugin_path = os.path.relpath(cmd_obj.cmd_path, os.path.curdir)
    plugin = os.path.basename(plugin_path)
    repo = os.environ.get("EXTRA_MODULES_REPO")
    branch = "main"

    to_join = [str(item).strip("/") for item in (repo, "blob", branch, plugin)]
    remote_url = os.path.join(*to_join)
    resp_str = wrap_in_block_quote(
        f"**{cmd}** : <a href='{remote_url}'>{plugin}</a>", "**>", "<**"
    )

    response = await message.reply(resp_str, disable_preview=True)


@bot.add_cmd("ey")
async def mention_others(bot, message):
    """Mentions all non-bot users in a group chat."""
    sender_username = message.from_user.username
    chat_id = message.chat.id

    non_bot_mentions = []
    try:
        async for member in bot.get_chat_members(chat_id):
            if (
                member.user
                and member.user.username
                and member.user.id
                and not member.user.is_bot
                and member.user.username != sender_username
            ):
                mention = f'<a href="tg://user?id={member.user.id}">\u200b</a>'
                non_bot_mentions.append(mention)
    except Exception as e:
        await message.reply(f"Error getting chat members: {e}")
        return

    dot_character = "​​"

    initial_output = "​"

    if hasattr(message, "input") and message.input:
        initial_output += f"<b>{message.input}</b>{dot_character}"
    else:
        initial_output += f"<b>@ everyone</b>{dot_character}"

    if non_bot_mentions:
        tagged_dots = [f"{dot_character}{mention}" for mention in non_bot_mentions]

        for i in range(0, len(tagged_dots), 50):
            chunk = tagged_dots[i : i + 50]
            current_output = initial_output + "​".join(chunk)
            await message.reply(text=current_output, parse_mode=ParseMode.HTML)

    else:
        message_to_send = (
            initial_output + " No other users to mention or unable to retrieve members."
        )
        await message.reply(text=message_to_send, parse_mode=ParseMode.HTML)


@BOT.add_cmd(cmd="log")
async def log_ai_analysis(bot: BOT, message: Message):
    """
    CMD: LOG
    INFO: Analysis logs using Gemini AI.
    USAGE: .log
    """
    # Fetch last 100 lines of logs
    logs = await run_shell_cmd(cmd="tail -n 100 logs/app_logs.txt")

    # Construct the prompt for the AI
    prompt = (
        "Analyze the provided log entries. "
        "List the latest errors, exceptions, or tracebacks found. "
        "Be concise and summarize the root cause of the most recent issue.\n\n"
        f"{logs}"
    )

    class LogContext:
        text = prompt
        is_thread_origin = False
        media = None

    # Modify the message object to inject the logs as input
    # forcing the question function to use our constructed prompt
    message.__dict__["input"] = ":"
    message.__dict__["filtered_input"] = ":"
    message.__dict__["flags"] = []

    # Detach reply context so AI focuses only on logs
    message.__dict__["_replied"] = LogContext()

    # Delegate to the existing AI question function
    await question(bot, message)


@bot.add_cmd(cmd="ubx")
async def index_codebase(bot: BOT, message: Message):
    """
    CMD: UBX
    INFO: Build and save the codebase index file.
    FLAGS: -u to upload the index file to chat
    USAGE: ,ubx | ,ubx -u
    """
    import asyncio
    import glob
    from pathlib import Path

    import aiofiles

    CONTEXT_FILE = "codebase_context.txt"
    MAX_CONCURRENT_READS = 50

    async def read_file_async(path: Path, root_dir: Path, semaphore: asyncio.Semaphore) -> str:
        async with semaphore:
            try:
                rel_path = path.relative_to(root_dir) if path.is_relative_to(root_dir) else path
                if str(rel_path) == CONTEXT_FILE:
                    return ""
                async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = await f.read()
                    return f"\n{'='*20}\nFile: {rel_path}\n{'='*20}\n{content}\n"
            except Exception:
                return ""

    status = await message.reply("<code>Indexing codebase...</code>")
    try:
        root_dir = os.getcwd()
        scan_dirs = ["app/"]

        try:
            import ub_core
            if hasattr(ub_core, "ub_core_dirname"):
                ub_core_path = ub_core.ub_core_dirname
                if os.path.exists(ub_core_path):
                    scan_dirs.append(ub_core_path)
                else:
                    scan_dirs.append("ub_core/")
            else:
                scan_dirs.append("ub_core/")
        except ImportError:
            scan_dirs.append("ub_core/")

        all_files = []
        for directory in scan_dirs:
            dir_path = directory if os.path.isabs(directory) else os.path.join(root_dir, directory)
            all_files.extend(glob.glob(f"{dir_path}/**/*.py", recursive=True))

        final_files = sorted([Path(f) for f in all_files], key=lambda p: str(p).lower())
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_READS)
        tasks = [read_file_async(file, Path(root_dir), semaphore) for file in final_files]
        results = await asyncio.gather(*tasks)

        content = "Analysis of the entire codebase directory structure and file contents:\n" + "".join(results)

        async with aiofiles.open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            await f.write(content)

        caption = f"Codebase indexed.\nSize: {len(content)} characters."

        if "-u" in message.flags:
            await message.reply_document(document=CONTEXT_FILE, caption=caption)
            await status.delete()
        else:
            await status.edit(caption)

    except Exception as e:
        await status.edit(f"Indexing failed: {e}")

