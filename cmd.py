import os

from app import BOT, Config, Message, bot
from pyrogram.enums import ParseMode


async def init_task(bot=bot, message=None):
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


@bot.add_cmd("ey")
async def mention_others(bot, message):
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
