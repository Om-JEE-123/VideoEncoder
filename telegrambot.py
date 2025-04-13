import os
import logging
import asyncio
import tempfile
import time
from datetime import datetime
import threading
from typing import Dict, Any, Optional, Tuple
import traceback
import sys

# Import config
import config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)] # Ensure logs go to stdout
)
logger = logging.getLogger(__name__)

try:
    import ffmpeg
    from telethon import TelegramClient, events, Button
    from telethon.errors import SessionPasswordNeededError, FloodWaitError, FileMigrateError, MessageNotModifiedError, AboutTooLongError, AuthKeyError, UserDeactivatedBanError
    from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename
    from telethon.utils import get_display_name

    from queue_manager import QueueManager # Keep using the same queue manager
    from utils import get_file_size_mb, ensure_temp_dir, clean_temp_files, format_time

    # --- Database (Optional - Requires Async/Threaded Implementation) ---
    # from sqlalchemy.orm import Session
    # from models import User, CompressionJob, UserPreference, Base
    # db_session: Optional[Session] = None # Needs proper async initialization
    # --------------------------------------------------------------------

except ImportError as e:
    logger.critical(f"Failed to import necessary libraries: {e}. Please ensure all dependencies (telethon, ffmpeg-python, etc.) are installed.")
    sys.exit(1)

# --- Telethon Bot Implementation ---

# Global variables
queue_manager = QueueManager()
# Dictionary to track active processing status messages by user_id
active_status_messages = {}

# --- Helper Functions ---

async def progress_callback(current, total, client, event, start_time, mode, status_msg_id):
    """Telethon progress callback to update status message."""
    user_id = event.sender_id
    now = time.time()
    diff = now - start_time
    if diff < 1.0 and current != total: # Avoid too frequent updates at start/end
        return

    percentage = round(current / total * 100, 1)
    speed = current / diff if diff > 0 else 0
    speed_mb = speed / (1024 * 1024)
    eta_seconds = (total - current) / speed if speed > 0 else 0

    # Limit updates frequency (e.g., every 3 seconds or 5%)
    last_update_time = active_status_messages.get(user_id, {}).get('last_progress_update', 0)
    last_percentage = active_status_messages.get(user_id, {}).get('last_percentage', -10)

    if now - last_update_time > 3 or percentage - last_percentage >= 5 or current == total:
        progress_str = f"{percentage}% ({speed_mb:.1f} MB/s)"
        eta_str = f"ETA: {format_time(eta_seconds)}" if eta_seconds > 0 else ""
        text = f"🔄 Status: {mode}\n📊 Progress: {progress_str}\n⏳ {eta_str}"

        try:
            if status_msg_id:
                await client.edit_message(event.chat_id, status_msg_id, text)
                # Update last update time and percentage in global tracker
                if user_id in active_status_messages:
                     active_status_messages[user_id]['last_progress_update'] = now
                     active_status_messages[user_id]['last_percentage'] = percentage

        except MessageNotModifiedError:
            pass # Ignore if message hasn't changed
        except FloodWaitError as fwe:
            logger.warning(f"Flood wait ({fwe.seconds}s) during progress update for user {user_id}.")
            await asyncio.sleep(fwe.seconds + 1) # Wait before next potential update
        except Exception as e:
            logger.warning(f"Failed to edit progress message for user {user_id}: {e}")


