import os
import re
import tempfile
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from instagrapi import Client
from instagrapi.exceptions import *

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        self.client = None
        self.logged_in = False
    
    def login(self):
        """Login to Instagram"""
        if self.logged_in:
            return True
            
        try:
            username = os.getenv('INSTAGRAM_USERNAME')
            password = os.getenv('INSTAGRAM_PASSWORD')
            
            if not username or not password:
                logger.error("Instagram credentials not found")
                return False
            
            self.client = Client()
            
            # Try to login
            logger.info(f"Attempting to login as {username}")
            self.client.login(username, password)
            
            self.logged_in = True
            logger.info("Successfully logged in to Instagram")
            return True
            
        except BadCredentialsException:
            logger.error("Bad Instagram credentials")
            return False
        except TwoFactorRequired:
            logger.error("Two-factor authentication required - please disable it temporarily")
            return False
        except ChallengeRequired:
            logger.error("Challenge required - Instagram wants to verify the account")
            return False
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def extract_media_id(self, url):
        """Extract media ID from Instagram URL"""
        try:
            if not self.client:
                return None
            return self.client.media_pk_from_url(url)
        except Exception as e:
            logger.error(f"Error extracting media ID: {e}")
            return None
    
    async def download_instagram_post(self, url):
        """Download Instagram post"""
        try:
            # Login if not already logged in
            if not self.login():
                return None, "❌ Instagram login failed. Check your credentials."
            
            # Extract media ID
            media_pk = self.extract_media_id(url)
            if not media_pk:
                return None, "❌ Invalid Instagram URL or could not extract media ID."
            
            logger.info(f"Processing media ID: {media_pk}")
            
            # Get media info
            media_info = self.client.media_info(media_pk)
            
            if media_info.media_type == 2:  # Video
                logger.info("Downloading video...")
                file_path = self.client.video_download(media_pk)
                return file_path, "video"
            else:  # Photo
                logger.info("Downloading photo...")
                file_path = self.client.photo_download(media_pk)  
                return file_path, "photo"
                
        except LoginRequired:
            logger.error("Login required")
            self.logged_in = False
            return None, "❌ Instagram login expired. Try again."
        except MediaNotFound:
            return None, "❌ Post not found. It might be deleted or private."
        except PrivateError:
            return None, "❌ This is a private account. Cannot download content."
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None, f"❌ Download failed: {str(e)}"

# Initialize downloader
downloader = InstagramDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    await update.message.reply_text(
        "🤖 **Instagram Downloader Bot**\n\n"
        "Send me an Instagram post/reel URL and I'll download it!\n\n"
        "**Supported:**\n"
        "• instagram.com/p/...\n"
        "• instagram.com/reel/...\n"
        "• instagram.com/tv/...\n\n"
        "**Note:** This bot requires Instagram login and works with public posts.",
        parse_mode='Markdown'
    )

async def handle_instagram_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram URLs"""
    text = update.message.text.strip()
    
    # Check if it's an Instagram URL
    if not re.search(r'instagram\.com/(p|reel|tv)/', text):
        await update.message.reply_text("❌ Please send a valid Instagram post, reel, or TV URL.")
        return
    
    # Send processing message
    msg = await update.message.reply_text("⏳ Processing your request...")
    
    try:
        # Download the post
        file_path, file_type = await downloader.download_instagram_post(text)
        
        if file_path and os.path.exists(file_path):
            # Send the downloaded file
            if file_type == "video":
                with open(file_path, 'rb') as video:
                    await update.message.reply_video(video, caption="📹 Here's your video!")
            else:
                with open(file_path, 'rb') as photo:
                    await update.message.reply_photo(photo, caption="📸 Here's your photo!")
            
            # Clean up
            try:
                os.unlink(file_path)
            except:
                pass
                
            await msg.delete()
            await update.message.reply_text("✅ Download completed!")
        else:
            await msg.edit_text(f"{file_type}")
            
    except Exception as e:
        logger.error(f"Handler error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)}")

def main():
    """Main function"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    instagram_username = os.getenv('INSTAGRAM_USERNAME')
    instagram_password = os.getenv('INSTAGRAM_PASSWORD')
    
    logger.info("=== INSTAGRAM DOWNLOADER BOT ===")
    logger.info(f"Telegram Token: {'✅ Found' if token else '❌ Missing'}")
    logger.info(f"Instagram Username: {'✅ Found' if instagram_username else '❌ Missing'} - {instagram_username}")
    logger.info(f"Instagram Password: {'✅ Found' if instagram_password else '❌ Missing'}")
    logger.info("===============================")
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        return
        
    if not instagram_username or not instagram_password:
        logger.error("Instagram credentials not found!")
        return
    
    logger.info("🚀 Starting bot...")
    
    # Create application
    app = Application.builder().token(token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instagram_url))
    
    # Start polling
    app.run_polling()

if __name__ == '__main__':
    main()