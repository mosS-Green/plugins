import yt_dlp
from app.modules.list_reminder import load_data, human_time_ago
from app import Config, bot
from pyrogram.types import Message


@bot.make_async
def get_ytm_link(song_name: str) -> str | None:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "format": "bestaudio/best",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f"ytsearch:{song_name}"
        info = ydl.extract_info(search_query, download=False)
        if info.get("entries"):
            video = info["entries"][0]
            video_id = video.get("id")
            if video_id:
                return f"https://music.youtube.com/watch?v={video_id}"
    return None


async def get_my_list() -> str:
    user_id = str(Config.OWNER_ID)
    data = await load_data()
    user_list = data.get(user_id, [])

    if not user_list:
        return "Your list is empty."

    lines = []
    for i, item in enumerate(user_list, 1):
        text = item["text"]
        ago = human_time_ago(item["time"])
        if "link" in item:
            line = f"{i}. <a href='{item['link']}'>{text}</a> <i>({ago})</i>"
        else:
            line = f"{i}. {text} <i>({ago})</i>"
        lines.append(line)

    resp = "<b>Leaf's list:</b>\n" + "\n".join(lines)
    return resp


FUNCTION_MAP = {
    "get_ytm_link": get_ytm_link,
    "get_my_list": get_my_list,
}


async def execute_function(part, message: Message | None = None):
    try:
        func_name = part.function_call.name
        func_args = part.function_call.args

        if func_name in FUNCTION_MAP:
            return await FUNCTION_MAP[func_name](**func_args)

        return f"Error: Unknown function '{func_name}'"
    except Exception as e:
        return f"Error executing function '{func_name}': {str(e)}"
