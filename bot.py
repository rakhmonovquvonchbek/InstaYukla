import os
import re
import requests
import tempfile
import logging
import random
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProxyInstagramDownloader:
    def __init__(self):
        # Free proxy list (you should replace with paid proxies for better reliability)
        self.free_proxies = [
            # HTTP proxies
            "http://8.208.84.236:3128",
            "http://47.74.152.29:8888",
            "http://20.111.54.16:8123",
            "http://47.88.29.108:8080",
            "http://138.68.60.8:8080",
            # Add more proxies here
        ]
        
        # Paid proxy configuration (uncomment and configure if you have paid proxies)
        self.paid_proxies = [
            # Example format for paid proxies:
            # "http://username:password@proxy-server:port",
            # "http://user123:pass456@premium-proxy.com:8080",
        ]
        
        self.user_agents = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Android 12; Mobile; rv:91.0) Gecko/91.0 Firefox/91.0',
            'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36'
        ]
        
        self.current_proxy = None
        self.proxy_failures = {}
    
    def get_working_proxy(self):
        """Get a working proxy from the list"""
        # Combine free and paid proxies
        all_proxies = self.paid_proxies + self.free_proxies
        
        # Filter out failed proxies
        available_proxies = [p for p in all_proxies if self.proxy_failures.get(p, 0) < 3]
        
        if not available_proxies:
            logger.warning("No working proxies available, resetting failure counts")
            self.proxy_failures = {}
            available_proxies = all_proxies
        
        # Select random proxy
        proxy = random.choice(available_proxies)
        logger.info(f"Selected proxy: {proxy[:20]}...")
        return proxy
    
    def test_proxy(self, proxy):
        """Test if a proxy is working"""
        try:
            proxies = {"http": proxy, "https": proxy}
            response = requests.get(
                "http://httpbin.org/ip", 
                proxies=proxies, 
                timeout=10,
                headers={'User-Agent': random.choice(self.user_agents)}
            )
            if response.status_code == 200:
                logger.info(f"Proxy {proxy[:20]}... is working")
                return True
        except Exception as e:
            logger.warning(f"Proxy {proxy[:20]}... failed: {e}")
            self.proxy_failures[proxy] = self.proxy_failures.get(proxy, 0) + 1
        return False
    
    def make_request(self, url, max_retries=3):
        """Make request with proxy rotation"""
        for attempt in range(max_retries):
            try:
                # Get a working proxy
                proxy = self.get_working_proxy()
                
                # Test proxy first
                if not self.test_proxy(proxy):
                    continue
                
                # Configure proxy and headers
                proxies = {"http": proxy, "https": proxy}
                headers = {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
                
                # Add delay between requests
                if attempt > 0:
                    delay = random.uniform(2, 5)
                    logger.info(f"Waiting {delay:.1f} seconds before retry...")
                    time.sleep(delay)
                
                # Make request
                logger.info(f"Making request to {url[:50]}... via proxy")
                response = requests.get(
                    url, 
                    proxies=proxies, 
                    headers=headers, 
                    timeout=30
                )
                
                if response.status_code == 200:
                    logger.info("Request successful!")
                    return response
                else:
                    logger.warning(f"Request failed with status: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Request attempt {attempt + 1} failed: {e}")
                if proxy:
                    self.proxy_failures[proxy] = self.proxy_failures.get(proxy, 0) + 1
        
        return None
    
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
    
    def extract_media_from_html(self, html_content):
        """Extract media URLs from Instagram HTML"""
        try:
            # Look for video URL
            video_patterns = [
                r'"video_url":"([^"]+)"',
                r'videoUrl":"([^"]+)"',
                r'"src":"([^"]*\.mp4[^"]*)"'
            ]
            
            for pattern in video_patterns:
                match = re.search(pattern, html_content)
                if match:
                    video_url = match.group(1).replace('\\u0026', '&').replace('\\/', '/')
                    return video_url, 'video'
            
            # Look for image URL
            image_patterns = [
                r'"display_url":"([^"]+)"',
                r'"src":"([^"]*\.jpg[^"]*)"',
                r'displayUrl":"([^"]+)"'
            ]
            
            for pattern in image_patterns:
                match = re.search(pattern, html_content)
                if match:
                    image_url = match.group(1).replace('\\u0026', '&').replace('\\/', '/')
                    return image_url, 'photo'
            
            return None, None
            
        except Exception as e:
            logger.error(f"Error extracting media: {e}")
            return None, None
    
    async def download_instagram_post(self, url):
        """Download Instagram post using proxy rotation"""
        try:
            shortcode = self.extract_shortcode(url)
            if not shortcode:
                return None, "❌ Invalid Instagram URL format"
            
            logger.info(f"Processing shortcode: {shortcode}")
            
            # Try different Instagram endpoints
            endpoints = [
                f"https://www.instagram.com/p/{shortcode}/",
                f"https://www.instagram.com/p/{shortcode}/?__a=1",
                f"https://www.instagram.com/reel/{shortcode}/",
            ]
            
            for endpoint in endpoints:
                logger.info(f"Trying endpoint: {endpoint}")
                
                # Make request with proxy rotation
                response = self.make_request(endpoint)
                
                if response:
                    # Extract media from response
                    media_url, media_type = self.extract_media_from_html(response.text)
                    
                    if media_url:
                        logger.info(f"Found {media_type}: {media_url[:50]}...")
                        
                        # Download the media file
                        return await self.download_media_file(media_url, media_type)
                
                # Wait between endpoint attempts
                time.sleep(random.uniform(1, 3))
            
            return None, "❌ Could not extract media from Instagram post. The post might be private or deleted."
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None, f"❌ Download failed: {str(e)}"
    
    async def download_media_file(self, media_url, media_type):
        """Download the actual media file"""
        try:
            # Use proxy for media download too
            response = self.make_request(media_url)
            
            if not response:
                return None, "❌ Failed to download media file"
            
            # Save to temporary file
            extension = '.mp4' if media_type == 'video' else '.jpg'
            with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
                temp_file.write(response.content)
                return temp_file.name, media_type
                
        except Exception as e:
            logger.error(f"Media download error: {e}")
            return None, f"❌ Media download failed: {str(e)}"

# Initialize downloader
downloader = ProxyInstagramDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    await update.message.reply_text(
        "🤖 **Instagram Downloader Bot with Proxy Support**\n\n"
        "Send me an Instagram post/reel URL and I'll download it using proxy rotation!\n\n"
        "**Supported:**\n"
        "• instagram.com/p/...\n"
        "• instagram.com/reel/...\n"
        "• instagram.com/tv/...\n\n"
        "**Features:**\n"
        "🔄 Automatic proxy rotation\n"
        "🛡️ Instagram block bypass\n"
        "📱 Mobile user agent simulation\n\n"
        "Just send me a link!",
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
    msg = await update.message.reply_text("🔄 Processing with proxy rotation... This may take a moment.")
    
    try:
        # Download the post
        file_path, file_type = await downloader.download_instagram_post(text)
        
        if file_path and os.path.exists(file_path):
            # Send the downloaded file
            if file_type == "video":
                with open(file_path, 'rb') as video:
                    await update.message.reply_video(video, caption="📹 Downloaded via proxy!")
            else:
                with open(file_path, 'rb') as photo:
                    await update.message.reply_photo(photo, caption="📸 Downloaded via proxy!")
            
            # Clean up
            try:
                os.unlink(file_path)
            except:
                pass
                
            await msg.delete()
            await update.message.reply_text("✅ Download completed using proxy rotation!")
        else:
            await msg.edit_text(f"{file_type}")
            
    except Exception as e:
        logger.error(f"Handler error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)}")

def main():
    """Main function"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    logger.info("=== PROXY INSTAGRAM DOWNLOADER BOT ===")
    logger.info(f"Telegram Token: {'✅ Found' if token else '❌ Missing'}")
    logger.info("Proxy Support: ✅ Enabled")
    logger.info("=====================================")
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        return
    
    logger.info("🚀 Starting bot with proxy support...")
    
    # Create application
    app = Application.builder().token(token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instagram_url))
    
    # Start polling
    app.run_polling()

if __name__ == '__main__':
    main()