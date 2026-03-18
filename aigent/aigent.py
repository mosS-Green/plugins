import json
import os
import re

from app.plugins.gemini.configs import SAFETY_SETTINGS
from google.genai.client import Client
from google.genai.types import Content, GenerateContentConfig, Part, ThinkingConfig
from pyrogram.types import ReplyParameters
from ub_core.utils import run_shell_cmd

from app import BOT, LOGGER, Convo, Message, bot

from .config import AIG_MODEL_LIST, get_system_prompt_with_tree
from .functions import execute_function
from .history import append_model_message, append_user_message, clear_history
from .tools import AIGENT_TOOLS

# ---------------------------------------------------------------------------
# Gemini client & config
# ---------------------------------------------------------------------------

_aigent_client = Client(api_key=os.getenv("AUTOBOT_GEMINI_API_KEY")).aio

# ---------------------------------------------------------------------------
# Model cycling (same list as autobot, skip first two)
# ---------------------------------------------------------------------------

_aig_model_idx = 0
_aig_requests_since_cycle = 0
_aig_last_logged_model = None


def _get_aig_model() -> str:
    return AIG_MODEL_LIST[_aig_model_idx]


def _cycle_aig_model():
    global _aig_model_idx, _aig_requests_since_cycle
    _aig_model_idx = (_aig_model_idx + 1) % len(AIG_MODEL_LIST)
    _aig_requests_since_cycle = 0
    LOGGER.info(f"Aigent: cycled model to {_get_aig_model()}")


def _get_aig_config() -> GenerateContentConfig:
    """Build a fresh config with the current project tree in the system prompt."""
    return GenerateContentConfig(
        candidate_count=1,
        system_instruction=get_system_prompt_with_tree(),
        temperature=0.5,
        max_output_tokens=60000,
        safety_settings=SAFETY_SETTINGS,
        thinking_config=ThinkingConfig(thinking_budget=0),
        tools=AIGENT_TOOLS,
    )

