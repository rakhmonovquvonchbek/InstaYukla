import os
import re
import requests
import instaloader
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
from urllib.parse import urlparse
import tempfile
import logging
import time
import random
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        self.session_cache = {}
        self.last_request_time = {}
        self.user_agents = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Android 12; Mobile; rv:91.0) Gecko/91.0 Firefox/91.0',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]
    
    def create_fresh_loader(self, user_agent_index=0):
        """Create a fresh instaloader instance with rotating user agents"""
        try:
            # Create session directory
            session_dir = f"/tmp/session_{user_agent_index}"
            os.makedirs(session_dir, exist_ok=True)
            
            loader = instaloader.Instaloader(
                download_pictures=True,
                download_videos=True,
                download_video_thumbnails=False,
                compress_json=False,
                post_metadata_txt_pattern="",
                dirname_pattern=session_dir,
                filename_pattern="{shortcode}",
                request_timeout=30,
                max_connection_attempts=3,
                sleep=True,  # Enable sleep between requests
                user_agent=self.user_agents[user_agent_index % len(self.user_agents)]
            )
            
            # Set custom headers to look more like a real browser
            if hasattr(loader.context, '_session'):
                loader.context._session.headers.update({
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                })
            
            return loader, session_dir
        except Exception as e:
            logger.error(f"Error creating loader: {e}")
            return None, None
    
    def smart_delay(self, base_delay=2):
        """Add smart delays between requests"""
        # Random delay between base_delay and base_delay*2
        delay = random.uniform(base_delay, base_delay * 2)
        logger.info(f"Waiting {delay:.1f} seconds...")
        time.sleep(delay)
    
    def login_with_retry(self, loader, max_attempts=5):
        """Login with multiple retry strategies"""
        username = os.getenv('INSTAGRAM_USERNAME')
        password = os.getenv('INSTAGRAM_PASSWORD')
        
        if not username or not password:
            logger.error("Instagram credentials not found in environment variables")
            return False
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"Login attempt {attempt + 1}/{max_attempts}")
                
                # Progressive delay - longer delays for later attempts
                if attempt > 0:
                    delay = min(30 * (2 ** attempt), 300)  # Max 5 minutes
                    logger.info(f"Waiting {delay} seconds before retry...")
                    time.sleep(delay)
                
                # Try to login
                loader.login(username, password)
                logger.info("Login successful!")
                return True
                
            except instaloader.exceptions.BadCredentialsException:
                logger.error("Bad credentials - check username/password")
                return False
                
            except instaloader.exceptions.TwoFactorAuthRequiredException:
                logger.error("Two-factor authentication required - please disable it temporarily")
                return False
                
            except instaloader.exceptions.ConnectionException as e:
                logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
                if "429" in str(e) or "rate limit" in str(e).lower():
                    # Rate limited - wait longer
                    wait_time = min(60 * (attempt + 1), 600)  # Up to 10 minutes
                    logger.info(f"Rate limited, waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                elif "suspicious" in str(e).lower() or "blocked" in str(e).lower():
                    logger.warning("Suspicious activity detected, using longer delay...")
                    time.sleep(120)  # 2 minutes
                
            except Exception as e:
                logger.error(f"Unexpected error during login: {e}")
                
        logger.error("All login attempts failed")
        return False
    
    async def download_instagram_post(self, url, max_retries=3):
        """Download Instagram post with enhanced error handling"""
        try:
            # Extract shortcode from URL
            shortcode_match = re.search(r'/p/([A-Za-z0-9_-]+)', url)
            if not shortcode_match:
                shortcode_match = re.search(r'/reel/([A-Za-z0-9_-]+)', url)
            
            if not shortcode_match:
                return None, "❌ Invalid Instagram URL format"
            
            shortcode = shortcode_match.group(1)
            logger.info(f"Processing shortcode: {shortcode}")
            
            # Try with different user agents
            for retry in range(max_retries):
                try:
                    logger.info(f"Attempt {retry + 1}/{max_retries}")
                    
                    # Use different user agent for each retry
                    loader, session_dir = self.create_fresh_loader(retry)
                    if not loader:
                        continue
                    
                    # Smart delay between attempts
                    if retry > 0:
                        self.smart_delay(5 + retry * 5)
                    
                    # Try to login
                    if not self.login_with_retry(loader, max_attempts=2):
                        logger.warning(f"Login failed on attempt {retry + 1}")
                        if retry < max_retries - 1:
                            continue
                        else:
                            return None, "❌ Instagram login failed after all attempts. Try again in 10-15 minutes."
                    
                    # Add delay after successful login
                    self.smart_delay(3)
                    
                    # Get post
                    logger.info("Fetching post...")
                    post = instaloader.Post.from_shortcode(loader.context, shortcode)
                    
                    # Check if it's a video or image
                    if post.is_video:
                        logger.info("Downloading video...")
                        video_url = post.video_url
                        response = requests.get(video_url, stream=True, timeout=30)
                        response.raise_for_status()
                        
                        # Save to temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
                            for chunk in response.iter_content(chunk_size=8192):
                                temp_file.write(chunk)
                            temp_path = temp_file.name
                        
                        return temp_path, "video"
                    else:
                        logger.info("Downloading image...")
                        image_url = post.url
                        response = requests.get(image_url, timeout=30)
                        response.raise_for_status()
                        
                        # Save to temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                            temp_file.write(response.content)
                            temp_path = temp_file.name
                        
                        return temp_path, "photo"
                        
                except instaloader.exceptions.LoginRequiredException:
                    logger.warning("Login required - retrying with fresh session")
                    continue
                    
                except instaloader.exceptions.PrivateProfileNotFollowedException:
                    return None, "❌ This is a private account. Cannot download content."
                    
                except instaloader.exceptions.PostUnavailableException:
                    return None, "❌ Post not found or has been deleted."
                    
                except instaloader.exceptions.ConnectionException as e:
                    logger.warning(f"Connection error: {e}")
                    if "429" in str(e) or "rate limit" in str(e).lower():
                        wait_time = 60 * (retry + 1)
                        logger.info(f"Rate limited, waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                    elif "blocked" in str(e).lower() or "suspicious" in str(e).lower():
                        wait_time = 120 + (retry * 60)
                        logger.info(f"Blocked detected, waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                    continue
                    
                except Exception as e:
                    logger.error(f"Attempt {retry + 1} failed: {e}")
                    if retry < max_retries - 1:
                        self.smart_delay(10 + retry * 10)
                        continue
                    else:
                        return None, f"❌ Download failed after {max_retries} attempts: {str(e)}"
            
            return None, "❌ Instagram temporarily blocked access. This is common on cloud servers. Try again in 10-15 minutes."
            
        except Exception as e:
            logger.error(f"Unexpected error in download_instagram_post: {e}")
            return None, f"❌ Unexpected error: {str(e)}"

# Initialize downloader
downloader = InstagramDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_msg = """
🤖 **Instagram Downloader Bot**

Send me an Instagram post URL and I'll download it for you!

📝 **Supported formats:**
• https://www.instagram.com/p/ABC123/
• https://www.instagram.com/reel/ABC123/

⚠️ **Note:** Due to Instagram's restrictions on cloud servers, downloads may sometimes fail. If you get a "temporarily blocked" message, please wait 10-15 minutes and try again.

Just send me a link to get started! 🚀
    """
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def download_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram URL messages"""
    message_text = update.message.text.strip()
    
    # Check if message contains Instagram URL
    instagram_patterns = [
        r'https?://(?:www\.)?instagram\.com/p/[A-Za-z0-9_-]+',
        r'https?://(?:www\.)?instagram\.com/reel/[A-Za-z0-9_-]+',
        r'https?://(?:www\.)?instagram\.com/tv/[A-Za-z0-9_-]+'
    ]
    
    url_found = None
    for pattern in instagram_patterns:
        match = re.search(pattern, message_text)
        if match:
            url_found = match.group(0)
            break
    
    if not url_found:
        await update.message.reply_text(
            "❌ Please send a valid Instagram URL!\n\n"
            "Example: https://www.instagram.com/p/ABC123/"
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text("🔄 Processing your request... This may take a few minutes.")
    
    try:
        # Download the post
        file_path, file_type = await downloader.download_instagram_post(url_found)
        
        if file_path and file_type:
            # Send the file
            if file_type == "video":
                with open(file_path, 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption="📹 Here's your Instagram video!"
                    )
            elif file_type == "photo":
                with open(file_path, 'rb') as photo_file:
                    await update.message.reply_photo(
                        photo=photo_file,
                        caption="📸 Here's your Instagram photo!"
                    )
            
            # Clean up temporary file
            try:
                os.unlink(file_path)
            except:
                pass
                
            # Delete processing message
            await processing_msg.delete()
            await update.message.reply_text("✅ Download completed!")
            
        else:
            # Error occurred
            error_msg = file_type if file_type else "❌ Failed to download the post."
            await processing_msg.edit_text(error_msg)
            
    except Exception as e:
        logger.error(f"Error in download_instagram: {e}")
        await processing_msg.edit_text(f"❌ An error occurred: {str(e)}")

def main():
    """Main function to run the bot"""
    # Get bot token from environment variable
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        logger.error("Available environment variables:")
        for key in os.environ.keys():
            if 'TOKEN' in key.upper():
                logger.error(f"  {key}")
        return
    
    # Verify Instagram credentials are available
    instagram_username = os.getenv('INSTAGRAM_USERNAME')
    instagram_password = os.getenv('INSTAGRAM_PASSWORD')
    
    logger.info("=== ENVIRONMENT CHECK ===")
    logger.info(f"Bot Token: {'✅ Found' if bot_token else '❌ Missing'}")
    logger.info(f"Instagram Username: {'✅ Found' if instagram_username else '❌ Missing'} - {instagram_username}")
    logger.info(f"Instagram Password: {'✅ Found' if instagram_password else '❌ Missing'}")
    logger.info("========================")
    
    if not instagram_username or not instagram_password:
        logger.error("Instagram credentials not found in environment variables")
        logger.error("Make sure INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD are set in Railway")
        return
    
    logger.info("Starting Instagram Downloader Bot...")
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_instagram))
    
    # Start the bot
    application.run_polling()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
🔗 **How to use:**

1. Copy any Instagram post/reel URL
2. Paste it here  
3. Wait for download to complete
4. Receive your media files!

**Supported URLs:**
• instagram.com/p/...
• instagram.com/reel/...
• instagram.com/tv/...

**Note:** Due to Instagram's restrictions on cloud servers, some downloads may fail. If you get a "temporarily blocked" message, wait 10-15 minutes and try again.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

if __name__ == '__main__':
    main()