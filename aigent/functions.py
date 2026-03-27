import json
import os
import difflib

from app import LOGGER
from app.modules.models import ask_ai

from .config import AIG_TEMP_DIR, PROJECT_ROOT


async def ask_default_ai(prompt: str, with_codebase: bool = False) -> str:
    """Delegate a prompt to the default AI model, optionally with full codebase context."""
    try:
        if with_codebase:
            from app.plugins.ai.gemini import Response, async_client
            from app.plugins.ai.gemini.code import upload_codebase
            from app.modules.models import get_model_and_config

            prompts = [prompt, await upload_codebase()]

            kwargs = await get_model_and_config(model_name="THINK")

            response = await async_client.models.generate_content(
                contents=prompts, **kwargs
            )

            result = Response(response)
            return f"PROMPT: {prompt}\nRESPONSE: {result.text}"

        else:
            result = await ask_ai(prompt=prompt)

        return f"PROMPT: {prompt}\nRESPONSE: {result}"
    except Exception as e:
        LOGGER.error(f"Aigent ask_default_ai error: {e}")
        return f"PROMPT: {prompt}\nERROR: {e}"


async def create_file(filename: str, content: str) -> str:
    """Create a file at the given path relative to project root."""
    try:
        file_path = os.path.join(PROJECT_ROOT, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"FILE_CREATED: {file_path}"
    except Exception as e:
        LOGGER.error(f"Aigent create_file error: {e}")
        return f"ERROR: {e}"


async def upload_file(filepath: str) -> str:
    """Return the absolute path of an existing file to be uploaded to chat."""
    full_path = os.path.join(PROJECT_ROOT, filepath)
    if not os.path.isfile(full_path):
        return f"ERROR: File not found: {filepath}"
    return f"UPLOAD_FILE: {full_path}"


def read_file(filepath: str) -> str:
    """Read and return the contents of a file."""
    full_path = os.path.join(PROJECT_ROOT, filepath)
    if not os.path.isfile(full_path):
        return f"ERROR: File not found: {filepath}"
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > 50_000:
            content = content[:50_000] + "\n... (truncated at 50KB)"
        return content
    except Exception as e:
        return f"ERROR reading file: {e}"


async def edit_file(filepath: str, instruction: str) -> str:
    """Generate edits via the default model and return a structured proposal."""
    full_path = os.path.join(PROJECT_ROOT, filepath)
    if not os.path.isfile(full_path):
        return f"ERROR: File not found: {filepath}"

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"ERROR reading file: {e}"

    edit_prompt = (
        "You are given a file and an edit instruction. "
        "Return a JSON list of edits. Each edit has:\n"
        '  - "original_text": the exact substring to find in the file (must match exactly)\n'
        '  - "new_text": the replacement text\n\n'
        "To insert new code, use a nearby line as original_text and include it "
        "along with the new code in new_text.\n"
        "To delete code, set new_text to an empty string.\n"
        "Return ONLY the JSON list, nothing else.\n\n"
        f"---FILE: {filepath}---\n{content}\n---END FILE---\n\n"
        f"Instruction: {instruction}"
    )

    from app.plugins.ai.gemini.client import async_client as default_client
    from google.genai.types import GenerateContentConfig

    response = await default_client.models.generate_content(
        contents=[edit_prompt],
        model="gemini-2.5-flash",
        config=GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    if not response.candidates or not response.candidates[0].content:
        return "ERROR: Default model returned no response for edit."

    raw_json = response.candidates[0].content.parts[0].text.strip()

    try:
        edits = json.loads(raw_json)
        if not isinstance(edits, list):
            edits = [edits]
    except json.JSONDecodeError:
        return f"ERROR: Default model returned invalid JSON: {raw_json[:500]}"

    # Validate all original_text values exist in the file
    for i, edit in enumerate(edits):
        if "original_text" not in edit or "new_text" not in edit:
            return (
                f"ERROR: Edit #{i + 1} missing required fields. Raw: {raw_json[:500]}"
            )
        if edit["original_text"] not in content:
            return (
                f"ERROR: Edit #{i + 1} original_text not found in file.\n"
                f"Looking for: {edit['original_text'][:200]}"
            )

    # Generate unified diff preview
    modified = content
    for edit in edits:
        modified = modified.replace(edit["original_text"], edit["new_text"], 1)

    diff_lines = list(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=filepath,
            tofile=filepath,
        )
    )
    diff_text = "".join(diff_lines)

    return json.dumps(
        {
            "type": "EDIT_PROPOSAL",
            "filepath": full_path,
            "edits": edits,
            "diff": diff_text,
        }
    )


async def download_replied_file(save_as: str = "", _message=None) -> str:
    """Download the replied file to the aig temp directory."""
    if _message is None:
        return "ERROR: No replied file available. The user must reply to a file/media message."

    try:
        from ub_core.utils import get_tg_media_details

        media = get_tg_media_details(_message)
        original_name = getattr(media, "file_name", None) or "file"
        file_name = save_as if save_as else original_name

        save_path = os.path.join(AIG_TEMP_DIR, file_name)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        await _message.download(file_name=save_path)

        # Return relative path for consistency
        rel_path = os.path.relpath(save_path, PROJECT_ROOT)
        return f"FILE_DOWNLOADED: {rel_path}"
    except Exception as e:
        LOGGER.error(f"Aigent download_replied_file error: {e}")
        return f"ERROR downloading file: {e}"


FUNCTION_MAP = {
    "ask_default_ai": ask_default_ai,
    "create_file": create_file,
    "upload_file": upload_file,
    "read_file": read_file,
    "edit_file": edit_file,
    "download_replied_file": download_replied_file,
}


async def execute_function(func_name: str, func_args: dict) -> str:
    """Execute a tool function by name and return the result string."""
    if func_name not in FUNCTION_MAP:
        return f"ERROR: Unknown function '{func_name}'"

    func = FUNCTION_MAP[func_name]

    try:
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return await func(**func_args)
        else:
            return func(**func_args)
    except Exception as e:
        LOGGER.error(f"Aigent execute_function '{func_name}' error: {e}")
        return f"ERROR executing '{func_name}': {e}"

