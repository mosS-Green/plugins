import yt_dlp

from app import bot, Message
from pyrogram.enums import ParseMode

from app.plugins.ai.models import async_client, get_response_text, Settings, run_basic_check


@bot.add_cmd(cmd="yt")
@run_basic_check
async def ytm_link(bot, message: Message):
    reply = message.replied
    content = reply.text if reply else message.input

    message_response = await message.reply("<code>...</code>")

    prompt = (
        "Extract the song title and artist from the following text. "
        "If there’s no clear song title, just reply with 'Unknown Song':\n\n" + content
    )
    
    ai_response = await async_client.models.generate_content(contents=[prompt], **Settings.get_kwargs())
    song_name = get_response_text(ai_response)

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
                f"[{song_name}]({ytm_link})",
                parse_mode=ParseMode.MARKDOWN,
                disable_preview=True,
            )

        else:
            await message_response.edit("No search results found.")
