import os
import sys
import logging
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, TypeHandler
from telegram import Update

if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import config, database, bot

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
)
logger = logging.getLogger(__name__)

async def init():
    """Initializes the application (e.g., database)."""
    await database.init_db()
    logger.info("Database initialized.")

def main():
    """Starts the Telegram bot in polling mode."""
    if not config.BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set!")
        return

    logger.info(f"Starting {config.BOT_NAME} v{config.BOT_VERSION}...")

    # Build the application
    application = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Handlers
    # 1. Check whitelist first for all incoming updates
    application.add_handler(TypeHandler(Update, bot.check_whitelist), group=-1)
    
    # 2. Command handlers
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CommandHandler("help", bot.start_command))
    application.add_handler(CommandHandler("estado", bot.status_command))
    application.add_handler(CommandHandler("limite", bot.limit_command))
    application.add_handler(CommandHandler("id", bot.id_command))
    application.add_handler(CommandHandler("audio", bot.audio_command))
    application.add_handler(CommandHandler("cortar", bot.cortar_command))
    application.add_handler(CommandHandler("nivel", bot.upgrade_command))
    application.add_handler(CommandHandler("subir_nivel", bot.upgrade_command))
    application.add_handler(CommandHandler("cancelar", bot.cancel_command))
    
    # 3. Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Run the application (this blocks until stopped)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # Initialize async resources before starting the bot loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init())
    
    main()
