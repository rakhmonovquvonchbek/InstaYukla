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
import uuid
import time

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        # Don't create the loader here anymore
        pass
    
    def create_fresh_loader(self):
        """Create a fresh instaloader instance for each request"""
        # Rotate between different user agents
        user_agents = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
        ]
        
        import random
        selected_ua = random.choice(user_agents)
        
        loader = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            user_agent=selected_ua
        )
        
        # Try to login, but don't fail if it doesn't work
        instagram_username = os.getenv('INSTAGRAM_USERNAME')
        instagram_password = os.getenv('INSTAGRAM_PASSWORD')
        
        print(f"DEBUG: Using User Agent: {selected_ua[:50]}...")
        print(f"DEBUG: Environment check - Username exists: {instagram_username is not None}")
        
        if instagram_username and instagram_password:
            try:
                # Try login with retry and delays
                for attempt in range(2):  # Reduced attempts to avoid triggering more blocks
                    try:
                        print(f"DEBUG: Login attempt {attempt + 1}")
                        loader.login(instagram_username, instagram_password)
                        print(f"DEBUG: Successfully logged in as {instagram_username}")
                        break
                    except Exception as login_error:
                        print(f"DEBUG: Login attempt {attempt + 1} failed: {login_error}")
                        if attempt < 1:
                            time.sleep(5)  # Longer delay between attempts
                        else:
                            print("DEBUG: Login failed, continuing without authentication")
            except Exception as e:
                print(f"DEBUG: Login setup failed: {e}")
        else:
            print("DEBUG: No Instagram credentials provided")
        
        return loader
    
    def extract_shortcode(self, url):
        """Extract Instagram post shortcode from URL"""
        patterns = [
            r'instagram\.com/p/([A-Za-z0-9_-]+)',
            r'instagram\.com/reel/([A-Za-z0-9_-]+)',
            r'instagram\.com/tv/([A-Za-z0-9_-]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def extract_username_from_story_url(self, url):
        """Extract username from Instagram story URL"""
        match = re.search(r'instagram\.com/stories/([^/]+)', url)
        return match.group(1) if match else None
    
    async def download_post(self, url, temp_dir):
        """Download Instagram post/reel"""
        try:
            shortcode = self.extract_shortcode(url)
            if not shortcode:
                return None, "Invalid Instagram URL"
            
            print(f"\n=== DEBUG: Starting download for shortcode: {shortcode} ===")
            print(f"DEBUG: Temp directory: {temp_dir}")
            print(f"DEBUG: Files in temp_dir BEFORE download: {os.listdir(temp_dir)}")
            
            # Create a fresh loader instance for this request
            loader = self.create_fresh_loader()
            
            # Create a unique subdirectory for this specific request
            unique_subdir = os.path.join(temp_dir, f"download_{uuid.uuid4().hex[:8]}")
            os.makedirs(unique_subdir, exist_ok=True)
            print(f"DEBUG: Created unique subdir: {unique_subdir}")
            
            # Retry mechanism for authentication issues
            max_retries = 5  # Increased retries
            for attempt in range(max_retries):
                try:
                    # Add delay between attempts to avoid rate limiting
                    if attempt > 0:
                        wait_time = attempt * 3  # 3, 6, 9, 12 seconds
                        print(f"DEBUG: Waiting {wait_time} seconds before retry...")
                        await asyncio.sleep(wait_time)
                    
                    post = instaloader.Post.from_shortcode(loader.context, shortcode)
                    print(f"DEBUG: Post object created successfully")
                    print(f"DEBUG: Post has {post.mediacount} media items")
                    
                    # Download to the unique subdirectory
                    loader.dirname_pattern = unique_subdir
                    print(f"DEBUG: About to download to: {unique_subdir}")
                    loader.download_post(post, target=unique_subdir)
                    print(f"DEBUG: Download completed")
                    
                    # Check what was downloaded
                    print(f"DEBUG: Files in unique_subdir after download: {os.listdir(unique_subdir)}")
                    print(f"DEBUG: Files in temp_dir after download: {os.listdir(temp_dir)}")
                    
                    # Get ONLY files from our unique subdirectory
                    files = []
                    for file in os.listdir(unique_subdir):
                        full_path = os.path.join(unique_subdir, file)
                        print(f"DEBUG: Checking file: {file}")
                        if file.endswith(('.jpg', '.jpeg', '.png', '.mp4')):
                            files.append(full_path)
                            print(f"DEBUG: Added media file: {file}")
                    
                    # Sort files to maintain consistent order
                    files.sort()
                    
                    print(f"DEBUG: Final files list: {[os.path.basename(f) for f in files]}")
                    print(f"=== DEBUG: Returning {len(files)} files ===\n")
                    
                    return files, None
                    
                except instaloader.exceptions.ConnectionException as e:
                    print(f"DEBUG: Connection exception: {e}")
                    if "401" in str(e) and attempt < max_retries - 1:
                        print(f"DEBUG: 401 error, retrying... (attempt {attempt + 1})")
                        await asyncio.sleep(5)  # Longer wait
                        loader = self.create_fresh_loader()
                        continue
                    elif "429" in str(e):
                        return None, "Instagram rate limit reached. Please wait 10-15 minutes before trying again."
                    else:
                        return None, "Instagram temporarily blocked access. This is common on cloud servers. Try again in a few minutes."
                except Exception as e:
                    print(f"DEBUG: Exception during download: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        loader = self.create_fresh_loader()
                        continue
                    else:
                        raise e
            
        except Exception as e:
            print(f"DEBUG: Outer exception: {e}")
            error_msg = str(e)
            if "401" in error_msg:
                return None, "Instagram authentication failed. The content might be private or temporarily unavailable."
            elif "404" in error_msg:
                return None, "Post not found. The link might be broken or the post was deleted."
            elif "429" in error_msg:
                return None, "Too many requests. Please wait a few minutes before trying again."
            else:
                return None, f"Error downloading: {error_msg}"

# Initialize downloader
downloader = InstagramDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
🤖 **Instagram Downloader Bot**

Send me an Instagram URL and I'll download it for you!

Supported formats:
📸 Posts (photos)
🎥 Videos/Reels
📚 Carousels (multiple photos/videos)

Just paste the Instagram link and I'll handle the rest!

Example:
`https://www.instagram.com/p/ABC123/`
`https://www.instagram.com/reel/XYZ789/`
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

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

**Note:** Stories and private content require special permissions.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram URLs"""
    message_text = update.message.text
    
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
    processing_msg = await update.message.reply_text("⏳ Processing your request...")
    
    try:
        # Create temporary directory - this creates a fresh, empty directory each time
        with tempfile.TemporaryDirectory() as temp_dir:
            files, error = await downloader.download_post(url_found, temp_dir)
            
            if error:
                await processing_msg.edit_text(f"❌ {error}")
                return
            
            if not files:
                await processing_msg.edit_text("❌ No media files found!")
                return
            
            await processing_msg.edit_text(f"📁 Found {len(files)} file(s). Uploading...")
            
            # Send files
            for i, file_path in enumerate(files):
                try:
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                        with open(file_path, 'rb') as photo:
                            await update.message.reply_photo(photo)
                    elif file_path.lower().endswith('.mp4'):
                        with open(file_path, 'rb') as video:
                            await update.message.reply_video(video)
                except Exception as e:
                    logger.error(f"Error sending file {file_path}: {e}")
            
            await processing_msg.delete()
            await update.message.reply_text("✅ Download completed!")
            
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await processing_msg.edit_text(f"❌ An error occurred: {str(e)}")

def main():
    """Main function to run the bot"""
    # Replace 'YOUR_BOT_TOKEN' with your actual bot token from BotFather
    BOT_TOKEN = "8361203216:AAGkbDrgzyC-2J-pzxBSJuwMwsNmgqVsY34"
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("❌ Please set your bot token!")
        print("1. Message @BotFather on Telegram")
        print("2. Create a new bot with /newbot")
        print("3. Copy the token and replace 'YOUR_BOT_TOKEN' in the code")
        return
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    print("🤖 Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()