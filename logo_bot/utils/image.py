import os
import io
import base64
import urllib.parse
import requests
import re
from PIL import Image

from ..config import HEADERS

def is_valid_image_url(url):
    """
    Check if a URL is a valid image URL by checking file extension or content type
    
    Args:
        url (str): URL to check
        
    Returns:
        bool: True if URL is a valid image URL, False otherwise
    """
    if not url:
        return False
        
    # Data URIs are valid as they contain image data
    if url.startswith('data:image/'):
        return True
        
    # If the URL has a query string or fragment, remove it
    cleaned_url = url.split('?')[0].split('#')[0]
    
    # Get the file extension
    _, ext = os.path.splitext(cleaned_url)
    
    # Convert to lowercase and check if it's an image extension
    ext = ext.lower()
    
    # Check common image extensions
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff']
    
    if ext in valid_extensions:
        return True
    
    # If no extension, try to request headers to determine MIME type
    if not ext and not url.startswith('data:'):
        try:
            headers = HEADERS.copy()
            response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                return 'image/' in content_type
        except Exception as e:
            print(f"Error validating image URL: {e}")
            return False
    
    return False

def download_image(image_url, output_path, max_retries=3, timeout=10):
    """
    Download an image from a URL with retries
    
    Args:
        image_url (str): URL of the image to download
        output_path (str): Path to save the image to
        max_retries (int): Maximum number of retries
        timeout (int): Timeout in seconds
        
    Returns:
        str: Path to the downloaded image, or None on error
    """
    from ..extractors.google import GoogleExtractor
    
    # Skip URLs with known access issues that direct approaches can't handle
    if 'trust.new-innov.com' in image_url:
        print(f"URL {image_url} requires special handling - using advanced Google extractor")
        # Initialize a temporary Google extractor to use just its download capabilities
        extractor = GoogleExtractor("example.com")
        return extractor._download_image(image_url, output_path)
    
    # For normal URLs, continue with standard approach
    for attempt in range(max_retries):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': image_url,
                'Connection': 'keep-alive',
            }
            
            response = requests.get(image_url, headers=headers, stream=True, timeout=timeout)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                
                # Make sure the content is an image
                if 'image' in content_type or check_content_for_image(response.content):
                    # Choose extension based on content type or URL
                    extension = choose_extension(content_type, image_url)
                    file_path = f"{os.path.splitext(output_path)[0]}{extension}"
                    
                    # Save the image
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(8192):
                            f.write(chunk)
                    
                    # Verify it's a valid image file
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        try:
                            Image.open(file_path).verify()
                            return file_path
                        except (UnidentifiedImageError, OSError, IOError) as e:
                            print(f"Downloaded file is not a valid image: {e}")
                            # If it's not a valid image, delete it
                            if os.path.exists(file_path):
                                os.remove(file_path)
                else:
                    print(f"URL does not point to an image. Content-Type: {content_type}")
            else:
                print(f"Failed to download image, status code: {response.status_code}")
                if attempt < max_retries - 1:
                    print(f"Retrying ({attempt + 2}/{max_retries})...")
                
        except requests.exceptions.Timeout:
            print(f"Request timed out. Retrying ({attempt + 2}/{max_retries})...")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying ({attempt + 2}/{max_retries})...")
    
    return None

def save_data_uri(data_uri, output_path):
    """
    Parse and save a data URI to a file
    
    Args:
        data_uri (str): Data URI to save
        output_path (str): Path to save the image to
        
    Returns:
        str: Path to the saved image, or None on error
    """
    try:
        # Parse the data URI
        if not data_uri.startswith('data:'):
            print(f"Invalid data URI: {data_uri[:50]}...")
            return None
            
        # Extract MIME type and data
        metadata, encoded_data = data_uri.split(',', 1)
        
        # Check if it's base64 encoded
        is_base64 = ';base64' in metadata
        
        if is_base64:
            # Decode the base64 data
            try:
                image_data = base64.b64decode(encoded_data)
            except Exception as e:
                print(f"Error decoding base64 data: {e}")
                return None
        else:
            # Handle URL-encoded data
            image_data = urllib.parse.unquote_plus(encoded_data).encode('latin1')
            
        # Write the data to a file
        with open(output_path, 'wb') as f:
            f.write(image_data)
            
        print(f"Image saved to {output_path} from data URI")
        return output_path
        
    except Exception as e:
        print(f"Error saving data URI: {e}")
        return None

