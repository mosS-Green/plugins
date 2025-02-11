import yt_dlp

from app import bot, Message
from pyrogram.enums import ParseMode

from .text import text_gen, get_slow_text, Settings, run_basic_check


@bot.add_cmd(cmd="yt")
@run_basic_check
async def ytm_link(bot, message: Message):
    reply = message.replied
    content = reply.text if reply else message.input

    message_response = await message.reply("<code>...</code>")

    prompts = (
        "The following text contains a song name, extract that. "
        "Or guess the song based on description. use search for getting the name. reply only with song name and artist."
        "If you are unable to guess, just reply with 'Unknown Song':\n\n" + content
    )
    
    ai_response = await text_gen(
            contents=prompts, **Settings.get_kwargs()
    )
    song_name = get_slow_text(ai_response)

    if "unknown song" in song_name.lower() or not song_name:
        await message_response.edit("Couldn't determine the song title.")
        return

    await message_response.edit("<code>......</code>")

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'bestaudio/best',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f"ytsearch:{song_name}"
        info = ydl.extract_info(search_query, download=False)

        if info.get('entries'):
            video = info['entries'][0]
            video_id = video.get('id')

            if not video_id:
                await message_response.edit("Not found.")
                return

            ytm_link = f"https://music.youtube.com/watch?v={video_id}"

            await message_response.edit(
                f"<a href='{ytm_link}'>{song_name}</a>",
                disable_preview=True,
            )

        else:
            await message_response.edit("No search results found.")
