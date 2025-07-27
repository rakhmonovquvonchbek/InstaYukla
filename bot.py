import os
import re
import requests
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import tempfile
import logging
import time
import random
from urllib.parse import quote

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.user_agents = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Android 12; Mobile; rv:91.0) Gecko/91.0 Firefox/91.0',
            'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36'
        ]
        
    def get_headers(self):
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def extract_shortcode(self, url):
        """Extract shortcode from Instagram URL"""
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
    
    async def download_with_third_party_api(self, url):
        """Try downloading using third-party Instagram downloaders"""
        shortcode = self.extract_shortcode(url)
        if not shortcode:
            return None, "Invalid Instagram URL"
        
        # Method 1: Try Instagram's public embed API
        try:
            logger.info("Trying Instagram embed API...")
            embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
            
            headers = self.get_headers()
            response = self.session.get(embed_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                # Look for media URLs in the embed response
                content = response.text
                
                # Search for video URLs
                video_patterns = [
                    r'"video_url":"([^"]+)"',
                    r'video_url&quot;:&quot;([^&]+)&quot;',
                    r'videoUrl":"([^"]+)"'
                ]
                
                for pattern in video_patterns:
                    match = re.search(pattern, content)
                    if match:
                        video_url = match.group(1).replace('\\u0026', '&').replace('\/', '/')
                        logger.info(f"Found video URL: {video_url[:50]}...")
                        return await self.download_media(video_url, 'mp4')
                
                # Search for image URLs
                image_patterns = [
                    r'"display_url":"([^"]+)"',
                    r'display_url&quot;:&quot;([^&]+)&quot;',
                    r'displayUrl":"([^"]+)"'
                ]
                
                for pattern in image_patterns:
                    match = re.search(pattern, content)
                    if match:
                        image_url = match.group(1).replace('\\u0026', '&').replace('\/', '/')
                        logger.info(f"Found image URL: {image_url[:50]}...")
                        return await self.download_media(image_url, 'jpg')
                        
        except Exception as e:
            logger.warning(f"Embed API failed: {e}")
        
        # Method 2: Try oEmbed API
        try:
            logger.info("Trying oEmbed API...")
            oembed_url = f"https://www.instagram.com/oembed/?url={quote(url)}"
            
            response = self.session.get(oembed_url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'thumbnail_url' in data:
                    thumbnail_url = data['thumbnail_url']
                    logger.info(f"Found thumbnail: {thumbnail_url[:50]}...")
                    return await self.download_media(thumbnail_url, 'jpg')
                    
        except Exception as e:
            logger.warning(f"oEmbed API failed: {e}")
        
        # Method 3: Try web scraping approach
        try:
            logger.info("Trying web scraping...")
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            
            headers = self.get_headers()
            headers['X-Requested-With'] = 'XMLHttpRequest'
            
            response = self.session.get(post_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                content = response.text
                
                # Look for JSON data in script tags
                json_patterns = [
                    r'window\._sharedData = ({.*?});',
                    r'"GraphVideo".*?"video_url":"([^"]+)"',
                    r'"GraphImage".*?"display_url":"([^"]+)"'
                ]
                
                for pattern in json_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if isinstance(match, str) and (match.startswith('http') and ('jpg' in match or 'mp4' in match)):
                            media_url = match.replace('\\u0026', '&').replace('\/', '/')
                            ext = 'mp4' if 'mp4' in media_url else 'jpg'
                            logger.info(f"Found media URL: {media_url[:50]}...")
                            return await self.download_media(media_url, ext)
                            
        except Exception as e:
            logger.warning(f"Web scraping failed: {e}")
        
        return None, "❌ Could not extract media from Instagram post. This might be a private post or the URL format is not supported."
    
    async def download_media(self, media_url, extension):
        """Download media file from URL"""
        try:
            logger.info(f"Downloading media: {media_url[:50]}...")
            
            headers = self.get_headers()
            response = self.session.get(media_url, headers=headers, timeout=60, stream=True)
            response.raise_for_status()
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}') as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
                temp_path = temp_file.name
            
            logger.info(f"Downloaded successfully: {temp_path}")
            return temp_path, "video" if extension == 'mp4' else "photo"
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None, f"Download failed: {str(e)}"
    
    async def download_instagram_post(self, url, max_retries=3):
        """Main download function with fallback methods"""
        try:
            logger.info(f"Starting download for: {url}")
            
            # Add random delay to avoid rate limiting
            await self.smart_delay(1, 3)
            
            # Try third-party API approach
            result = await self.download_with_third_party_api(url)
            if result[0]:  # If successful
                return result
            
            # If all methods fail
            return None, "❌ Unable to download from Instagram. This could be due to:\n• Private account\n• Post deleted\n• Instagram blocking the request\n• Network issues\n\nTry again in a few minutes or with a different post."
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None, f"❌ Unexpected error: {str(e)}"
    
    async def smart_delay(self, min_seconds=1, max_seconds=3):
        """Add random delay"""
        delay = random.uniform(min_seconds, max_seconds)
        logger.info(f"Waiting {delay:.1f} seconds...")
        time.sleep(delay)

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

⚠️ **Important Notes:**
• This bot works **without requiring Instagram login**
• Some private posts may not be accessible
• If download fails, try again in a few minutes

🚀 **Just send me a link to get started!**
    """
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

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

**Troubleshooting:**
• Private posts won't work
• Very new posts might be harder to download
• If it fails, try with an older post
• Wait a few minutes between attempts
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

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
    processing_msg = await update.message.reply_text("🔄 Processing your request... This may take a moment.")
    
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
    
    logger.info("=== NO-LOGIN INSTAGRAM BOT ===")
    logger.info(f"Bot Token: {'✅ Found' if bot_token else '❌ Missing'}")
    logger.info("Instagram Login: ⚠️ Not Required (using public APIs)")
    logger.info("=============================")
    
    logger.info("Starting Instagram Downloader Bot (No Login Required)...")
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_instagram))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()