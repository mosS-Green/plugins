import os
import json
from functools import wraps

from google.genai.types import (
    DynamicRetrievalConfig,
    GenerateContentConfig,
    GoogleSearchRetrieval,
    SafetySetting,
    Tool,
)
from pyrogram import filters

from app import BOT, Message, extra_config

@bot.add_cmd(cmd="fh")
async def init_task(bot=bot, message=None):
    past_message_id = int(os.environ.get("PAST_MESSAGE_ID"))
    
    past_message = await bot.get_messages(
        chat_id=Config.LOG_CHAT, message_ids=past_message_id
    )

    global PAST
    PAST = json.loads(past_message.text)
    
    if message is not None:
        await message.reply("Done.", del_in=5)


class Fast:
    MODEL = "gemini-2.0-flash"

    # fmt:off
    CONFIG = GenerateContentConfig(

        system_instruction=PAST,

        temperature=0.9,

        max_output_tokens=4000,

        safety_settings=[
            SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="BLOCK_NONE"),
        ],
        # fmt:on

        tools=[
            Tool(
                google_search=GoogleSearchRetrieval(
                    dynamic_retrieval_config=DynamicRetrievalConfig(
                        dynamic_threshold=0.3
                    )
                )
            )
        ],
    )

    @staticmethod
    def get_kwargs() -> dict:
        return {"model": Fast.MODEL, "config": Fast.CONFIG}
