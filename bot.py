import os
import re
import requests
import tempfile
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        self.session = requests.Session()
        
    def get_post_data(self, shortcode):
        """Get post data using Instagram's public GraphQL endpoint"""
        try:
            # Instagram's public endpoint for post data
            url = f"https://www.instagram.com/graphql/query/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': 'missing',
                'X-Requested-With': 'XMLHttpRequest',
                'Connection': 'keep-alive',
            }
            
            # Try to get post info without authentication
            simple_url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"
            
            response = self.session.get(simple_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    return data
                except:
                    # If JSON fails, try to extract from HTML
                    return self.extract_from_html(response.text)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting post data: {e}")
            return None
    
    def extract_from_html(self, html_content):
        """Extract media URLs from HTML content"""
        try:
            # Look for video URL
            video_match = re.search(r'"video_url":"([^"]+)"', html_content)
            if video_match:
                video_url = video_match.group(1).replace('\\u0026', '&').replace('\\/', '/')
                return {'video_url': video_url, 'is_video': True}
            
            # Look for image URL
            image_match = re.search(r'"display_url":"([^"]+)"', html_content)
            if image_match:
                image_url = image_match.group(1).replace('\\u0026', '&').replace('\\/', '/')
                return {'display_url': image_url, 'is_video': False}
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting from HTML: {e}")
            return None
    
    def download_media(self, url, filename):
        """Download media file"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }
            
            response = self.session.get(url, headers=headers, timeout=60, stream=True)
            response.raise_for_status()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
                return temp_file.name
                
        except Exception as e:
            logger.error(f"Download failed: {e}")
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
    
    async def download_instagram_post(self, url):
        """Main download function"""
        try:
            shortcode = self.extract_shortcode(url)
            if not shortcode:
                return None, "Invalid Instagram URL"
            
            logger.info(f"Processing shortcode: {shortcode}")
            
            # Get post data
            post_data = self.get_post_data(shortcode)
            if not post_data:
                return None, "Could not fetch post data. The post might be private or deleted."
            
            # Check if it's a video or image
            if post_data.get('is_video') and post_data.get('video_url'):
                # Download video
                file_path = self.download_media(post_data['video_url'], '.mp4')
                if file_path:
                    return file_path, "video"
            elif post_data.get('display_url'):
                # Download image
                file_path = self.download_media(post_data['display_url'], '.jpg')
                if file_path:
                    return file_path, "photo"
            
            return None, "Could not extract media from the post"
            
        except Exception as e:
            logger.error(f"Error in download_instagram_post: {e}")
            return None, f"Download failed: {str(e)}"

# Initialize downloader
downloader = InstagramDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    await update.message.reply_text(
        "🤖 **Instagram Downloader Bot**\n\n"
        "Send me an Instagram post/reel URL and I'll download it!\n\n"
        "Supported:\n"
        "• instagram.com/p/...\n"
        "• instagram.com/reel/...\n\n"
        "Just paste the link and I'll handle the rest!",
        parse_mode='Markdown'
    )

async def handle_instagram_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram URLs"""
    text = update.message.text.strip()
    
    # Check if it's an Instagram URL
    if not re.search(r'instagram\.com/(p|reel)/', text):
        await update.message.reply_text("❌ Please send a valid Instagram post or reel URL.")
        return
    
    # Send processing message
    msg = await update.message.reply_text("⏳ Processing...")
    
    try:
        # Download the post
        file_path, file_type = await downloader.download_instagram_post(text)
        
        if file_path:
            # Send the downloaded file
            if file_type == "video":
                with open(file_path, 'rb') as video:
                    await update.message.reply_video(video, caption="📹 Downloaded!")
            else:
                with open(file_path, 'rb') as photo:
                    await update.message.reply_photo(photo, caption="📸 Downloaded!")
            
            # Clean up
            try:
                os.unlink(file_path)
            except:
                pass
                
            await msg.delete()
        else:
            await msg.edit_text(f"❌ {file_type}")
            
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

def main():
    """Main function"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found!")
        return
    
    print("🚀 Starting bot...")
    
    # Create application
    app = Application.builder().token(token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instagram_url))
    
    # Start polling
    app.run_polling()

if __name__ == '__main__':
    main()