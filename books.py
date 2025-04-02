import libgen_api_enhanced

from pyrogram.enums import ParseMode
from ub_core import BOT, Message, bot


@bot.add_cmd(cmd="b")
async def search_books_filtered(bot: BOT, message: Message):
    if not message.input:
        await message.reply(
            "Please provide a search query after the command.\nExample: /b Pride and Prejudice"
        )
        return

    query = message.input
    loading_msg = await message.reply(f"Searching for books matching {query}...")

    s = libgen_api_enhanced.LibgenSearch()
    search_filters = {"Extension": "epub"}

    try:
        results = s.search_default_filtered(query, search_filters, exact_match=False)

        if not results:
            await loading_msg.edit_text(f"No EPUB results found for {query}.")
            return

        if "-10" in message.flags:
            top_results = results[:10]
        elif "-20" in message.flags:
            top_results = results[:20]
        else:
            top_results = results[:5]

        output_text = f"Top {len(top_results)} ebook results for {query}:\n\n"

        for i, book in enumerate(top_results):
            title = book.get("Title", "N/A")
            author = book.get("Author", "N/A")
            download_link = book.get("Direct_Download_Link")

            display_title = (title[:40] + "...") if len(title) > 40 else title

            if download_link:
                title_link = f"**[{display_title}]({download_link})**"
            else:
                title_link = f"**{display_title}**"

            output_text += f"{i + 1}. {title_link}\n   __by {author}__\n\n"

        await loading_msg.edit_text(
            output_text.strip(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    except Exception as e:
        await loading_msg.edit_text(f"An error occurred during the search: {str(e)}")
