import os

# Telegram Bot Settings
# TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") # No longer needed for user bot

# Telegram API Credentials (User Bot - Telethon)
API_ID = int(os.getenv("API_ID", 0)) # Get from my.telegram.org, MUST be integer
API_HASH = os.getenv("API_HASH", "")  # Get from my.telegram.org
BOT_SESSION_NAME = os.getenv("BOT_SESSION_NAME", "bot_session") # Name for the .session file

# Video Processing Settings
MAX_VIDEO_SIZE_MB = 2048  # Increased limit for large files
DEFAULT_HEIGHT = 480    # Target height for compression
DEFAULT_VIDEO_BITRATE = "2000k"  # Increased for better quality with large files
DEFAULT_AUDIO_BITRATE = "192k"
DEFAULT_CRF = 28
DEFAULT_PRESET = "fast"  # Changed to faster preset for large files

# Timeout Settings
DOWNLOAD_TIMEOUT = 3600  # 1 hour for large downloads
PROCESSING_TIMEOUT = 7200  # 2 hours for processing
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for streaming

# Path Settings
TEMP_DIR = "temp"