SHELL_PATTERN = re.compile(r"<SHELL>(.*?)</SHELL>", re.DOTALL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _history_to_contents(history: list[dict]) -> list[Content]:
    """Convert JSON history to google.genai Content objects."""
    contents = []
    for entry in history:
        parts = [
            Part.from_text(text=p["text"]) for p in entry["parts"] if p.get("text")
        ]
        if parts:
            contents.append(Content(role=entry["role"], parts=parts))
    return contents


async def _handle_shell_command(
    shell_cmd: str,
    convo: Convo,
    message: Message,
) -> str | None:
    """Show shell command and wait for user approval. Returns output or None."""
    prompt_msg = await convo.send_message(
        text=f"<pre language=shell>{shell_cmd.strip()}</pre>\n\nReply <code>ok</code> to run.",
        reply_to_id=message.id,
    )

    try:
        user_reply: Message = await convo.get_response()
    except TimeoutError:
        await prompt_msg.edit(f"{prompt_msg.text}\n\n<i>timed out, skipped.</i>")
        return None

    reply_text = (user_reply.text or "").strip().lower()
    if reply_text == "ok":
        output = await run_shell_cmd(cmd=shell_cmd.strip(), timeout=60)
        result_text = output.strip() or "(no output)"
        await convo.send_message(
            text=f"<pre language=shell>{result_text[:4000]}</pre>",
            reply_to_id=user_reply.id,
        )
        return result_text
    else:
        await convo.send_message(
            text="<i>skipped.</i>",
            reply_to_id=user_reply.id,
        )
        return None


async def _handle_edit_proposal(
    result: str,
    chat_id: int,
    message: Message,
) -> str:
    """Show edit diff and wait for user approval. Applies edits if approved."""
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return result  # not a valid proposal, pass through

    if data.get("type") != "EDIT_PROPOSAL":
        return result

    filepath = data["filepath"]
    edits = data["edits"]
    diff_text = data["diff"]
    filename = os.path.basename(filepath)

    # Show diff to user
    diff_display = diff_text[:3800] if diff_text else "(no diff generated)"
    diff_msg_text = (
        f"<b>Proposed edits to <code>{filename}</code>:</b>\n"
        f"<pre language=diff>{diff_display}</pre>\n\n"
        f"Reply <code>ok</code> to apply."
    )

    async with bot.Convo(
        chat_id=chat_id,
        client=bot,
        from_user=message.from_user.id,
        timeout=120,
    ) as convo:
        await convo.send_message(text=diff_msg_text, reply_to_id=message.id)

        try:
            user_reply: Message = await convo.get_response()
        except TimeoutError:
            return "Edit timed out, not applied."

        reply_text = (user_reply.text or "").strip().lower()
        if reply_text != "ok":
            await convo.send_message(
                text="<i>edit rejected.</i>", reply_to_id=user_reply.id
            )
            return "User rejected the edit."

    # Apply edits
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        for edit in edits:
            content = content.replace(edit["original_text"], edit["new_text"], 1)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        await bot.send_message(
            chat_id=chat_id,
            text=f"<code>{filename}</code> updated. ({len(edits)} edit(s) applied)",
            reply_parameters=ReplyParameters(message_id=message.id),
        )
        return f"Edit applied successfully to {filename}. {len(edits)} change(s) made."

    except Exception as e:
        LOGGER.error(f"Aigent edit apply error: {e}")
        return f"ERROR applying edit: {e}"


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


@bot.add_cmd(cmd="aig")
async def aigent_cmd(bot: BOT, message: Message):
    """
    CMD: AIG
    INFO: AI coding agent with tool-calling, file creation, editing, and shell commands.
    FLAGS: -c to clear history
    USAGE: .aig <message>
    """

    # --- Flag: clear history ---
    if "-c" in message.flags:
        clear_history(message.chat.id)
        await message.reply("aigent history cleared.")
        return

    user_input = message.filtered_input
    if not user_input:
        await message.reply(
            "provide a message.\nusage: <code>.aig &lt;message&gt;</code>", del_in=8
        )
        return

    chat_id = message.chat.id
    status_msg = await message.reply("<code>aigent thinking...</code>")

    # Cycle model if needed
    global _aig_requests_since_cycle, _aig_last_logged_model
    _aig_requests_since_cycle += 1
    if _aig_requests_since_cycle >= 19:
        _cycle_aig_model()

    model_name = _get_aig_model()
    if model_name != _aig_last_logged_model:
        _aig_last_logged_model = model_name
        LOGGER.info(f"Aigent using model: {model_name}")

    # Build config with fresh tree-injected system prompt
    aig_config = _get_aig_config()

    # Append user message to history
    history = await append_user_message(chat_id, user_input)
    contents = _history_to_contents(history)

    # --- Function-calling loop ---
    max_iterations = 10
    final_text = None
    last_func_names = []

    for _ in range(max_iterations):
        try:
            response = await _aigent_client.models.generate_content(
                contents=contents,
                model=model_name,
                config=aig_config,
            )
        except Exception as e:
            LOGGER.error(f"Aigent generation error: {e}")
            await status_msg.edit(f"<code>aigent error: {e}</code>")
            return

        if not response.candidates or not response.candidates[0].content:
            await status_msg.edit("<code>aigent: no response.</code>")
            return

        candidate = response.candidates[0]
        parts = candidate.content.parts or []

        # Collect all function calls from this response
        func_calls = [p for p in parts if p.function_call]

        if func_calls:
            func_names = [p.function_call.name for p in func_calls]
            last_func_names = func_names
            await status_msg.edit(
                f"<code>aigent calling: {', '.join(func_names)}...</code>"
            )

            # Append the full model response (with all function calls)
            contents.append(candidate.content)

            # Execute each function call and collect responses
            response_parts = []
            for fc_part in func_calls:
                func_name = fc_part.function_call.name
                func_args = (
                    dict(fc_part.function_call.args)
                    if fc_part.function_call.args
                    else {}
                )

                result = await execute_function(func_name, func_args)

                # Handle create_file: upload to chat
                if func_name == "create_file" and result.startswith("FILE_CREATED:"):
                    file_path = result.split("FILE_CREATED: ", 1)[1].strip()
                    if os.path.exists(file_path):
                        try:
                            await bot.send_document(
                                chat_id=chat_id,
                                document=file_path,
                                caption=f"<code>{os.path.basename(file_path)}</code>",
                                reply_parameters=ReplyParameters(message_id=message.id),
                            )
                        except Exception as e:
                            LOGGER.error(f"Aigent file upload error: {e}")

                # Handle upload_file: upload existing file to chat
                elif func_name == "upload_file" and result.startswith("UPLOAD_FILE:"):
                    file_path = result.split("UPLOAD_FILE: ", 1)[1].strip()
                    if os.path.exists(file_path):
                        try:
                            await bot.send_document(
                                chat_id=chat_id,
                                document=file_path,
                                caption=f"<code>{os.path.basename(file_path)}</code>",
                                reply_parameters=ReplyParameters(message_id=message.id),
                            )
                            result = f"Uploaded {os.path.basename(file_path)} to chat."
                        except Exception as e:
                            LOGGER.error(f"Aigent upload_file error: {e}")
                            result = f"ERROR uploading file: {e}"

                # Handle edit_file: show diff, wait for user approval
                elif func_name == "edit_file":
                    try:
                        parsed = json.loads(result)
                        if parsed.get("type") == "EDIT_PROPOSAL":
                            result = await _handle_edit_proposal(
                                result, chat_id, message
                            )
                    except (json.JSONDecodeError, TypeError):
                        pass  # result is already an error string

                response_parts.append(
                    Part.from_function_response(
                        name=func_name,
                        response={"result": result},
                    )
                )

            # Append all function responses as a single user turn
            contents.append(Content(role="user", parts=response_parts))
            continue

        # No function calls — final text response
        text_parts = [p.text for p in parts if p.text]
        if text_parts:
            final_text = "\n".join(text_parts).strip()
        break

    # If no text response but tool calls were made, generate a completion message
    if not final_text and last_func_names:
        final_text = "Done."

    if not final_text:
        await status_msg.edit("<code>aigent: empty response.</code>")
        return

    # Save model response to history
    await append_model_message(chat_id, final_text)

    # --- Check for <SHELL> commands ---
    shell_matches = SHELL_PATTERN.findall(final_text)

    if shell_matches:
        clean_text = SHELL_PATTERN.sub("", final_text).strip()

        if clean_text:
            await status_msg.edit(clean_text)
        else:
            await status_msg.delete()

        async with bot.Convo(
            chat_id=chat_id,
            client=bot,
            from_user=message.from_user.id,
            timeout=120,
        ) as convo:
            for cmd in shell_matches:
                await _handle_shell_command(cmd, convo, message)
    else:
        await status_msg.edit(final_text[:4096])
