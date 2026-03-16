import asyncio
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from ub_core import BOT, Message
from ub_core.utils import run_shell_cmd, progress
from ub_core.utils.downloader import DownloadedFile

# Regex to find Facebook URLs
FB_URL_REGEX = r"https?://(?:www\.)?(?:m\.)?(?:facebook\.com|fb\.watch|fb\.com)\S*"


@BOT.add_cmd(cmd="fbdl")
async def facebook_downloader(bot: BOT, message: Message):
    """
    CMD: FBDL
    INFO: Downloads Facebook video(s) using yt-dlp and sends them as documents.
    USAGE: .fbdl <facebook_link(s)> | Reply to message with facebook link(s)
    """
    links = []
    input_text = message.filtered_input

    # Get links from the command argument
    if input_text:
        links.extend(re.findall(FB_URL_REGEX, input_text))

    # Get links from replied message
    if message.replied and message.replied.text:
        links.extend(re.findall(FB_URL_REGEX, message.replied.text))

    if not links:
        await message.reply(
            "No Facebook links found in your message or replied message. Please provide valid links.",
            del_in=10,
        )
        return

    # Remove duplicates
    unique_links = list(set(links))

    status_message = await message.reply(
        f"Found {len(unique_links)} Facebook link(s). Starting download..."
    )

    download_dir = Path(tempfile.mkdtemp(prefix="fbdl_"))

    try:
        # Construct yt-dlp command
        # -P sets output directory
        # --restrict-filenames: restricts filenames to only ASCII characters
        # --no-warnings --ignore-errors: suppresses non-critical output
        # --no-playlist: prevents downloading entire playlists if a playlist link is given
        # --format "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best": tries to get best quality MP4 with audio, fallback to best MP4, then general best
        # --output "%(title)s.%(ext)s": sets output filename pattern
        yt_dlp_command = [
            "yt-dlp",
            "-P",
            str(download_dir),
            "--restrict-filenames",
            "--no-warnings",
            "--ignore-errors",
            "--no-playlist",
            "--format",
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--output",
            "%(title)s.%(ext)s",
            *unique_links,
        ]

        await status_message.edit(
            f"Downloading {len(unique_links)} video(s) using yt-dlp..."
        )

        # Execute yt-dlp command
        stdout = await run_shell_cmd(
            cmd=shlex.join(yt_dlp_command), timeout=600
        )  # Increased timeout for potentially large files

        # Check if any files were downloaded
        downloaded_files = list(download_dir.iterdir())
        if not downloaded_files:
            await status_message.edit(
                f"Failed to download video(s) from the provided links. yt-dlp output:\n<pre>{stdout or 'No output'}</pre>",
                parse_mode="html",
            )
            return

        await status_message.edit(
            f"Download complete. Uploading {len(downloaded_files)} file(s) to Telegram..."
        )

        # Determine Telegram upload limit (2GB for non-premium, 4GB for premium)
        max_tg_upload_size = 2 * 1024 * 1024 * 1024  # 2 GB
        if bot.me.is_premium:
            max_tg_upload_size = 4 * 1024 * 1024 * 1024  # 4 GB

        for file_path in sorted(downloaded_files):  # Sort to ensure consistent order
            if file_path.is_file():
                try:
                    file_info = DownloadedFile(file=file_path)

                    file_size_bytes = file_path.stat().st_size
                    if file_size_bytes > max_tg_upload_size:
                        await message.reply(
                            f"Skipping {file_info.name} as its size ({file_info.size:.2f} MB) exceeds Telegram's upload limit ({max_tg_upload_size / (1024*1024*1024):.0f} GB)."
                        )
                        continue

                    upload_msg = await message.reply(f"Uploading: `{file_info.name}`")

                    await bot.send_document(
                        chat_id=message.chat.id,
                        document=str(file_path),
                        caption=file_info.name,
                        reply_to_message_id=message.id,  # Reply to the original command message
                        progress=progress,
                        progress_args=(upload_msg, "Uploading...", str(file_path)),
                        disable_content_type_detection=True,
                    )
                    await upload_msg.delete()  # Delete the "Uploading..." message after successful upload

                except asyncio.CancelledError:
                    await message.reply(f"Upload of {file_path.name} cancelled.")
                    # Optionally, break the loop if all uploads should stop
                    break
                except Exception as e:
                    await message.reply(f"Failed to upload {file_path.name}: {e}")
                    # Continue with other files

        await status_message.edit("All requested videos processed.", del_in=5)

    except asyncio.CancelledError:
        await status_message.edit("Facebook download task cancelled.")
    except Exception as e:
        await status_message.edit(
            f"An unexpected error occurred during processing: {e}"
        )
    finally:
        if download_dir.exists():
            shutil.rmtree(download_dir, ignore_errors=True)