def get_image_info(url, timeout=10):
    """
    Get information about an image without downloading the entire file
    
    Args:
        url (str): URL of the image
        timeout (int): Timeout in seconds
        
    Returns:
        dict: Information about the image, or None on error
    """
    try:
        # Check if it's an SVG first (text-based format)
        if url.lower().endswith('.svg'):
            return {
                'format': 'SVG',
                'width': 0,  # SVG is vector, so size is infinite
                'height': 0,
                'url': url
            }
            
        # For other formats, download the image data
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        
        # Use PIL to get image info
        img = Image.open(io.BytesIO(response.content))
        
        return {
            'format': img.format,
            'width': img.width,
            'height': img.height,
            'mode': img.mode,
            'url': url
        }
    except Exception as e:
        print(f"Error getting image info for {url}: {e}")
        return None

def convert_webp_to_png(input_path):
    """
    Convert WebP image to PNG format
    
    Args:
        input_path (str): Path to the WebP image
        
    Returns:
        str: Path to the converted PNG image, or original path if not a WebP
    """
    try:
        if not input_path.lower().endswith('.webp'):
            return input_path  # Not a WebP file, return original path
            
        output_path = input_path.rsplit('.', 1)[0] + '.png'
        
        # Open WebP image and convert to PNG
        img = Image.open(input_path)
        
        # Check if image has transparency
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            # Preserve alpha channel
            img = img.convert('RGBA')
        else:
            # Convert to RGB if no transparency
            img = img.convert('RGB')
            
        # Save as PNG
        img.save(output_path, 'PNG')
        
        # Remove original WebP file
        os.remove(input_path)
        
        print(f"Converted WebP to PNG: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error converting WebP to PNG: {e}")
        return input_path  # Return original path if conversion fails

def auto_crop_image(image_path):
    """
    Auto-crop image to remove transparent background
    
    Args:
        image_path (str): Path to the image
        
    Returns:
        str: Path to the cropped image, or original path on error
    """
    try:
        # Check if file exists
        if not os.path.exists(image_path):
            print(f"File not found: {image_path}")
            return image_path
            
        # Open the image
        img = Image.open(image_path)
        
        # Make sure it has an alpha channel
        if img.mode != 'RGBA':
            # If it's a PNG with a palette and transparency
            if img.mode == 'P' and 'transparency' in img.info:
                img = img.convert('RGBA')
            # If it's another format, add alpha channel
            elif img.mode != 'RGBA':
                # Some formats don't support alpha, so we skip
                if img.format in ['JPEG', 'JPG']:
                    return image_path
                try:
                    img = img.convert('RGBA')
                except:
                    # If conversion fails, return original
                    return image_path
        
        # Get image data
        width, height = img.size
        pixels = img.load()
        
        # Find bounding box of non-transparent pixels
        top = 0
        bottom = height
        left = 0
        right = width
        found_content = False
        
        # Find top
        for y in range(height):
            for x in range(width):
                if pixels[x, y][3] > 0:  # If alpha > 0
                    top = y
                    found_content = True
                    break
            if found_content:
                break
                
        # Find bottom
        found_content = False
        for y in range(height - 1, -1, -1):
            for x in range(width):
                if pixels[x, y][3] > 0:
                    bottom = y + 1
                    found_content = True
                    break
            if found_content:
                break
                
        # Find left
        found_content = False
        for x in range(width):
            for y in range(height):
                if pixels[x, y][3] > 0:
                    left = x
                    found_content = True
                    break
            if found_content:
                break
                
        # Find right
        found_content = False
        for x in range(width - 1, -1, -1):
            for y in range(height):
                if pixels[x, y][3] > 0:
                    right = x + 1
                    found_content = True
                    break
            if found_content:
                break
        
        # If we found non-transparent content
        if left < right and top < bottom:
            # Crop to bounding box
            cropped = img.crop((left, top, right, bottom))
            
            # Save cropped image
            cropped.save(image_path, format=img.format if img.format else 'PNG')
            print(f"Auto-cropped image to remove transparent background: {image_path}")
        else:
            print(f"No non-transparent content found or image already cropped: {image_path}")
            
        return image_path
    except Exception as e:
        print(f"Error auto-cropping image: {e}")
        return image_path  # Return original path if cropping fails

