import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_installations():
    """Check what packages are installed"""
    logger.info("=== CHECKING INSTALLATIONS ===")
    
    # Check Python version
    logger.info(f"Python version: {sys.version}")
    
    # Check if packages are available
    packages_to_check = [
        'telegram',
        'instagrapi', 
        'requests'
    ]
    
    for package in packages_to_check:
        try:
            __import__(package)
            logger.info(f"✅ {package} - INSTALLED")
        except ImportError as e:
            logger.error(f"❌ {package} - NOT INSTALLED: {e}")
    
    # List all installed packages
    try:
        import pkg_resources
        installed_packages = [d.project_name for d in pkg_resources.working_set]
        logger.info(f"All installed packages: {sorted(installed_packages)}")
    except:
        logger.info("Could not list all packages")
    
    logger.info("==============================")

def main():
    """Main function with installation check"""
    # Check installations first
    check_installations()
    
    # Try to import instagrapi specifically
    try:
        from instagrapi import Client
        logger.info("🎉 SUCCESS: instagrapi imported successfully!")
        
        # Test creating a client
        client = Client()
        logger.info("🎉 SUCCESS: instagrapi Client created successfully!")
        
    except ImportError as e:
        logger.error(f"❌ FAILED: Cannot import instagrapi: {e}")
        logger.error("This means instagrapi is not installed properly.")
        return
    except Exception as e:
        logger.error(f"❌ FAILED: Error creating instagrapi client: {e}")
        return
    
    # Check Telegram bot token
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    logger.info(f"Telegram Token: {'✅ Found' if token else '❌ Missing'}")
    
    # Check Instagram credentials
    username = os.getenv('INSTAGRAM_USERNAME')
    password = os.getenv('INSTAGRAM_PASSWORD')
    logger.info(f"Instagram Username: {'✅ Found' if username else '❌ Missing'}")
    logger.info(f"Instagram Password: {'✅ Found' if password else '❌ Missing'}")
    
    if not token:
        logger.error("Cannot start bot without TELEGRAM_BOT_TOKEN")
        return
    
    logger.info("🚀 All checks passed! Starting actual bot...")
    
    # Import telegram modules
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🎉 **Bot is working!**\n\n"
            "✅ instagrapi is installed and working\n"
            "✅ Telegram bot is connected\n\n"
            "Send me an Instagram URL to test downloading!",
            parse_mode='Markdown'
        )
    
    async def test_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"Received: {update.message.text}\n\n"
            "instagrapi is working! Ready to implement download logic."
        )
    
    # Create application
    app = Application.builder().token(token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, test_message))
    
    # Start polling
    app.run_polling()

if __name__ == '__main__':
    main()