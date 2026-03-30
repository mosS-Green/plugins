import os
import shlex

from pyrogram.types import ReplyParameters
from ub_core.utils import get_tg_media_details, run_shell_cmd

from app import BOT, LOGGER, Message, bot

from .config import (
    CLI_TIMEOUT,
    GEMINI_API_KEY,
    GEN_MODEL,
    GEN_TEMP_DIR,
    PROJECT_ROOT,
    REVIEW_TIMEOUT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _git_diff() -> str:
    """Return the current unstaged diff in the project."""
    return (await run_shell_cmd(cmd="git diff", timeout=10)).strip()


async def _git_revert():
    """Revert all unstaged changes."""
    await run_shell_cmd(cmd="git checkout -- .", timeout=10)


async def _download_replied_file(reply: Message) -> str | None:
    """Download replied media to the gen temp dir.  Returns the local path."""
    try:
        media = get_tg_media_details(reply)
        file_name = getattr(media, "file_name", None) or "file"
        save_path = os.path.join(GEN_TEMP_DIR, file_name)
        await reply.download(file_name=save_path)
        return save_path
    except Exception as e:
        LOGGER.error(f"gen download error: {e}")
        return None


async def _run_gemini_cli(prompt: str, model: str, sandbox: bool = False) -> str:
    """Run gemini CLI as a subprocess and return its output."""
    # Build command — use --prompt for non-interactive (headless) mode
    # and --approval-mode auto_edit to auto-approve file edits
    parts = ["gemini", "--prompt", prompt]
    if model:
        parts.extend(["-m", model])
    if sandbox:
        parts.append("-s")
    parts.extend(["--approval-mode", "auto_edit"])

    cmd = " ".join(shlex.quote(p) for p in parts)

    # Pass GEMINI_API_KEY via env. run_shell_cmd uses asyncio subprocess,
    # which inherits env. We set it in os.environ temporarily.
    old_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

    try:
        output = await run_shell_cmd(cmd=cmd, timeout=CLI_TIMEOUT)
    finally:
        # Restore
        if old_key is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = old_key

    return output.strip() if output else ""


# ---------------------------------------------------------------------------
# Review flow: show diff, wait for approval, revert if rejected
# ---------------------------------------------------------------------------


async def _review_changes(
    chat_id: int,
    message: Message,
    cli_output: str,
    diff_text: str,
) -> None:
    """Send the CLI response + diff for review.  Revert on rejection."""
    # Send AI response
    if cli_output:
        response_text = cli_output[:4000]
        await bot.send_message(
            chat_id=chat_id,
            text=response_text,
            reply_parameters=ReplyParameters(message_id=message.id),
        )

    # Send diff for review
    diff_display = diff_text[:3800]
    review_msg_text = (
        f"<b>Changes made:</b>\n"
        f"<pre language=diff>{diff_display}</pre>\n\n"
        f"Reply <code>ok</code> to keep.  Anything else reverts."
    )

    async with bot.Convo(
        chat_id=chat_id,
        client=bot.client,
        from_user=message.from_user.id,
        timeout=REVIEW_TIMEOUT,
    ) as convo:
        await convo.send_message(text=review_msg_text, reply_to_id=message.id)

        try:
            user_reply: Message = await convo.get_response()
        except TimeoutError:
            await _git_revert()
            await bot.send_message(
                chat_id=chat_id,
                text="<i>timed out — changes reverted.</i>",
                reply_parameters=ReplyParameters(message_id=message.id),
            )
            return

        reply_text = (user_reply.text or "").strip().lower()
        if reply_text == "ok":
            await convo.send_message(
                text="<i>changes kept.</i>",
                reply_to_id=user_reply.id,
            )
        else:
            await _git_revert()
            await convo.send_message(
                text="<i>reverted.</i>",
                reply_to_id=user_reply.id,
            )


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


@bot.add_cmd(cmd="gen")
async def gen_cmd(bot: BOT, message: Message):
    """
    CMD: GEN
    INFO: AI coding agent powered by Gemini CLI. Reads, writes, and edits files autonomously.
    FLAGS:
        -c  clear gen temp files
        -s  run in sandbox mode
        -m  specify model (default: gemini-2.5-flash)
        -upload <path>  upload a project file to chat
    USAGE: .gen <prompt>
    """
    flags = message.flags

    # --- Flag: clear temp ---
    if "-c" in flags:
        cleared = 0
        for f in os.listdir(GEN_TEMP_DIR):
            fp = os.path.join(GEN_TEMP_DIR, f)
            if os.path.isfile(fp):
                os.remove(fp)
                cleared += 1
        await message.reply(f"cleared {cleared} temp file(s).")
        return

    # --- Flag: upload file ---
    if "-upload" in flags:
        filepath = message.filtered_input.strip()
        full_path = os.path.join(PROJECT_ROOT, filepath)
        if not os.path.isfile(full_path):
            await message.reply(f"file not found: <code>{filepath}</code>", del_in=8)
            return
        try:
            await bot.send_document(
                chat_id=message.chat.id,
                document=full_path,
                caption=f"<code>{os.path.basename(full_path)}</code>",
                reply_parameters=ReplyParameters(message_id=message.id),
            )
        except Exception as e:
            await message.reply(f"upload error: {e}")
        return

    # --- Build prompt ---
    user_input = message.filtered_input
    reply = message.replied

    if not user_input and not reply:
        await message.reply(
            "provide a prompt or reply to a file.\n"
            "usage: <code>.gen &lt;prompt&gt;</code>",
            del_in=8,
        )
        return

    # Determine model
    model = flags.get("-m", GEN_MODEL) if isinstance(flags, dict) else GEN_MODEL
    if not isinstance(model, str):
        model = GEN_MODEL

    sandbox = "-s" in flags

    status_msg = await message.reply(f"<code>gen ({model})...</code>")

    # --- Handle replied file ---
    prompt = user_input or ""
    if reply and reply.media:
        await status_msg.edit("<code>downloading file...</code>")
        local_path = await _download_replied_file(reply)
        if local_path:
            # Use @path syntax so gemini-cli can read it
            prompt = f"@{local_path} {prompt}" if prompt else f"Analyze @{local_path}"
        else:
            await status_msg.edit("<code>file download failed.</code>")
            return
    elif reply and reply.text:
        prompt = f"Context from replied message:\n{reply.text}\n\n{prompt}"

    if not prompt.strip():
        await status_msg.edit("<code>empty prompt.</code>")
        return

    # --- Snapshot git state ---
    diff_before = await _git_diff()

    # --- Run gemini-cli ---
    await status_msg.edit(f"<code>running gemini-cli ({model})...</code>")
    try:
        cli_output = await _run_gemini_cli(
            prompt=prompt,
            model=model,
            sandbox=sandbox,
        )
    except Exception as e:
        LOGGER.error(f"gen cli error: {e}")
        await status_msg.edit(f"<code>error: {e}</code>")
        return

    # --- Check for file changes ---
    diff_after = await _git_diff()

    # Compute only the NEW changes (subtract pre-existing diff)
    new_changes = diff_after != diff_before and bool(diff_after)

    if new_changes:
        # Delete status, show response + review flow
        await status_msg.delete()
        await _review_changes(
            chat_id=message.chat.id,
            message=message,
            cli_output=cli_output,
            diff_text=diff_after,
        )
    else:
        # No file changes — just show the response
        if cli_output:
            await status_msg.edit(cli_output[:4096])
        else:
            await status_msg.edit("<code>no output.</code>")
