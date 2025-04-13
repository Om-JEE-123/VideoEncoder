#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Simple wrapper to launch the simpler bot implementation"""

import os
import sys
import logging
import subprocess
import config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Check for API_ID and API_HASH (for Telethon)
if not config.API_ID or not config.API_HASH:
    logger.error("API_ID and/or API_HASH environment variables are not set.")
    logger.info("Please get them from my.telegram.org and set them as environment variables.")
    sys.exit(1)
else:
    logger.info("API_ID and API_HASH found.")

# Check for ffmpeg
try:
    # Use check=True to raise an error if ffmpeg is not found
    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    logger.info("FFmpeg is installed and ready.")
except (subprocess.SubprocessError, FileNotFoundError):
    logger.error("FFmpeg is not installed or not in the PATH.")
    logger.info("Please install FFmpeg before running the bot.")
    sys.exit(1)

# Run the bot
if __name__ == "__main__":
    logger.info("Starting Telegram Video Compression Bot (Telethon Edition)...")
    try:
        # Import from the refactored telegrambot.py
        from telegrambot import run_bot
        # Run the main bot function (which now handles client initialization)
        run_bot()
    except KeyboardInterrupt:
        # run_bot() now handles KeyboardInterrupt, so this might be redundant
        logger.info("Shutdown requested by user (KeyboardInterrupt detected in runner).")
    except Exception as e:
        logger.critical(f"Critical error in runner: {e}")
        sys.exit(1)