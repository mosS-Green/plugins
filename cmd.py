import os

from app import BOT, Config, Message

from .aicore import MODEL, ask_ai
from .telegraph import tele_graph

Config.CMD_DICT["eu"] = Config.CMD_DICT["extupdate"]

Config.CMD_DICT["ry"] = Config.CMD_DICT["reply"]


@BOT.add_cmd(cmd="ch")
async def plugin_info(bot: BOT, message: Message):
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
    resp_str = f"**>\n**{cmd}** : <a href='{remote_url}'>{plugin}</a><**"

    response = await message.reply(resp_str, disable_preview=True)

    if "-d" in message.flags:
        load_msg = await response.reply("<code>...</code>")
        title = f"Ainalysis of {plugin}"

        with open(plugin_path, "r") as file:
            content = file.read()

        analyze_prompt = (
            "Analyze the following code for errors and suggest optimizations for "
            "performance, readability, and efficiency. Highlight potential bugs, "
            "redundant code, and areas for improvement."
        )

        input = message.filtered_input or analyze_prompt
        prompts = f"{input}\n\nCode:\n```{content}```"
        analysis = await ask_ai(prompt=prompts, **MODEL["THINK"])

        await tele_graph(load_msg, title, analysis)
