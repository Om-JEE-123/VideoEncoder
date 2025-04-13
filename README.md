# Telegram Video Compression Bot

A Telegram bot that compresses videos to 480p and outputs them in MKV format.

## Features

- Compresses any video to 480p resolution
- Converts videos to MKV (Matroska) format
- No file size limits on input videos
- Outputs detailed compression statistics
- Processes videos from groups/channels when forwarded
- Simple user interface with easy-to-understand commands

## Commands

- `/start` - Start the bot and show welcome message
- `/help` - Display help information
- `/status` - Check your video compression status (when using queue_manager)
- `/cancel` - Cancel your current compression task (when using queue_manager)

## Implementation Details

Two implementation options are provided:

1. **simple_bot.py** - A standalone implementation using curl and subprocess for API calls
   - Doesn't require any Python Telegram Bot libraries
   - Simpler to maintain with fewer dependencies
   - Handles all basic compression functionality

2. **Full featured implementation** - Uses python-telegram-bot library
   - bot.py - Main bot logic and command handlers
   - video_processor.py - Video processing functionality
   - queue_manager.py - Queue system for handling multiple requests
   - utils.py - Utility functions

## Requirements

- Python 3.8+
- FFmpeg (for video compression)
- curl (for simple_bot.py)
- python-telegram-bot (for full implementation)
- ffmpeg-python (for full implementation)

## Configuration

Set your Telegram Bot Token as an environment variable:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

## Running the Bot

For the simple implementation:

```
python simple_bot.py
```

For the full featured implementation:

```
python main.py
```

## License

MIT