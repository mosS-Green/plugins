import os

from ub_core import BOT, Config, Message

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

    await message.reply(resp_str, disable_preview=True)
