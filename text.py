

from app import BOT, Message, bot
from pyrogram.enums import ParseMode

from .aicore import MODEL, ask_ai, run_basic_check
from .telegraph import tele_graph
from ub_core.utils import run_shell_cmd


import os

@bot.add_cmd(cmd="dbg")
async def debug_logs(bot: BOT, message: Message):
    text = await run_shell_cmd(cmd=f"tail -n 50 logs/app_logs.txt")
    
    if os.path.exists("codebase_context.txt"):
        try:
            with open("codebase_context.txt", "r", encoding="utf-8") as f:
                context = f.read()
            text += f"\n\n=== Codebase Context ===\n{context}"
        except Exception:
            pass

    extra_input = f"\n\nUser Input: {message.input}" if message.input else ""
    prompt = f"Analyze these logs and very concisely tell me what the issue was. Say No issues if none detected. Use the provided codebase context to identify specific files/plugins involved. Ignore the sqlite3 errors.{extra_input}"
    
    ai_response = await ask_ai(prompt=prompt, query=text, quote=True, **MODEL["DEFAULT"])
    
    await message.reply(ai_response)



@bot.add_cmd(cmd=["r", "rx"])
@run_basic_check
async def r_question(bot: BOT, message: Message):
    reply = message.replied
    input = message.input

    user_first_name = message.from_user.first_name if message.input else None
    reply_first_name = reply.from_user.first_name if reply and reply.from_user else None

    if (
        message.cmd == "rx"
        and reply
        and reply_first_name
        and not (reply.media or not input)
    ):
        prompt = f"[{user_first_name}]:- {input}"
        query = f"[{reply_first_name}]:- {reply.text}" if reply.text else None
    else:
        prompt = input
        query = reply

    loading_msg = await message.reply("<code>...</code>")

    model = MODEL["LEAF"] if message.cmd == "rx" else MODEL["DEFAULT"]
    ai_text = await ask_ai(prompt=prompt, query=query, quote=True, **model)

    await loading_msg.edit(
        text=ai_text, parse_mode=ParseMode.MARKDOWN, disable_preview=True
    )


@bot.add_cmd(cmd="rt")
@run_basic_check
async def ai_think(bot: BOT, message: Message):
    reply = message.replied
    prompts = message.input
    load_msg = await message.reply("<code>...</code>")
    content = await ask_ai(prompt=prompts, query=reply, **MODEL["THINK"])
    await tele_graph(load_msg=load_msg, title="Answer", text=content)


@bot.add_cmd(cmd="f")
@run_basic_check
async def fix(bot: BOT, message: Message):
    prompts = (
        "REWRITE FOLLOWING MESSAGE AS IS, "
        "WITH NO CHANGES TO FORMAT AND SYMBOLS ETC."
        f"AND ONLY WITH CORRECTION TO SPELLING ERRORS :- "
        f"\n{message.replied.text}"
    )
    response = await ask_ai(prompt=prompts, **MODEL["QUICK"])
    await message.replied.edit(response)
