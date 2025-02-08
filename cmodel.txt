import os
import json
import copy

from pyrogram import filters
from app.plugins.ai.models import Settings

from app import BOT, Message, Config, bot

CMODEL = copy.deepcopy(Settings)

@bot.add_cmd(cmd="fh")
async def init_task(bot=bot, message=None):
    past_message_id = int(os.environ.get("PAST_MESSAGE_ID"))

    past_message = await bot.get_messages(
        chat_id=Config.LOG_CHAT, message_ids=past_message_id
    )

    json_data = json.loads(past_message.text)
    CMODEL.MODEL = json_data["model"]
    CMODEL.CONFIG.system_instruction = json_data["text"]

    if message is not None:
        await message.reply("Done.", del_in=5)