def is_likely_hero_image(url):
    """
    Determine if a URL is likely a hero/banner image rather than a logo
    
    Args:
        url (str): URL to check
        
    Returns:
        bool: True if URL is likely a hero image, False otherwise
    """
    if not url:
        return False
        
    url_lower = url.lower()
    
    # Hero image indicators in the URL
    hero_terms = [
        'hero', 'banner', 'background', 'header-bg', 'bg-', 'slide', 
        'carousel', 'header-image', 'splash', 'cover', 'main-image',
        'showcase', 'featured', 'jumbotron', 'slider', 'billboard',
        'masthead', 'header-photo', 'panorama', 'headline', 'feature-img',
        'header-banner', 'hero-image', 'main-banner', 'bg_'
    ]
    
    # Check filename part
    filename = url_lower.split('/')[-1]
    if any(term in filename for term in hero_terms):
        return True
    
    # Check full URL path
    if any(term in url_lower for term in hero_terms):
        return True
            
    # Check for overly generic names
    generic_names = ['header.jpg', 'header.png', 'header.svg', 'bg.jpg', 'bg.png', 'bg.svg']
    if any(name in url_lower for name in generic_names):
        return True
    
    # Check for common hero image paths
    hero_paths = ['/assets/images/header/', '/images/hero/', '/img/banner/', '/assets/banner/']
    if any(path in url_lower for path in hero_paths):
        return True
            
    return False

def is_likely_icon_not_logo(url):
    """
    Check if a URL is likely to be an icon but not a company logo
    
    Args:
        url (str): URL to check
        
    Returns:
        bool: True if URL is likely an icon but not a logo, False otherwise
    """
    if not url:
        return False
        
    url_lower = url.lower()
    filename = url_lower.split('/')[-1]
    
    # Common patterns for icons that aren't logos
    icon_patterns = [
        'icon-', '-icon', 'ico-', '-ico',
        'symbol-', '-symbol',
        'glyph-', '-glyph'
    ]
    
    # Specific icon types that aren't typically logos
    specific_icons = [
        'arrow', 'chevron', 'menu', 'hamburger', 'search', 'cart', 
        'social', 'facebook', 'twitter', 'instagram', 'linkedin',
        'youtube', 'pinterest', 'tiktok', 'snapchat', 'whatsapp',
        'phone', 'email', 'contact', 'chat', 'message', 'comment',
        'user', 'profile', 'account', 'person', 'login', 'signin',
        'download', 'upload', 'share', 'close', 'plus', 'minus',
        'star', 'heart', 'like', 'check', 'checkmark', 'clock',
        'calendar', 'time', 'date', 'location', 'map', 'pin',
        'settings', 'gear', 'cog', 'edit', 'pencil', 'delete',
        'trash', 'refresh', 'sync', 'update', 'play', 'pause'
    ]
    
    # Check if filename starts with icon pattern
    if any(pattern in filename for pattern in icon_patterns):
        return True
        
    # Check if filename contains specific icon types
    if any(icon in filename for icon in specific_icons):
        return True
        
    # Feature icons often appear in feature sections
    if 'feature' in url_lower and ('icon' in url_lower or 'symbol' in url_lower):
        return True
        
    return False