async def run_ffmpeg_process(ffmpeg_cmd, timeout):
    """Runs the ffmpeg command asynchronously with a timeout."""
    logger.info(f"Running FFmpeg command: {' '.join(ffmpeg_cmd.compile())}")
    proc = await asyncio.create_subprocess_exec(
        *ffmpeg_cmd.compile(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "FFmpeg failed with no stderr"
            logger.error(f"FFmpeg error (code {proc.returncode}): {error_msg}")
            raise ffmpeg.Error('ffmpeg', stdout, stderr)
        logger.info("FFmpeg process completed successfully.")
        return True, None # Success, No Error Message
    except asyncio.TimeoutError:
        logger.error(f"FFmpeg processing timed out after {timeout} seconds.")
        try:
            proc.kill()
            await proc.wait()
            logger.info("Killed hanging FFmpeg process.")
        except Exception as kill_err:
            logger.error(f"Error trying to kill FFmpeg process: {kill_err}")
        return False, f"Processing timed out after {timeout}s" # Failure, Error Message
    except ffmpeg.Error as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if hasattr(e, 'stderr') and e.stderr else str(e)
        logger.error(f"Error during FFmpeg execution: {error_msg}")
        return False, f"Compression failed: {error_msg[:255]}" # Failure, Error Message
    except Exception as e:
        logger.error(f"Unexpected error running ffmpeg: {e}", exc_info=True)
        return False, f"Unexpected FFmpeg error: {str(e)[:255]}" # Failure, Error Message


async def process_video_file(
    client: TelegramClient,
    event: events.NewMessage.Event,
    original_filename: str,
    status_msg_id: int,
    job_id: Optional[int] = None
) -> Tuple[Optional[str], Optional[str], dict, Optional[str]]:
    """Downloads, compresses, and prepares the video file for upload. Returns paths, stats, and error message if any."""
    stats = {'processing_time': 0}
    start_time_total = time.time()
    original_file_path = None
    compressed_file_path = None
    temp_dir = None
    error_message = None # Store potential errors

    try:
        # 1. Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="video_proc_", dir=config.TEMP_DIR)
        logger.info(f"Created temp dir: {temp_dir}")

        # 2. Download the file
        await client.edit_message(event.chat_id, status_msg_id, "⬇️ Downloading video...")
        download_start_time = time.time()

        # Prepare path for download
        original_file_path = os.path.join(temp_dir, f"original_{original_filename}")

        # Download using Telethon
        downloaded_file_obj = await client.download_media(
            message=event.message,
            file=original_file_path,
            progress_callback=lambda c, t: progress_callback(c, t, client, event, download_start_time, "Downloading", status_msg_id)
        )

        if not downloaded_file_obj or not os.path.exists(original_file_path):
             raise ValueError("Download failed or file not found after download.")

        download_duration = time.time() - download_start_time
        logger.info(f"Download complete: {original_file_path} ({download_duration:.2f}s)")

        # 3. Probe video file
        await client.edit_message(event.chat_id, status_msg_id, "🔍 Analyzing video...")
        try:
            probe = await asyncio.to_thread(ffmpeg.probe, original_file_path)
        except ffmpeg.Error as e:
            error_message = f"FFmpeg probe failed: {e.stderr.decode() if e.stderr else str(e)}"
            logger.error(error_message)
            await client.edit_message(event.chat_id, status_msg_id, f"❌ Analysis failed: {error_message[:100]}...")
            # Don't return here yet, allow cleanup in finally block
            return None, None, stats, error_message # Return error

        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if not video_stream:
            error_message = "No video stream found in the file"
            logger.error(error_message)
            await client.edit_message(event.chat_id, status_msg_id, f"❌ Error: {error_message}")
            return None, None, stats, error_message # Return error

        logger.info("Video probe successful.")

        # 4. Compression
        await client.edit_message(event.chat_id, status_msg_id, "⚙️ Compressing video...")
        width = int(video_stream['width'])
        height = int(video_stream['height'])

        # Calculate new dimensions
        if height <= config.DEFAULT_HEIGHT:
            new_height = height
            new_width = width
        else:
            new_height = config.DEFAULT_HEIGHT
            new_width = int(width * (new_height / height))
            if new_width % 2 != 0: new_width += 1 # Ensure even width

        # Define compressed path
        base, _ = os.path.splitext(original_filename)
        compressed_filename = f"compressed_{base}.mkv"
        compressed_file_path = os.path.join(temp_dir, compressed_filename)

        # Prepare FFmpeg command
        ffmpeg_cmd = (
            ffmpeg
            .input(original_file_path)
            .output(
                compressed_file_path,
                vf=f'scale={new_width}:{new_height}',
                video_bitrate=config.DEFAULT_VIDEO_BITRATE,
                audio_bitrate=config.DEFAULT_AUDIO_BITRATE,
                preset=config.DEFAULT_PRESET,
                crf=config.DEFAULT_CRF,
                acodec='aac', # Explicitly set audio codec compatible with MKV
                vcodec='libx264', # Explicitly set video codec
                format='matroska'
            )
            .overwrite_output()
        )

        # Run FFmpeg with timeout
        compression_success, ffmpeg_error = await run_ffmpeg_process(ffmpeg_cmd, config.PROCESSING_TIMEOUT)

        if not compression_success:
            error_message = ffmpeg_error or "Compression failed for unknown reasons."
            await client.edit_message(event.chat_id, status_msg_id, f"❌ Error: {error_message}")
            return original_file_path, None, stats, error_message # Return error

        if not os.path.exists(compressed_file_path) or os.path.getsize(compressed_file_path) == 0:
            error_message = "Compression finished, but output file is missing or empty."
            logger.error(error_message)
            await client.edit_message(event.chat_id, status_msg_id, f"❌ Error: {error_message}")
            return original_file_path, None, stats, error_message # Return error

        # Calculate processing time
        processing_time = time.time() - start_time_total
        stats['processing_time'] = processing_time
        logger.info(f"Processing complete ({processing_time:.2f}s). Output: {compressed_file_path}")

        return original_file_path, compressed_file_path, stats, None # Success!

    except FileMigrateError as e:
         logger.error(f"FileMigrateError during download for user {event.sender_id}: {e}. This indicates a DC transfer issue.")
         error_message = "Telegram DC transfer error during download. Please try again later."
         try: await client.edit_message(event.chat_id, status_msg_id, f"❌ Error: {error_message}")
         except: pass
         return None, None, stats, error_message
    except ValueError as e: # Catch specific errors like download failure message
         logger.error(f"ValueError during processing for user {event.sender_id}: {e}")
         error_message = str(e)
         try: await client.edit_message(event.chat_id, status_msg_id, f"❌ Error: {error_message}")
         except: pass
         return None, None, stats, error_message
    except Exception as e:
        logger.error(f"Unexpected error in process_video_file for user {event.sender_id}: {e}", exc_info=True)
        error_message = f"An unexpected error occurred: {str(e)[:100]}"
        try: await client.edit_message(event.chat_id, status_msg_id, f"❌ Error: {error_message}")
        except: pass
        # Try to return original path for cleanup if download succeeded
        return original_file_path if os.path.exists(original_file_path or "") else None, None, stats, error_message
    # Note: Cleanup should happen in the calling function `process_next_video`'s finally block


# --- Telethon Event Handlers ---

async def process_next_video(client: TelegramClient):
    """Processes the next video from the queue."""
    if queue_manager.is_empty():
        return

    user_id, data = queue_manager.get_current_task()
    if not user_id or not data:
        logger.warning("Could not get current task from queue despite not being empty.")
        return

    event = data['event'] # The original event object
    chat_id = event.chat_id
    job_id = data.get('job_id')
    status_msg = data['status_msg']
    video_file_name = data['video_file_name']
    video_file_size = data['video_file_size']
    status_msg_id = status_msg.id
    original_file_path = None
    compressed_file_path = None

    logger.info(f"Starting processing task for user {user_id} from queue.")
    # Store status message info for progress callback
    active_status_messages[user_id] = {'msg_id': status_msg_id, 'last_progress_update': 0, 'last_percentage': -10}


    try:
        # Process (Download & Compress)
        original_file_path, compressed_file_path, compression_stats, error = await process_video_file(
            client, event, video_file_name, status_msg_id, job_id
        )

        # If processing failed
        if error or not compressed_file_path or not os.path.exists(compressed_file_path):
            logger.error(f"Processing failed for user {user_id}. Error: {error}")
            # Error message should have been edited by process_video_file
            return # Stop processing this item

        # Upload the compressed file
        await client.edit_message(chat_id, status_msg_id, "⬆️ Uploading compressed video...")
        upload_start_time = time.time()

        original_size_mb = get_file_size_mb(os.path.getsize(original_file_path))
        compressed_size_mb = get_file_size_mb(os.path.getsize(compressed_file_path))
        size_reduction = (original_size_mb - compressed_size_mb) / original_size_mb * 100 if original_size_mb > 0 else 0
        processing_time_str = format_time(compression_stats.get('processing_time', 0))

        # Corrected caption definition with explicit \n
        caption = (
            f"🎬 Compressed Video ({config.DEFAULT_HEIGHT}p)\n\n"
            f"📊 Original size: {original_size_mb:.2f} MB\n"
            f"📊 Compressed size: {compressed_size_mb:.2f} MB\n"
            f"📉 Size reduction: {size_reduction:.1f}%\n"
            f"⏱️ Processing time: {processing_time_str}\n\n"
            # f"Bot by @your_username_here" # Optional: Add your bot username
        )

        # Get video duration from ffmpeg stats if possible for thumbnail generation
        thumb = None
        duration = 0
        try:
             probe = await asyncio.to_thread(ffmpeg.probe, compressed_file_path)
             vid_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
             if vid_stream and 'duration' in vid_stream:
                  duration = int(float(vid_stream['duration']))
             # Simple thumbnail generation (optional, requires ffmpeg)
             thumb_path = os.path.join(os.path.dirname(compressed_file_path), "thumb.jpg")
             (
                 ffmpeg
                 .input(compressed_file_path, ss=duration * 0.1) # Seek 10% into video
                 .output(thumb_path, vframes=1, s='160x160') # Output one frame scaled
                 .overwrite_output()
                 .run(quiet=True)
             )
             if os.path.exists(thumb_path):
                  thumb = thumb_path
        except Exception as thumb_err:
             logger.warning(f"Could not generate thumbnail: {thumb_err}")


        # Define video attributes
        attributes = [
            DocumentAttributeVideo(
                duration=duration,
                w=int(vid_stream['width']) if vid_stream else 0,
                h=int(vid_stream['height']) if vid_stream else 0,
                supports_streaming=True
            ),
            DocumentAttributeFilename(file_name=os.path.basename(compressed_file_path))
        ]

        # Upload
        await client.send_file(
            chat_id,
            compressed_file_path,
            caption=caption,
            thumb=thumb,
            attributes=attributes,
            progress_callback=lambda c, t: progress_callback(c, t, client, event, upload_start_time, "Uploading", status_msg_id)
        )

        upload_duration = time.time() - upload_start_time
        logger.info(f"Upload successful for user {user_id} ({upload_duration:.2f}s).")

        # Final status update
        final_status_text = (
            f"✅ Video compressed and delivered!\n"
            f"📉 Size reduction: {size_reduction:.1f}%\n"
            f"⏱️ Processing time: {processing_time_str}"
        )
        await client.edit_message(chat_id, status_msg_id, final_status_text)

    except FloodWaitError as fwe:
        logger.error(f"Flood wait ({fwe.seconds}s) during processing/upload for user {user_id}.")
        await asyncio.sleep(fwe.seconds + 5) # Wait significantly before retrying anything
        # Re-add task to queue? Or just fail? For now, fail.
        try: await client.edit_message(chat_id, status_msg_id, f"❌ A Telegram flood wait occurred ({fwe.seconds}s). Please try again later.")
        except: pass
    except Exception as e:
        logger.error(f"Unhandled error in process_next_video for user {user_id}: {e}", exc_info=True)
        try:
            await client.edit_message(chat_id, status_msg_id, f"❌ An unexpected error occurred during processing/upload: {str(e)[:100]}")
        except Exception as final_err:
             logger.error(f"Failed to send final error message: {final_err}")

    finally:
        # Clean up temporary files and directory
        temp_dir_path = None
        if original_file_path:
            if os.path.exists(original_file_path):
                try:
                    os.remove(original_file_path)
                    logger.info(f"Removed temp original file: {original_file_path}")
                except OSError as e:
                    logger.warning(f"Error removing temp original file {original_file_path}: {e}")
            temp_dir_path = os.path.dirname(original_file_path) # Get dir path for later cleanup
        if compressed_file_path and os.path.exists(compressed_file_path):
            try:
                os.remove(compressed_file_path)
                logger.info(f"Removed temp compressed file: {compressed_file_path}")
            except OSError as e:
                logger.warning(f"Error removing temp compressed file {compressed_file_path}: {e}")
            # Get dir path if not already set
            if not temp_dir_path: temp_dir_path = os.path.dirname(compressed_file_path)
        # Remove thumbnail if it exists
        thumb_to_remove = os.path.join(temp_dir_path or "", "thumb.jpg")
        if os.path.exists(thumb_to_remove):
             try: os.remove(thumb_to_remove); logger.info("Removed temp thumbnail.")
             except OSError as e: logger.warning(f"Error removing thumbnail {thumb_to_remove}: {e}")

        # Clean up the temporary directory itself if it exists and is empty
        if temp_dir_path and os.path.exists(temp_dir_path):
             try:
                 if not os.listdir(temp_dir_path):
                     os.rmdir(temp_dir_path)
                     # Restore original log message
                     logger.info(f"Removed empty temporary directory: {temp_dir_path}")
                 else:
                    logger.warning(f"Temporary directory not empty, not removing: {temp_dir_path}")
             except OSError as e:
                 logger.error(f"Error removing temporary directory {temp_dir_path}: {e}")

        # Remove user from active message tracker
        if user_id in active_status_messages:
             del active_status_messages[user_id]

        # Mark task complete and trigger next
        queue_manager.task_complete(user_id)
        logger.info(f"Task completed for user {user_id}. Triggering next process check.")
        # Schedule the next check instead of awaiting directly to prevent deep recursion
        asyncio.create_task(process_next_video(client))


# --- Main Bot Logic ---

async def main(client: TelegramClient):
    """Main function to define event handlers and run the client."""

    # --- Restored /start handler ---
    @client.on(events.NewMessage(pattern='/start'))
    async def start_command(event: events.NewMessage.Event):
        sender = await event.get_sender()
        sender_name = get_display_name(sender) if sender else "there"
        logger.info(f"Received /start command from {sender_name} (ID: {event.sender_id})")
        # Corrected welcome_message definition
        welcome_message = (
            f"👋 Hello {sender_name}!\n\n"
            f"I'm a Video Compression Bot (Telethon Edition).\n"
            f"I can reduce the size of videos and convert them to {config.DEFAULT_HEIGHT}p resolution.\n\n"
            f"Just send me a video file (up to 2GB/4GB depending on your account type), and I'll compress it.\n\n"
            f"📋 **Commands**:\n"
            f"/start - Show this welcome message\n"
            f"/help - Get help and usage information\n"
            f"/status - Check the status of your video compression\n"
            f"/cancel - Cancel your current *pending* compression task"
        )
        await event.respond(welcome_message, parse_mode='md')

    # --- Restored /help handler ---
    @client.on(events.NewMessage(pattern='/help'))
    async def help_command(event: events.NewMessage.Event):
        logger.info(f"Received /help command from {event.sender_id}")
        help_text = (
            "🎬 **Video Compression Bot Help**\n\n"
            "**How to use:**\n"
            "1. Send me any video file (as video or document).\n"
            "2. Wait for the compression to complete.\n"
            "3. Receive your compressed video.\n\n"
            f"**Compression Settings:**\n"
            f"- Target Height: {config.DEFAULT_HEIGHT}p\n"
            f"- Format: MKV\n"
            f"- Video Bitrate: ~{config.DEFAULT_VIDEO_BITRATE}\n"
            f"- Audio Bitrate: {config.DEFAULT_AUDIO_BITRATE}\n"
            f"- Preset: {config.DEFAULT_PRESET}\n"
            f"- CRF: {config.DEFAULT_CRF}\n\n"
            "**Commands:**\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/status - Check your compression status\n"
            "/cancel - Cancel the current *pending* compression task\n\n"
            "**Tips:**\n"
            "- Larger videos take significantly more time to download, process, and upload.\n"
            "- The bot processes one video at a time from the queue.\n"
            "- Status updates show progress during download/upload."
        )
        await event.respond(help_text, parse_mode='md')


    @client.on(events.NewMessage(pattern='/status'))
    async def status_command(event: events.NewMessage.Event):
        user_id = event.sender_id
        logger.info(f"Received /status command from {user_id}")
        position = queue_manager.get_position(user_id)

        if position is None:
            await event.respond("✅ You don't have any videos in the compression queue.")
        elif position == 0:
            await event.respond("⚙️ Your video is currently being processed. Please wait for status updates.")
        else:
            queue_size = queue_manager.size()
            await event.respond(f"⏳ Your video is in the queue. Position: {position+1}/{queue_size}")


    @client.on(events.NewMessage(pattern='/cancel'))
    async def cancel_command(event: events.NewMessage.Event):
        user_id = event.sender_id
        logger.info(f"Received /cancel command from {user_id}")
        # TODO: Implement cancellation of the actual ffmpeg process if running (complex)
        position = queue_manager.get_position(user_id)
        if position == 0:
             await event.respond("❌ Cannot cancel a job that is already processing. Please wait for it to finish or fail.")
             return

        removed = queue_manager.remove_from_queue(user_id)

        if removed:
             await event.respond("✅ Your pending compression task has been cancelled and removed from the queue.")
             # Optional: Update database status if implemented
        else:
            await event.respond("❌ You don't have any *pending* compression tasks to cancel.")


    @client.on(events.NewMessage(func=lambda e: e.video or (e.document and hasattr(e.document, 'mime_type') and 'video' in e.document.mime_type)))
    async def handle_video_message(event: events.NewMessage.Event):
        user_id = event.sender_id
        sender = await event.get_sender()
        sender_name = get_display_name(sender) if sender else user_id
        logger.info(f"Received video message from {sender_name} (ID: {user_id})")

        # Check queue
        if queue_manager.is_in_queue(user_id):
            position = queue_manager.get_position(user_id)
            if position == 0:
                await event.respond("⏳ You already have a video being processed. Please wait for it to complete.")
            else:
                 queue_size = queue_manager.size()
                 await event.respond(f"⏳ You already have a video in the queue (position: {position+1}/{queue_size}). Use /cancel to remove it.")
            return

        # Get video details
        media = event.video or event.document
        if not media:
             await event.respond("❌ Could not get video data from the message.")
             return

        file_size_bytes = media.size
        file_size_mb = get_file_size_mb(file_size_bytes)
        file_id = media.id # Use media ID for Telethon

        # Determine filename
        file_name = "video.mp4" # Default
        if hasattr(media, 'attributes'):
             for attr in media.attributes:
                  if isinstance(attr, DocumentAttributeFilename):
                       file_name = attr.file_name
                       break
        logger.info(f"Video details: Name='{file_name}', Size={file_size_mb:.2f} MB, ID={file_id}")

        # Check file size against a reasonable limit (e.g., 4GB, adjust as needed)
        # Telegram Desktop/Mobile clients often upload large files as Documents.
        # User accounts can typically handle up to 2GB or 4GB downloads/uploads.
        MAX_USER_FILE_SIZE_BYTES = 4 * 1024 * 1024 * 1024 # 4 GB limit (adjust if needed)
        if file_size_bytes > MAX_USER_FILE_SIZE_BYTES:
            await event.respond(
                f"❌ File too large ({file_size_mb:.1f} MB). "
                f"Maximum allowed size is {get_file_size_mb(MAX_USER_FILE_SIZE_BYTES):.0f} GB."
            )
            return

        # --- Optional: Database Interaction ---
        # db_user = get_or_create_user_async(user_id, ...) # Needs async implementation
        # job = create_compression_job_async(db_user.id, file_name, file_size_mb) # Needs async implementation
        # job_id = job.id if job else None
        job_id = None # Placeholder for now
        # ------------------------------------

        # Send acknowledgment and status message
        ack_message_text = (
            f"✅ Received: {file_name}\n"
            f"📊 Size: {file_size_mb:.2f} MB\n"
            f"⏳ Adding to compression queue..."
        )
        status_msg = await event.respond(ack_message_text)

        # Add to queue
        queue_manager.add_to_queue(user_id, {
            'event': event, # Store the event for context
            'chat_id': event.chat_id,
            'status_msg': status_msg, # Store the message object itself
            'video_file_name': file_name,
            'video_file_size': file_size_bytes,
            'job_id': job_id # Store job ID if using DB
        })

        # Update status message
        position = queue_manager.get_position(user_id)
        queue_size = queue_manager.size()
        if position == 0:
            await status_msg.edit(
                f"✅ Received: {file_name}\n"
                f"📊 Size: {file_size_mb:.2f} MB\n"
                f"⚙️ Starting compression (1/{queue_size})..."
            )
            # Start processing immediately
            asyncio.create_task(process_next_video(client))
        else:
            await status_msg.edit(
                f"✅ Received: {file_name}\n"
                f"📊 Size: {file_size_mb:.2f} MB\n"
                f"⏳ Added to queue (position: {position+1}/{queue_size})"
            )

    # Start the first processing task check if queue is not empty on startup
    if not queue_manager.is_empty():
        logger.info("Queue is not empty on startup, initiating processing check.")
        asyncio.create_task(process_next_video(client))

    logger.info("Bot event handlers are set up.")


# --- Main Execution ---

async def run_bot_async():
    """Initializes and runs the Telethon client."""
    logger.info("Initializing Telethon client...")
    if not config.API_ID or not config.API_HASH:
         logger.critical("API_ID and API_HASH are not configured in config.py or environment variables. Exiting.")
         sys.exit(1)

    # Ensure TEMP_DIR exists
    ensure_temp_dir(config.TEMP_DIR)

    client = TelegramClient(
        config.BOT_SESSION_NAME,
        config.API_ID,
        config.API_HASH,
        # device_model="MyVideoBot", # Optional: Customize device info
        # system_version="1.0",      # Optional
        # app_version="CompressorBot", # Optional
        base_logger=logger, # Use our configured logger
        # connection_retries=5 # Optional: Configure retries
    )

    try:
        logger.info("Connecting Telethon client...")
        # Start the client
        await client.start(
            phone=lambda: input("Please enter your phone number (with country code): "),
            password=lambda: input("Please enter your 2FA password (if any): "),
            code_callback=lambda: input("Please enter the code you received: ")
        )
        logger.info("Client started successfully.")

        # Get info about the logged-in user (itself)
        me = await client.get_me()
        logger.info(f"Logged in as: {get_display_name(me)} (ID: {me.id})")

        # Setup event handlers
        await main(client)

        # Run until disconnected
        logger.info("Bot is running. Waiting for events...")
        await client.run_until_disconnected()

    except SessionPasswordNeededError:
        logger.error("Two-step verification (2FA) is enabled, but no password was provided or it was incorrect.")
    except AuthKeyError:
         logger.error("Authentication key error. The session file might be corrupted. Please delete the .session file and try again.")
    except UserDeactivatedBanError:
         logger.error("The user account used for the bot has been deactivated or banned.")
    except Exception as e:
        logger.critical(f"An error occurred during client startup or runtime: {e}", exc_info=True)
    finally:
        if client.is_connected():
            logger.info("Disconnecting client...")
            await client.disconnect()
            logger.info("Client disconnected.")

def run_bot():
    """Synchronous wrapper to run the async bot logic."""
    try:
        # Use asyncio.run() in Python 3.7+
        asyncio.run(run_bot_async())
        logger.info("Bot finished running.")
        return "Bot finished running."
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt).")
        return "Bot stopped by user."
    except Exception as e:
        logger.critical(f"Critical error running the bot's async loop: {e}", exc_info=True)
        return f"Critical Error: {e}"

# Note: The run_simple_bot.py script should now call this run_bot() function.

