import os
from dotenv import load_dotenv

load_dotenv()

# App Configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_IDS = [int(chat_id) for chat_id in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if chat_id]
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD")
ACCESS_ROOT_PASSWORD = os.getenv("ACCESS_ROOT_PASSWORD")
DAILY_DOWNLOAD_LIMIT = int(os.getenv("DAILY_DOWNLOAD_LIMIT", "5"))
LIMIT_TIMEZONE = os.getenv("LIMIT_TIMEZONE", "America/Mexico_City")
USER_DOWNLOAD_COOLDOWN_SECONDS = int(os.getenv("USER_DOWNLOAD_COOLDOWN_SECONDS", "10"))
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "1"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "300"))

# Database & Paths Configuration
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "data/bot.db")
TEMP_DOWNLOAD_DIR = os.getenv("TEMP_DOWNLOAD_DIR", "tmp/files")
SQL_INIT_PATH = "sql/init.sql"

# Meta
BOT_NAME = os.getenv("BOT_NAME", "telegram-video-bot")
BOT_VERSION = os.getenv("BOT_VERSION", "0.1.0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Status Constants
STATUS_PENDING = "PENDING"
STATUS_DOWNLOADING = "DOWNLOADING"
STATUS_DOWNLOADED = "DOWNLOADED"
STATUS_SENT = "SENT"
STATUS_TOO_LARGE = "TOO_LARGE"
STATUS_ERROR = "ERROR"
STATUS_UNAUTHORIZED = "UNAUTHORIZED"