def process_logo_image(image_path):
    """
    Process a logo image to improve quality and validate it
    
    Args:
        image_path (str): Path to the image
        
    Returns:
        tuple: (processed_path, valid, issues)
            - processed_path: Path to the processed image or None if processing failed
            - valid: Boolean indicating if the image is valid after processing
            - issues: List of issues found with the image
    """
    try:
        # Check if file exists
        if not os.path.exists(image_path):
            print(f"File not found: {image_path}")
            return None, False, ["File not found"]
            
        # Special handling for SVG files
        if image_path.lower().endswith('.svg'):
            # SVG files can't be processed by PIL, just check if they're valid SVG files
            try:
                # Try to read as binary first since it might be compressed
                with open(image_path, 'rb') as f:
                    svg_content = f.read()
                    # Check for SVG signature bytes or text
                    if b'<svg' in svg_content and b'</svg>' in svg_content:
                        print(f"SVG file appears valid: {image_path}")
                        # Return as-is since we can't process SVGs with PIL
                        return image_path, True, []
                    else:
                        # If not binary SVG, try text
                        try:
                            svg_text = svg_content.decode('utf-8')
                            if '<svg' in svg_text and '</svg>' in svg_text:
                                print(f"SVG file appears valid (text format): {image_path}")
                                return image_path, True, []
                        except UnicodeDecodeError:
                            pass
                        
                        print(f"File is not a valid SVG: {image_path}")
                        return None, False, ["Image is not a valid SVG file"]
            except Exception as e:
                print(f"Error reading SVG file: {e}")
                return None, False, ["Image is corrupted or not a valid SVG file"]
        
        # For WebP images, convert to PNG for better compatibility
        if image_path.lower().endswith('.webp'):
            image_path = convert_webp_to_png(image_path)
        
        # Import here to avoid circular imports
        from .qa import validate_and_fix_logo
        
        # Validate the logo quality and get any issues
        processed_path, is_valid, issues = validate_and_fix_logo(image_path)
        
        # If valid, apply standard processing
        if is_valid:
            # Open the image
            img = Image.open(processed_path)
            
            # Auto-crop the image to remove transparent backgrounds
            if img.mode == 'RGBA' or (img.mode == 'P' and 'transparency' in img.info):
                cropped_path = auto_crop_image(processed_path)
                if cropped_path:
                    processed_path = cropped_path
        
        # Return the processed image path and validation status
        return processed_path, is_valid, issues
            
    except Exception as e:
        print(f"Error during logo processing: {e}")
        import traceback
        traceback.print_exc()
        return None, False, [f"Error during processing: {str(e)}"]

def check_content_for_image(content):
    """
    Check if content is likely an image by examining its bytes
    
    Args:
        content (bytes): Content to check
        
    Returns:
        bool: True if the content appears to be an image, False otherwise
    """
    # Common image file signatures (magic numbers)
    signatures = {
        b'\xFF\xD8\xFF': 'jpg/jpeg',  # JPEG
        b'\x89PNG\r\n\x1A\n': 'png',  # PNG
        b'GIF8': 'gif',  # GIF
        b'<svg': 'svg',  # SVG (XML-based, so checking for opening tag)
        b'\x00\x00\x01\x00': 'ico',  # ICO
        b'RIFF': 'webp',  # WEBP
    }
    
    if not content or len(content) < 8:
        return False
        
    # Check against known signatures
    for signature, format_name in signatures.items():
        if content.startswith(signature):
            return True
            
    # Additional check for SVG which might have whitespace or XML declaration before the SVG tag
    if b'<svg' in content[:1000] and (b'</svg>' in content or b'/>' in content[-100:]):
        return True
        
    return False

def choose_extension(content_type, url):
    """
    Choose the appropriate file extension based on content type and URL
    
    Args:
        content_type (str): Content type from HTTP headers
        url (str): URL of the image
        
    Returns:
        str: Appropriate file extension with dot (e.g. '.png')
    """
    # Map content types to extensions
    content_type_map = {
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/svg+xml': '.svg',
        'image/webp': '.webp',
        'image/x-icon': '.ico',
        'image/vnd.microsoft.icon': '.ico',
    }
    
    # First check content type
    if content_type and content_type in content_type_map:
        return content_type_map[content_type]
    
    # Then check URL extension
    url_path = url.split('?')[0].split('#')[0]  # Remove query and fragment
    file_extension = os.path.splitext(url_path)[1].lower()
    
    if file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico']:
        return file_extension
    
    # Default to PNG if we can't determine
    return '.png' 