import logging
import os
import subprocess
import threading
from flask import Flask, render_template_string

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Set up the app
app = Flask(__name__)

@app.route('/')
def index():
    # Check if bot token is available
    has_token = bool(os.environ.get('TELEGRAM_BOT_TOKEN'))
    bot_status = "Ready to start" if has_token else "Missing Telegram Bot Token"
    
    # Check if ffmpeg is installed
    ffmpeg_available = False
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        ffmpeg_available = True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    html = f"""
    <!DOCTYPE html>
    <html data-bs-theme="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Telegram Video Compression Bot</title>
        <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card shadow mb-4">
                        <div class="card-header">
                            <h3 class="mb-0">Telegram Video Compression Bot</h3>
                        </div>
                        <div class="card-body">
                            <p class="lead">This is a Telegram bot that compresses videos to 480p and reduces file size.</p>
                            <p>Bot Status: <span class="badge bg-{'success' if has_token else 'danger'}">{bot_status}</span></p>
                            <p>FFmpeg Status: <span class="badge bg-{'success' if ffmpeg_available else 'danger'}">{'Available' if ffmpeg_available else 'Not Installed'}</span></p>
                            
                            <h5 class="mt-4">Features:</h5>
                            <ul>
                                <li>Compresses any video to 480p resolution</li>
                                <li>Converts to MKV (Matroska) format</li>
                                <li>No file size limits on input videos</li>
                                <li>Outputs detailed compression statistics</li>
                                <li>Processes videos from groups/channels when forwarded</li>
                            </ul>
                            
                            <h5 class="mt-4">How to use:</h5>
                            <p>1. Run the bot on a separate terminal window with: <code>python run_simple_bot.py</code></p>
                            <p>2. Search for your bot on Telegram (using the bot username)</p>
                            <p>3. Send any video file to compress</p>
                            
                            <div class="alert alert-info mt-4">
                                <p class="mb-0"><strong>Bot Commands:</strong></p>
                                <ul class="mb-0">
                                    <li><code>/start</code> - Start the bot</li>
                                    <li><code>/help</code> - Get usage information</li>
                                </ul>
                            </div>
                            
                            <div class="alert alert-warning mt-4">
                                <h5>Running the Bot:</h5>
                                <p>To run the bot, use:</p>
                                <pre class="bg-dark text-light p-3 rounded">python run_simple_bot.py</pre>
                                <p>Make sure you have set your Telegram Bot Token:</p>
                                <pre class="bg-dark text-light p-3 rounded">export TELEGRAM_BOT_TOKEN=your_token_here</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/start_bot')
def start_bot_route():
    """API endpoint to start the bot"""
    try:
        # Run the bot in a subprocess instead of importing directly
        subprocess.Popen(['python', 'run_simple_bot.py'])
        return "Bot started successfully. Check your terminal for output logs."
    except Exception as e:
        return f"Error starting bot: {e}"

if __name__ == '__main__':
    # Start the Flask app
    logger.info("Starting web server. To run the bot, use 'python run_simple_bot.py'")
    app.run(host='0.0.0.0', port=5000)
