import os
from app import BOT, Config, Message, bot
from .aicore import ask_ai, MODEL
from .telegraph import post_to_telegraph

Config.CMD_DICT["eu"] = Config.CMD_DICT["extupdate"]

Config.CMD_DICT["ry"] = Config.CMD_DICT["reply"]


@BOT.add_cmd(cmd="ch")
async def plugin_info(bot: BOT, message: Message):

    cmd = message.filtered_input
    cmd_obj = Config.CMD_DICT.get(cmd)

    plugin_path = os.path.relpath(cmd_obj.cmd_path, os.curdir)
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
        
        with open(plugin_path, 'r') as file:
            content = file.read()

        prompts = (
            f"Analyze the following code for errors and suggest optimizations for "
            f"performance, readability, and efficiency. Highlight potential bugs, "
            f"redundant code, and areas for improvement.\n\nCode:\n```{content}```"
        )
        article = await ask_ai(prompt=prompts, **MODEL["THINK"])
        page_url = await post_to_telegraph(title, article, "leaflet", "t.me/leafinferno")

        await load_msg.edit(
            f"[{title}]({page_url})",
            parse_mode=ParseMode.MARKDOWN,
            disable_preview=True
        )
