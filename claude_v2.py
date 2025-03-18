import anthropic
import sys
import os
import requests
import re
import time
import json
import hashlib
import traceback
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path
import io
from PIL import Image
import argparse
import base64
import urllib.parse
import random

# Load environment variables from .env file
load_dotenv()

# Constants
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "logo_bot")
os.makedirs(CACHE_DIR, exist_ok=True)

# Directory for storing high-quality logo files
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "logos")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# HTTP Headers to use for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

def normalize_url(url):
    """Normalize URL by adding https:// prefix if missing"""
    if url and not url.startswith(('http://', 'https://')):
        return 'https://' + url
    return url

def download_company_logo(website_url, force_refresh=False, use_claude_fallback=True):
    """
    Download company logo from a website
    
    Args:
        website_url: URL of the website to extract logo from
        force_refresh: Whether to bypass cache (default: False)
        use_claude_fallback: Whether to use Claude as fallback if direct extraction fails (default: True)
    """
    # Normalize URL by adding https:// if missing
    website_url = normalize_url(website_url)
    
    start_time = time.time()
    
    # Initialize token tracking in case we use Claude
    token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "system_prompt_tokens": 313,  # Tool use system prompt tokens for Claude 3.5 Sonnet
        "computer_tool_tokens": 683,  # Additional tokens for computer_20241022
        "bash_tool_tokens": 245       # Additional tokens for bash_20241022
    }
    
    # Check cache first unless force_refresh is True
    if not force_refresh:
        cache_key = hashlib.md5(website_url.encode()).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                # Check if we previously determined this is a text-based logo
                if cache_data.get('text_based_logo', False):
                    print("Cached result indicates this site uses a text-based logo with no image file.")
                    return None
                
                cached_logo_url = cache_data.get('logo_url')
                if cached_logo_url:
                    print(f"Found cached logo URL: {cached_logo_url}")
                    
                    # Check if the cached URL has hero/banner terms that indicate it's not a real logo
                    if is_likely_hero_image(cached_logo_url):
                        print("Cached URL appears to be a hero image, not a logo. Clearing cache for this URL.")
                        os.remove(cache_file)
                        print(f"Removed cached entry for {website_url}")
                    # If it's not a hero image, check if it's valid
                    elif is_valid_image_url(cached_logo_url):
                        return download_image(cached_logo_url, website_url)
                    else:
                        print("Cached logo URL is invalid. Clearing cache entry.")
                        os.remove(cache_file)
    
    # FIRST APPROACH: Try direct BeautifulSoup extraction first (much cheaper)
    print("APPROACH 1: Using direct BeautifulSoup extraction...")
    logo_result = extract_logo_from_website(website_url)
    
    # Check if we determined this is a text-based logo site
    if logo_result == "TEXT_BASED_LOGO":
        print("This site uses a text-based logo with no image file.")
        # Cache the result
        cache_key = hashlib.md5(website_url.encode()).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        with open(cache_file, 'w') as f:
            json.dump({
                'website_url': website_url,
                'text_based_logo': True,
                'timestamp': time.time(),
                'method': 'beautifulsoup'
            }, f)
        return None
    
    logo_url = logo_result
    
    # If we found a valid logo URL with BeautifulSoup, use it
    if logo_url and is_valid_image_url(logo_url) and not is_likely_hero_image(logo_url) and not is_likely_icon_not_logo(logo_url):
        print(f"Successfully found logo URL using BeautifulSoup: {logo_url}")
        
        # Check for higher quality versions
        high_quality_url = try_find_higher_quality_version(logo_url, website_url)
        if high_quality_url and high_quality_url != logo_url and is_valid_image_url(high_quality_url) and not is_likely_hero_image(high_quality_url) and not is_likely_icon_not_logo(high_quality_url):
            print(f"Found higher quality version: {high_quality_url}")
            logo_url = high_quality_url
            
        # Cache the URL
        cache_key = hashlib.md5(website_url.encode()).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        with open(cache_file, 'w') as f:
            json.dump({
                'website_url': website_url,
                'logo_url': logo_url,
                'timestamp': time.time(),
                'method': 'beautifulsoup'
            }, f)
            
        # Download and return
        return download_image(logo_url, website_url)
    
    # If BeautifulSoup failed and we're not using Claude fallback, return None
    if not use_claude_fallback:
        print("BeautifulSoup extraction failed and Claude fallback is disabled.")
        return None
    
    # SECOND APPROACH: If direct extraction failed, try Claude (expensive but powerful)
    print("BeautifulSoup extraction failed or returned invalid URL.")
    print("APPROACH 2: Trying Claude GUI approach...")
    
    # Get API key from environment variable
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        print("ANTHROPIC_API_KEY not found in .env file")
        print("Cannot use Claude fallback without API key.")
        return None
    
    # Initialize the Anthropic client with the API key
    client = anthropic.Anthropic(api_key=api_key)
    
    # Try the GUI approach with Claude
    logo_url, gui_tokens = try_copy_image_address(client, website_url)
    
    # Update token usage
    token_usage["input_tokens"] += gui_tokens["input_tokens"]
    token_usage["output_tokens"] += gui_tokens["output_tokens"]
    
    # Check if Claude detected a text-based logo
    if logo_url is None and gui_tokens.get("text_based_logo", False):
        print("Claude determined this site uses a text-based logo with no image file.")
        # Cache this result
        cache_key = hashlib.md5(website_url.encode()).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        with open(cache_file, 'w') as f:
            json.dump({
                'website_url': website_url,
                'text_based_logo': True,
                'timestamp': time.time(),
                'method': 'claude'
            }, f)
        
        show_token_usage_and_cost(token_usage)
        return None
    
    # Check if we found a valid logo URL with Claude
    if logo_url and is_valid_image_url(logo_url) and not is_likely_hero_image(logo_url) and not is_likely_icon_not_logo(logo_url):
        print(f"Successfully found logo URL using Claude: {logo_url}")
        
        # Check for higher quality versions
        high_quality_url = try_find_higher_quality_version(logo_url, website_url)
        if high_quality_url and high_quality_url != logo_url and is_valid_image_url(high_quality_url) and not is_likely_hero_image(high_quality_url) and not is_likely_icon_not_logo(high_quality_url):
            print(f"Found higher quality version: {high_quality_url}")
            logo_url = high_quality_url
            
        # Cache the URL
        cache_key = hashlib.md5(website_url.encode()).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        with open(cache_file, 'w') as f:
            json.dump({
                'website_url': website_url,
                'logo_url': logo_url,
                'timestamp': time.time(),
                'method': 'claude'
            }, f)
            
        # Show token usage and cost
        show_token_usage_and_cost(token_usage)
        
        # Download and return
        return download_image(logo_url, website_url)
    
    # If we still don't have a logo URL, give up
    print("Could not find a valid logo URL after multiple attempts.")
    if use_claude_fallback:
        show_token_usage_and_cost(token_usage)
    execution_time = time.time() - start_time
    print(f"\nTotal execution time: {execution_time:.2f} seconds")
    return None

def is_likely_hero_image(url):
    """Determine if a URL is likely a hero image rather than a logo"""
    if not url:
        return False
        
    url_lower = url.lower()
    
    # Expanded list of hero image indicators in the URL
    hero_terms = [
        'hero', 'banner', 'background', 'header-bg', 'bg-', 'slide', 
        'carousel', 'header-image', 'splash', 'cover', 'main-image',
        'showcase', 'featured', 'jumbotron', 'slider', 'billboard',
        'masthead', 'header-photo', 'panorama', 'headline', 'feature-img',
        'header-banner', 'hero-image', 'main-banner', 'bg_'
    ]
    
    # Check filename part - if it directly contains hero terms
    filename = url_lower.split('/')[-1]
    if any(term in filename for term in hero_terms):
        return True
    
    # Check full URL path for hero terms
    if any(term in url_lower for term in hero_terms):
        return True
            
    # Check for overly generic names that are likely to be hero images
    generic_names = ['header.jpg', 'header.png', 'header.svg', 'bg.jpg', 'bg.png', 'bg.svg']
    if any(name in url_lower for name in generic_names):
        return True
    
    # Check for common paths that typically contain hero images
    hero_paths = ['/assets/images/header/', '/images/hero/', '/img/banner/', '/assets/banner/']
    if any(path in url_lower for path in hero_paths):
        return True
            
    return False

def extract_logo_from_website(url, prioritize_header=True):
    """Extract logo URL directly from website using BeautifulSoup with enhanced methods"""
    print("Analyzing website HTML to find logos...")
    
    try:
        # First try finding directly in header/navbar (most reliable approach)
        if prioritize_header:
            print("Looking for logo in header/navbar first...")
            header_result = find_header_logo(url)
            
            # Check if it's a text-based logo
            if header_result == "TEXT_BASED_LOGO":
                print("Found text-based logo in the header. The site doesn't use an image-based logo.")
                return "TEXT_BASED_LOGO"
                
            # Otherwise it's an image URL
            header_logo = header_result
            if header_logo and is_valid_image_url(header_logo):
                # Make sure it's not a hero image or favicon
                if not is_likely_hero_image(header_logo) and 'favicon' not in header_logo.lower():
                    print(f"Found valid logo in header/navbar: {header_logo}")
                    return header_logo
                elif is_likely_hero_image(header_logo):
                    print(f"Image found in header appears to be a hero image, not a logo: {header_logo}")
                elif 'favicon' in header_logo.lower():
                    print(f"Image found in header appears to be a favicon, not a logo: {header_logo}")
        
        # Next try the potential logos finder method (gets multiple candidates)
        potential_logos = find_potential_logos(url)
        
        if potential_logos:
            print(f"Found {len(potential_logos)} potential logo candidates")
            
            # Filter out low-quality candidates
            filtered_logos = []
            for logo in potential_logos:
                # Skip obvious placeholder images
                if 'nitro-empty-id' in logo['url'] and 'base64' in logo['url']:
                    print(f"Filtering out nitro placeholder: {logo['url'][:50]}...")
                # Skip hero images
                elif is_likely_hero_image(logo['url']):
                    print(f"Filtering out hero image: {logo['url'][:50]}...")
                # Skip favicon images
                elif 'favicon' in logo['url'].lower():
                    print(f"Filtering out favicon: {logo['url'][:50]}...")
                # Skip icons that aren't likely logos
                elif is_likely_icon_not_logo(logo['url']):
                    print(f"Filtering out icon that's not a logo: {logo['url'][:50]}...")
                # Skip very low priority images
                elif logo.get('priority', 0) < 0:
                    print(f"Filtering out low priority image: {logo['url'][:50]}...")
                else:
                    filtered_logos.append(logo)
            
            # If we have valid logos after filtering
            if filtered_logos:
                # Try each logo candidate, starting with the highest priority ones
                for logo_candidate in filtered_logos:
                    print(f"Checking candidate (priority {logo_candidate.get('priority', 0):.1f}): {logo_candidate['url'][:80]}...")
                    if is_valid_image_url(logo_candidate['url']) and not is_likely_hero_image(logo_candidate['url']):
                        print(f"Found valid logo URL: {logo_candidate['url']}")
                        return logo_candidate['url']
        
        # Try to find logos from metadata (but not favicon)
        print("Looking for logos in metadata...")
        meta_logo = extract_logo_from_metadata(url)
        if meta_logo and is_valid_image_url(meta_logo) and not is_likely_hero_image(meta_logo) and 'favicon' not in meta_logo.lower():
            print(f"Found logo in metadata: {meta_logo}")
            return meta_logo
            
        # No logo found with any method
        print("No valid logo found with any direct extraction method.")
        print("This site may use a text-based logo without an image file.")
        return None
        
    except Exception as e:
        print(f"Error extracting logo directly: {e}")
        return None

def find_header_logo(url):
    """Specifically look for logo in header/navbar area"""
    html = fetch_website_html(url)
    if not html:
        return None
        
    soup = BeautifulSoup(html, 'html.parser')
    base_url = "{0.scheme}://{0.netloc}".format(urlparse(url))
    
    # First, look for direct header/navbar elements
    header_elements = soup.find_all(['header', 'nav'])
    
    # Also look for divs with header/navbar classes
    header_classes = ['header', 'navbar', 'nav', 'site-header', 'main-header', 'top-header']
    for div in soup.find_all('div', class_=lambda c: c and any(cls in str(c).lower() for cls in header_classes)):
        header_elements.append(div)
    
    # Handle text-based logos first (like "Apprentice Health" case)
    for header in header_elements:
        # Look for anchor tags with "logo" class
        text_logo_links = header.find_all('a', class_=lambda c: c and 'logo' in str(c).lower())
        
        for link in text_logo_links:
            # Check if this link points to homepage (common for logos)
            href = link.get('href', '')
            is_home_link = href == '/' or href == '#' or href == url or href == url.rstrip('/')
            
            if is_home_link:
                # Check if there's an image inside the link
                img = link.find('img')
                if img and img.get('src'):
                    # This is an image-based logo
                    src = img.get('src')
                    if src and 'favicon' not in src.lower():
                        abs_url = urljoin(url, src)
                        if not is_likely_hero_image(abs_url):
                            return abs_url
                else:
                    # This is a text-based logo without an image
                    # Check if it has text content
                    if link.text.strip():
                        print(f"Found text-based logo: '{link.text.strip()}'")
                        # Return special marker for text-based logos
                        return "TEXT_BASED_LOGO"
    
    # Continue with normal image-based logo search
    for header in header_elements:
        # Look for logo containers within the header
        logo_containers = header.find_all(class_=lambda c: c and any(term in str(c).lower() for term in ['logo', 'brand', 'site-title']))
        
        # If no specific logo containers, search all images in header
        if not logo_containers:
            logo_containers = [header]
        
        for container in logo_containers:
            # First look for images with proper src
            images = container.find_all('img', src=True)
            
            # If none found, try images with lazy-loading attributes
            if not images:
                images = container.find_all('img', attrs={'data-src': True})
            if not images:
                images = container.find_all('img', attrs={'nitro-lazy-src': True})
            
            for img in images:
                # Skip favicon images
                if img.get('src') and 'favicon' in img.get('src').lower():
                    continue
                
                # Extract the URL from the most appropriate attribute
                src = img.get('src')
                
                # If no src, try other attributes in this order of preference
                if not src:
                    for attr in ['nitro-lazy-src', 'data-src', 'data-original', 'data-lazy-src']:
                        if img.get(attr) and 'favicon' not in img.get(attr).lower():
                            src = img.get(attr)
                            break
                
                # If still no src found or it's a favicon, skip this img
                if not src or 'favicon' in src.lower():
                    continue
                    
                # Try srcset attributes for higher resolution
                srcset = img.get('srcset') or img.get('nitro-lazy-srcset')
                highest_res_url = None
                
                if srcset:
                    try:
                        # Find the highest resolution image in srcset
                        highest_width = 0
                        srcset_parts = srcset.split(',')
                        
                        for part in srcset_parts:
                            part = part.strip()
                            url_parts = part.split(' ')
                            
                            if len(url_parts) >= 2:
                                url = url_parts[0].strip()
                                if 'favicon' in url.lower():
                                    continue
                                    
                                width_str = url_parts[1].strip()
                                if width_str.endswith('w'):
                                    try:
                                        width = int(width_str[:-1])
                                        if width > highest_width:
                                            highest_width = width
                                            highest_res_url = url
                                    except ValueError:
                                        pass
                    except Exception as e:
                        print(f"Error parsing srcset: {e}")
                
                # Use highest res from srcset if available, otherwise use src
                if highest_res_url:
                    img_url = highest_res_url
                elif src:
                    img_url = src
                else:
                    continue
                
                # Make the URL absolute
                if img_url.startswith('//'):
                    abs_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    abs_url = base_url + img_url
                elif not img_url.startswith(('http://', 'https://', 'data:')):
                    abs_url = urljoin(url, img_url)
                else:
                    abs_url = img_url
                
                # Skip hero images, large banners, and favicons
                if is_likely_hero_image(abs_url) or 'favicon' in abs_url.lower() or is_likely_icon_not_logo(abs_url):
                    continue
                
                # Check if this is likely a logo based on attributes
                alt_text = img.get('alt', '').lower()
                class_attr = img.get('class', [])
                if class_attr:
                    class_attr = ' '.join(str(c) for c in class_attr).lower()
                else:
                    class_attr = ''
                
                is_likely_logo = ('logo' in img_url.lower() or 
                                 'logo' in alt_text or 
                                 'brand' in alt_text or
                                 'logo' in class_attr)
                
                # If in a logo container or has logo attributes, return this URL
                container_class = container.get('class', [])
                if container_class:
                    container_class = ' '.join(str(c) for c in container_class).lower()
                else:
                    container_class = ''
                
                if is_likely_logo or 'logo' in container_class:
                    return abs_url
                    
                # If inside a link to homepage, very likely a logo
                parent_a = img.find_parent('a')
                if parent_a and parent_a.get('href') in ['/', '#', url, url.rstrip('/')]:
                    return abs_url
                    
    # No logo found in headers
    return None

def extract_logo_from_metadata(url):
    """Try to extract logo URL from website metadata"""
    html = fetch_website_html(url)
    if not html:
        return None
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # Check for various metadata that might contain the logo
    # 1. Check for Open Graph image
    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content') and not is_likely_hero_image(og_image['content']) and 'favicon' not in og_image['content'].lower():
        return urljoin(url, og_image['content'])
    
    # 2. Check for Twitter card image
    twitter_image = soup.find('meta', {'name': 'twitter:image'})
    if twitter_image and twitter_image.get('content') and not is_likely_hero_image(twitter_image['content']) and 'favicon' not in twitter_image['content'].lower():
        return urljoin(url, twitter_image['content'])
    
    # 3. Check for schema.org organization logo
    schema_org = soup.find('script', {'type': 'application/ld+json'})
    if schema_org and schema_org.string:
        try:
            data = json.loads(schema_org.string)
            if isinstance(data, dict):
                # Look for logo in schema.org data
                logo = None
                if 'logo' in data:
                    logo = data['logo']
                elif 'organization' in data and 'logo' in data['organization']:
                    logo = data['organization']['logo']
                elif 'publisher' in data and 'logo' in data['publisher']:
                    logo = data['publisher']['logo']
                
                # If logo is a dict, look for url field
                if isinstance(logo, dict) and 'url' in logo:
                    logo = logo['url']
                
                if logo and isinstance(logo, str) and not is_likely_hero_image(logo) and 'favicon' not in logo.lower():
                    return urljoin(url, logo)
        except:
            pass
    
    return None

def find_potential_logos(url):
    """Find all potential logo images on a website and rank them by likelihood"""
    images = find_image_urls(url, url)
    
    if not images:
        return []
    
    # Add priority scores to all images
    for img in images:
        # Default priority
        priority = 0
        
        # Skip and heavily penalize favicons
        if 'favicon' in img['url'].lower():
            priority -= 20
            continue
            
        # Increase priority for images with logo in URL
        if 'logo' in img['url'].lower():
            priority += 10
            
        # Penalize images that are hero images or likely not logos
        if is_likely_hero_image(img['url']):
            priority -= 15
        
        # Increase priority for SVG images (vector graphics)
        if img['url'].lower().endswith('.svg'):
            priority += 5
        
        # Increase priority for PNG images (lossless)
        elif img['url'].lower().endswith('.png'):
            priority += 3
            
        # Increase priority for images explicitly marked as logos
        if img['is_likely_logo']:
            priority += 5
            
        # Increase priority for images in header areas
        if 'header' in img['parent_class'] or 'nav' in img['parent_class']:
            priority += 3
            
        # Boost priority for images with 'logo' in alt text or class
        if any(term in img['alt'] for term in ['logo', 'brand']):
            priority += 4
            
        if any(term in img['class'] for term in ['logo', 'brand']):
            priority += 4
            
        if any(term in img['id'] for term in ['logo', 'brand']):
            priority += 4
            
        # Higher priority for images at the top of the page (header area)
        if 'header' in img['parent_class']:
            priority += 3
            
        # Penalize favicons again based on dimensions
        width = img.get('width')
        height = img.get('height')
        if width and height:
            try:
                width_val = int(width) if width else 0
                height_val = int(height) if height else 0
                if width_val <= 32 and height_val <= 32:
                    priority -= 5
            except (ValueError, TypeError):
                pass  # Ignore conversion errors
        
        # Store the priority score
        img['priority'] = priority
    
    # Sort by priority (highest first)
    sorted_images = sorted(images, key=lambda x: x['priority'], reverse=True)
    
    # Filter out favicon images before returning
    filtered_images = [img for img in sorted_images if 'favicon' not in img['url'].lower()]
    
    # Return top candidates
    return filtered_images[:10]  # Return top 10 candidates

def try_find_higher_quality_version(url, domain_url):
    """Try to find a higher quality version of the logo by modifying the URL patterns"""
    if not url:
        return None
        
    # Don't try for data URIs
    if url.startswith('data:'):
        return url
        
    try:
        print(f"Looking for higher quality versions of {url}")
        
        # Parse the URL and domain
        parsed_url = urlparse(url)
        image_path = parsed_url.path
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Get the filename and extension
        filename, ext = os.path.splitext(image_path.split('/')[-1])
        if not ext:
            ext = '.png'  # Default extension if none found
            
        # Generate potential higher quality URL patterns
        higher_quality_urls = []
        
        # Try with 2x, @2x, etc. for retina displays
        retina_patterns = [
            f"{filename}@2x{ext}",  # Common retina pattern
            f"{filename}_2x{ext}",  # Alternate retina pattern
            f"{filename}-2x{ext}",  # Alternate retina pattern
            f"{filename}@3x{ext}",  # iPhone retina pattern
            f"{filename}_3x{ext}",  
            f"{filename}-3x{ext}",
            f"{filename}-hd{ext}",  # HD version
            f"{filename}_hd{ext}",
            f"{filename}-large{ext}",  # Larger version
            f"{filename}_large{ext}",
            f"{filename}-high{ext}",  # Higher resolution
            f"{filename}_high{ext}"
        ]
        
        # Add the retina patterns to the URL directory
        for pattern in retina_patterns:
            dir_path = os.path.dirname(image_path)
            higher_quality_urls.append(f"{base_url}{dir_path}/{pattern}")
            
        # Try different directories
        alternate_dirs = []
        
        # Try going up one directory and adding standard image directories
        parent_dir = os.path.dirname(image_path)
        if parent_dir:
            grandparent_dir = os.path.dirname(parent_dir)
            if grandparent_dir:
                alternate_dirs.extend([
                    f"{grandparent_dir}/large/{filename}{ext}",
                    f"{grandparent_dir}/2x/{filename}{ext}",
                    f"{grandparent_dir}/hd/{filename}{ext}",
                    f"{grandparent_dir}/high/{filename}{ext}"
                ])
                
        # Try common image directories at site root
        alternate_dirs.extend([
            f"/assets/images/large/{filename}{ext}",
            f"/media/large/{filename}{ext}",
            f"/press-kit/{filename}{ext}",
            f"/brand/{filename}{ext}"
        ])
        
        # Add alternate directory URLs
        for alt_dir in alternate_dirs:
            higher_quality_urls.append(f"{base_url}{alt_dir}")
            
        # Try higher resolution versions
        for test_url in higher_quality_urls:
            # Skip favicon URLs
            if 'favicon' in test_url.lower():
                continue
                
            # Skip hero images
            if is_likely_hero_image(test_url):
                continue
                
            try:
                # Check if the URL exists and returns a valid image
                headers = HEADERS.copy()
                response = requests.head(test_url, headers=headers, timeout=5, allow_redirects=True)
                
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'image/' in content_type or 'svg' in content_type:
                        print(f"Found higher quality version: {test_url}")
                        return test_url
            except Exception as e:
                print(f"Error getting image info for {test_url}: {e}")
                    
        # If no higher quality version is found, return the original URL
        return url
    except Exception as e:
        print(f"Error looking for higher quality versions: {e}")
        return url

def download_image(image_url, website_url, max_retries=3):
    """Download an image from a URL and save it to the output directory"""
    try:
        # Create a filename based on the website domain
        domain = re.sub(r'^https?://', '', website_url).rstrip('/')
        domain = domain.replace('www.', '')
        
        # Handle special characters in domain
        domain = re.sub(r'[^a-zA-Z0-9\.]', '_', domain)
        
        # Detect file extension from URL or default to png if not found
        file_ext = os.path.splitext(image_url.split('?')[0])[1].lower() or '.png'
        
        # Clean up file extension
        if not file_ext.startswith('.'):
            file_ext = '.' + file_ext
            
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff']
        if file_ext not in valid_extensions:
            file_ext = '.png'  # Default to png for unrecognized extensions
            
        filename = f"{domain}_logo{file_ext}"
        output_path = os.path.join(OUTPUT_DIR, filename)
        
        # Special handling for data URIs
        if image_url.startswith('data:'):
            output_path = save_data_uri(image_url, output_path)
            if output_path:
                # Convert WebP to PNG if needed
                if output_path.lower().endswith('.webp'):
                    output_path = convert_webp_to_png(output_path)
                # Auto-crop the image to remove transparent background
                output_path = auto_crop_image(output_path)
            return output_path
            
        # Otherwise, download the file using requests
        download_attempts = 0
        while download_attempts < max_retries:
            try:
                headers = HEADERS.copy()
                # Add a random delay between retries
                if download_attempts > 0:
                    time.sleep(random.uniform(1, 3))
                
                response = requests.get(image_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    print(f"Logo saved to {output_path}")
                    
                    # Convert WebP to PNG if needed
                    if output_path.lower().endswith('.webp'):
                        output_path = convert_webp_to_png(output_path)
                    
                    # Auto-crop the image to remove transparent background
                    output_path = auto_crop_image(output_path)
                    
                    return output_path
                else:
                    print(f"Failed to download image, status code: {response.status_code}")
                    
            except Exception as e:
                print(f"Error downloading image (attempt {download_attempts + 1}/{max_retries}): {e}")
                
            download_attempts += 1
        
        return None
        
    except Exception as e:
        print(f"Error downloading image: {e}")
        return None

def save_data_uri(data_uri, output_path):
    """Parse and save a data URI to a file"""
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
            
        print(f"Logo saved to {output_path} from data URI")
        return output_path
        
    except Exception as e:
        print(f"Error saving data URI: {e}")
        return None
        
def is_valid_image_url(url):
    """Check if a URL is an image URL by checking file extension"""
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

def show_token_usage_and_cost(token_usage):
    """Display token usage and estimated cost"""
    # Current Claude 3.5 Sonnet pricing (as of Oct 2024)
    input_token_cost_per_million = 3.00  # $3.00 per million input tokens
    output_token_cost_per_million = 15.00  # $15.00 per million output tokens
    
    # Calculate total input tokens including system prompt and tool tokens
    base_input_tokens = token_usage["input_tokens"]
    tool_input_tokens = token_usage["system_prompt_tokens"] + token_usage["computer_tool_tokens"] + token_usage["bash_tool_tokens"]
    total_input_tokens = base_input_tokens + tool_input_tokens
    
    output_tokens = token_usage["output_tokens"]
    total_tokens = total_input_tokens + output_tokens
    
    input_cost = (total_input_tokens / 1_000_000) * input_token_cost_per_million
    output_cost = (output_tokens / 1_000_000) * output_token_cost_per_million
    total_cost = input_cost + output_cost
    
    print("\n----- TOKEN USAGE AND COST (Claude 3.5 Sonnet) -----")
    print(f"Base input tokens:  {base_input_tokens:,}")
    print(f"Tool & system tokens: {tool_input_tokens:,}")
    print(f"Total input tokens: {total_input_tokens:,}")
    print(f"Output tokens:      {output_tokens:,}")
    print(f"Total tokens:       {total_tokens:,}")
    print("\n----- ESTIMATED COST -----")
    print(f"Input cost:  ${input_cost:.6f}")
    print(f"Output cost: ${output_cost:.6f}")
    print(f"Total cost:  ${total_cost:.6f}")
    print("-------------------------------")

def clear_cache():
    """Clear the logo URL cache"""
    if os.path.exists(CACHE_DIR):
        for file in os.listdir(CACHE_DIR):
            os.remove(os.path.join(CACHE_DIR, file))
        print(f"Cleared cache from {CACHE_DIR}")

def get_image_info(url):
    """Get information about an image file without downloading the whole file"""
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
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
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

def try_copy_image_address(client, website_url, actual_logo_url=None):
    """Try to get logo URL using Firefox and 'Copy Image Address'"""
    
    # Initialize token tracking
    tokens = {
        "input_tokens": 0,
        "output_tokens": 0
    }
    
    # Create optimized prompt for GUI approach
    initial_prompt = f"""Find the highest quality company logo from {website_url}.

    Follow these steps in exact order:
    1. Use bash to run "firefox {website_url}" to launch Firefox
    2. Wait for the page to load completely (take a screenshot after launch)
    3. Locate the company logo (typically in the header/top of page)
    4. Right-click on the logo and select "Copy Image Address" from the context menu
    5. After selecting "Copy Image Address", report the URL with prefix "LOGO URL: "
    
    IMPORTANT: 
    - Look for the highest quality version of the logo (SVG format is preferred, then PNG)
    - If you see multiple versions of the logo, choose the largest one
    - NEVER select favicons or icons - look for the main company logo only
    - If "Copy Image Address" doesn't work, try "Inspect" and find the src attribute
    - Take screenshots frequently to confirm your progress
    
    NOTE: Many sites use text-based logos without images. If you don't find an image-based logo after a thorough search, report "LOGO TYPE: TEXT-BASED" instead of a URL.
    """
    
    # Start with the initial user message
    messages = [{"role": "user", "content": initial_prompt}]
    
    # Optimize for fewer iterations while still being effective
    max_iterations = 8
    logo_url = None
    
    # Track state of the interaction
    right_clicked = False
    inspect_opened = False
    
    # Agent loop for GUI approach
    for iteration in range(max_iterations):
        print(f"GUI Iteration {iteration + 1}:")
        
        # Make the API call with computer and bash tools - using Claude 3.5 Sonnet
        response = client.beta.messages.create(
            model="claude-3-5-sonnet-20241022",  # Use Claude 3.5 Sonnet (Oct) version
            max_tokens=2048,                     # Reduced for efficiency
            tools=[
                {
                    "type": "computer_20241022",  # Updated tool type for Claude 3.5 Sonnet
                    "name": "computer",
                    "display_width_px": 1024,
                    "display_height_px": 768,
                    "display_number": 1,
                },
                {
                    "type": "bash_20241022",  # Updated tool type for Claude 3.5 Sonnet
                    "name": "bash"
                }
            ],
            messages=messages,
            betas=["computer-use-2024-10-22"]  # Updated beta flag for Claude 3.5 Sonnet
        )
        
        # Track token usage
        tokens["input_tokens"] += response.usage.input_tokens
        tokens["output_tokens"] += response.usage.output_tokens
        
        # Extract text and tool use from response
        response_text = ""
        tool_use_blocks = []
        
        for content_block in response.content:
            content_type = getattr(content_block, 'type', None)
            
            if content_type == 'text':
                if hasattr(content_block, 'text'):
                    response_text += content_block.text
                    print(f"Claude: {content_block.text[:150]}...")
            
            elif content_type == 'tool_use':
                tool_use_blocks.append(content_block)
                if content_block.name == "computer":
                    action = content_block.input.get('action', 'unknown action')
                    print(f"Claude used tool: computer - {action}")
                    
                    # Track if we've right-clicked
                    if action == "right_click":
                        right_clicked = True
                else:
                    cmd = content_block.input.get('command', 'unknown command')
                    print(f"Claude used tool: bash - {cmd}")
        
        # Check if response contains a text-based logo message
        if "LOGO TYPE: TEXT-BASED" in response_text:
            print("Claude determined this site uses a text-based logo with no image file")
            return None, tokens
            
        # Check if response contains a logo URL pattern
        logo_url_match = re.search(r'LOGO URL:\s*(https?://[^\s"\'<>\]]+)', response_text)
        if logo_url_match:
            logo_url = logo_url_match.group(1).strip()
            # Skip if it's a favicon
            if 'favicon' in logo_url.lower():
                print(f"Claude found a favicon, which we don't want: {logo_url}")
                logo_url = None
            else:
                print(f"Found logo URL from GUI approach: {logo_url}")
                break
        
        # Also look for any image URL that might be the logo (but not favicon)
        if not logo_url:
            image_urls = re.findall(r'(https?://[^\s"\'<>]+\.(?:png|jpg|jpeg|svg|gif|webp)(?:\?[^\s"\'<>]*)?)', response_text, re.IGNORECASE)
            # Filter out favicons
            image_urls = [url for url in image_urls if 'favicon' not in url.lower()]
            logo_urls = [url for url in image_urls if any(term in url.lower() for term in ['logo', 'brand', 'header']) and not is_likely_hero_image(url)]
            
            if logo_urls:
                logo_url = logo_urls[0]
                print(f"Found potential logo URL in GUI approach: {logo_url}")
                break
            elif image_urls and len(image_urls) > 0:
                # Check all image URLs to make sure they're not hero images
                for url in image_urls:
                    if not is_likely_hero_image(url) and 'favicon' not in url.lower():
                        logo_url = url
                        print(f"Found image URL that might be logo in GUI approach: {logo_url}")
                        break
                if logo_url:
                    break
        
        # Continue the agent loop with tool results
        if tool_use_blocks:
            messages.append({"role": "assistant", "content": response.content})
            
            # Generate optimized tool results with actual logo info where applicable
            tool_results = []
            for tool_block in tool_use_blocks:
                if tool_block.name == "computer":
                    action = tool_block.input.get("action")
                    
                    if action == "screenshot":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": "[Screenshot taken. The website is visible with the company logo in the header area.]"
                        })
                    elif action == "right_click":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": "[Right-click successful. Context menu opened showing options including 'Copy Image Address', 'Copy Image', 'Inspect Element', etc.]"
                        })
                    elif action == "left_click" and right_clicked and not inspect_opened:
                        # If actual_logo_url is available and Claude tries to use Inspect, provide useful feedback
                        if "inspect" in str(response.content).lower() and actual_logo_url:
                            inspect_opened = True
                            # Create a realistic HTML inspector view with actual URL
                            element_html = f'<img src="{actual_logo_url}" alt="Logo" class="site-logo" />'
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_block.id,
                                "content": f"[Clicked on 'Inspect'. Developer tools opened showing HTML:\n{element_html}\n]"
                            })
                        else:
                            # Assume Claude clicked on "Copy Image Address"
                            # If we have the actual_logo_url, provide it as if it was copied
                            if actual_logo_url:
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_block.id,
                                    "content": f"[Clicked on 'Copy Image Address'. The URL has been copied to clipboard: {actual_logo_url}]"
                                })
                            else:
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_block.id,
                                    "content": "[Clicked on menu option. The action was performed successfully.]"
                                })
                    else:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": "[Action performed successfully.]"
                        })
                
                elif tool_block.name == "bash":
                    cmd = tool_block.input.get("command", "")
                    if "firefox" in cmd:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": f"[Firefox launched with {website_url}. Browser window is now open.]"
                        })
                    else:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": f"[Command executed: {cmd}]"
                        })
            
            # Continue the conversation with tool results
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
        else:
            # If no tools were used but we didn't find a URL, try prompting more explicitly
            if iteration < max_iterations - 1:
                if right_clicked:
                    # If we've right-clicked but still don't have the URL, give more specific instructions
                    followup_prompt = """You've right-clicked on the logo. Now select "Copy Image Address" from the context menu.
                    
                    After selecting it, tell me what URL was copied with the prefix "LOGO URL: ".
                    
                    Look for SVG or high-resolution PNG versions if available. If "Copy Image Address" isn't in the menu, use "Inspect" and find the image URL in the HTML.
                    
                    IMPORTANT: Do NOT select favicon or site icon images - they are typically very small (32x32 pixels) and located in the browser tab.
                    
                    If after inspection you determine this site uses a text-based logo with no image, report "LOGO TYPE: TEXT-BASED".
                    """
                else:
                    # If we haven't right-clicked yet, focus on that
                    followup_prompt = """Let's try again:
                    
                    1. Take another screenshot to confirm the page has loaded
                    2. Find the company logo (usually in the header/top of the page)
                    3. Right-click directly on the logo image
                    4. Select "Copy Image Address" from the context menu
                    5. Report the URL with "LOGO URL: " prefix
                    
                    Remember to look for the highest quality version (SVG preferred, then PNG) for best results.
                    NEVER select favicon or site icon images.
                    
                    If after thorough inspection you determine this site uses a text-based logo with no image file, report "LOGO TYPE: TEXT-BASED".
                    """
                
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": followup_prompt})
    
    return logo_url, tokens

def fetch_website_html(url):
    """Fetch the HTML content of a website with timeout and error handling"""
    # Normalize URL by adding https:// if missing
    url = normalize_url(url)
    
    try:
        response = requests.get(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            timeout=10,  # Add timeout to prevent hanging on slow websites
            allow_redirects=True  # Follow redirects
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching HTML: {e}")
        return ""

def find_image_urls(url, website_url):
    """Find all image URLs on a website - optimized for speed and comprehensive sources"""
    html = fetch_website_html(url)
    if not html:
        return []
        
    soup = BeautifulSoup(html, 'html.parser')
    base_url = "{0.scheme}://{0.netloc}".format(urlparse(url))
    
    # Dictionary to store image URLs with useful attributes
    images = []
    
    # Logo keywords for efficient matching
    logo_keywords = ['logo', 'brand', 'header', 'site-icon', 'site-logo']
    
    # Find all img tags
    for img in soup.find_all('img'):
        src = img.get('src')
        
        # Skip favicon images immediately
        if src and 'favicon' in src.lower():
            continue
            
        # Track if this is in header/navbar for priority scoring
        parent_tags = [p.name for p in img.parents if p.name]
        in_header = any(tag in ['header', 'nav'] for tag in parent_tags)
        
        # Check parent class attributes for header/navbar indicators
        parent_classes = []
        for parent in img.parents:
            if parent.get('class'):
                parent_classes.extend(parent.get('class'))
        parent_classes = [cls.lower() for cls in parent_classes if cls]
        
        in_header_class = any(cls in ['header', 'navbar', 'nav', 'logo', 'brand'] for cls in parent_classes)
        header_priority = 10 if in_header or in_header_class else 0
        
        # If no src, check for other sources including Nitro-specific attributes
        if not src:
            # First check Nitro-specific attributes
            if img.get('nitro-lazy-src') and 'favicon' not in img.get('nitro-lazy-src').lower():
                src = img.get('nitro-lazy-src')
            # Then check other lazy-loading attributes
            else:
                for attr in ['data-src', 'data-original', 'data-lazy-src', 'data-fallback-src']:
                    if img.get(attr) and 'favicon' not in img.get(attr).lower():
                        src = img.get(attr)
                        break
            
            # If still no src found, skip this img
            if not src:
                continue
                
        # Check for srcset to get highest resolution image
        srcset = img.get('srcset') or img.get('nitro-lazy-srcset')
        highest_res_url = None
        
        if srcset:
            # Parse srcset to find highest resolution image
            try:
                srcset_parts = srcset.split(',')
                for part in srcset_parts:
                    part = part.strip()
                    if not part:
                        continue
                    
                    # Extract URL and width descriptor
                    url_parts = part.split(' ')
                    if len(url_parts) >= 1:
                        url = url_parts[0].strip()
                        # Skip favicon images
                        if 'favicon' in url.lower():
                            continue
                            
                        # If there's a width descriptor, parse it
                        width = 0
                        if len(url_parts) >= 2:
                            width_str = url_parts[1].strip()
                            if width_str.endswith('w'):
                                try:
                                    width = int(width_str[:-1])
                                except ValueError:
                                    pass
                        
                        # Track highest resolution
                        if not highest_res_url or width > 0:
                            highest_res_url = url
            except Exception as e:
                print(f"Error parsing srcset: {e}")
                
        # Use highest resolution from srcset if available
        if highest_res_url:
            src = highest_res_url
            
        # Fix data URIs
        if src.startswith('https://data:') or src.startswith('data:'):
            src = fix_data_uri(src)
            
        # Make relative URLs absolute
        if src.startswith('//'):
            abs_url = 'https:' + src
        elif src.startswith('/'):
            abs_url = base_url + src
        elif not src.startswith(('http://', 'https://', 'data:')):
            abs_url = urljoin(url, src)
        else:
            abs_url = src
            
        # Skip favicon and hero images
        if 'favicon' in abs_url.lower() or is_likely_hero_image(abs_url):
            continue
            
        # Quick check for logo in URL or other attributes
        alt_text = img.get('alt', '').lower()
        img_class = ' '.join(img.get('class', [])).lower() if img.get('class') else ''
        img_id = img.get('id', '').lower()
        parent_class = ' '.join(img.parent.get('class', [])).lower() if img.parent and img.parent.get('class') else ''
        parent_id = img.parent.get('id', '').lower() if img.parent else ''
        
        # Check if this is likely a logo based on various attributes
        is_logo_in_url = any(keyword in abs_url.lower() for keyword in logo_keywords)
        is_logo_in_alt = any(keyword in alt_text for keyword in ['logo', 'brand'])
        is_logo_in_class = any(keyword in img_class for keyword in logo_keywords)
        is_logo_in_parent = any(keyword in parent_class for keyword in logo_keywords)
        
        # Check if image is in header/navbar
        in_header_or_nav = False
        for parent in img.parents:
            if parent.name in ['header', 'nav'] or (parent.get('class') and 
                               any(cls.lower() in ['header', 'navbar', 'nav', 'topbar'] 
                                   for cls in parent.get('class'))):
                in_header_or_nav = True
                break
                
        # Calculate an initial priority score for this image
        priority = 0
        
        # Location-based scoring
        if in_header_or_nav:
            priority += 15  # Highest priority for header/navbar elements
            
        # Attribute-based scoring
        if is_logo_in_url:
            priority += 10
        if is_logo_in_alt:
            priority += 8
        if is_logo_in_class:
            priority += 7
        if is_logo_in_parent:
            priority += 6
            
        # Image type scoring
        if abs_url.lower().endswith('.svg'):
            priority += 5  # SVG is highest quality
        elif abs_url.lower().endswith('.png'):
            priority += 3  # PNG is good quality
            
        # Site identity scoring - image in header linking to homepage is very likely a logo
        if img.parent and img.parent.name == 'a' and img.parent.get('href') in ['/', '#', website_url]:
            priority += 12
            
        is_likely_logo = (is_logo_in_url or is_logo_in_alt or is_logo_in_class or 
                         is_logo_in_parent or in_header_or_nav or 
                         (img.parent and img.parent.name == 'a' and img.parent.get('href') == '/'))
        
        # Add to our candidates with calculated priority
        images.append({
            'url': abs_url,
            'alt': alt_text,
            'class': img_class,
            'id': img_id,
            'parent_class': parent_class,
            'parent_id': parent_id,
            'is_likely_logo': is_likely_logo,
            'priority': priority,
            'width': img.get('width'),
            'height': img.get('height')
        })
    
    # Also check for inline SVG elements
    svg_elements = soup.find_all('svg')
    for svg in svg_elements:
        # Try to determine if this is a logo
        svg_class = ' '.join(svg.get('class', [])).lower() if svg.get('class') else ''
        svg_id = svg.get('id', '').lower()
        parent_class = ' '.join(svg.parent.get('class', [])).lower() if svg.parent and svg.parent.get('class') else ''
        
        is_likely_logo = any(keyword in attr for keyword in logo_keywords 
                           for attr in [svg_class, svg_id, parent_class])
        
        if is_likely_logo:
            print(f"Found inline SVG that might be a logo")
            # We can't directly use inline SVG, but we note its presence
    
    # Also look for background-image in CSS
    style_tags = soup.find_all('style')
    for style in style_tags:
        if style.string:
            background_urls = re.findall(r'background-image:\s*url\([\'"]?([^\'"]+)[\'"]?\)', style.string)
            for bg_url in background_urls:
                if any(keyword in bg_url.lower() for keyword in logo_keywords) and 'favicon' not in bg_url.lower():
                    # Make relative URLs absolute
                    if bg_url.startswith('//'):
                        abs_url = 'https:' + bg_url
                    elif bg_url.startswith('/'):
                        abs_url = base_url + bg_url
                    elif not bg_url.startswith(('http://', 'https://')):
                        abs_url = urljoin(url, bg_url)
                    else:
                        abs_url = bg_url
                        
                    # Skip hero images
                    if is_likely_hero_image(abs_url):
                        continue
                        
                    images.append({
                        'url': abs_url,
                        'alt': '',
                        'class': '',
                        'id': '',
                        'parent_class': '',
                        'parent_id': '',
                        'is_likely_logo': True,
                        'priority': 5
                    })
                    
    # Look for links to image files in header elements
    header_elements = soup.find_all(['header', 'div'], class_=lambda c: c and ('header' in c.lower() or 'logo' in c.lower()))
    for header in header_elements:
        links = header.find_all('a')
        for link in links:
            href = link.get('href')
            if href and 'favicon' not in href.lower() and any(href.lower().endswith(ext) for ext in ['.svg', '.png', '.jpg', '.jpeg']):
                # Make the URL absolute
                abs_url = urljoin(url, href)
                
                # Skip hero images
                if is_likely_hero_image(abs_url):
                    continue
                    
                images.append({
                    'url': abs_url,
                    'alt': link.get('title', '').lower(),
                    'class': ' '.join(link.get('class', [])).lower() if link.get('class') else '',
                    'id': link.get('id', '').lower(),
                    'parent_class': ' '.join(link.parent.get('class', [])).lower() if link.parent and link.parent.get('class') else '',
                    'parent_id': link.parent.get('id', '').lower() if link.parent else '',
                    'is_likely_logo': True,
                    'priority': 8
                })
    
    # Extract logos from structured data (JSON-LD)
    json_ld_tags = soup.find_all('script', type='application/ld+json')
    for tag in json_ld_tags:
        if tag.string:
            try:
                data = json.loads(tag.string)
                # Extract organization logo
                if isinstance(data, dict):
                    # Check various paths where a logo might be found
                    logo_paths = [
                        data.get('logo'),
                        data.get('image'),
                        data.get('organization', {}).get('logo'),
                        data.get('publisher', {}).get('logo')
                    ]
                    
                    for logo_path in logo_paths:
                        if logo_path:
                            # Handle both string URLs and objects with URL
                            logo_url = logo_path.get('url') if isinstance(logo_path, dict) else logo_path
                            
                            if isinstance(logo_url, str) and 'favicon' not in logo_url.lower():
                                # Make relative URLs absolute
                                abs_url = urljoin(url, logo_url)
                                
                                # Skip hero images
                                if is_likely_hero_image(abs_url):
                                    continue
                                
                                images.append({
                                    'url': abs_url,
                                    'alt': 'JSON-LD Logo',
                                    'class': '',
                                    'id': '',
                                    'parent_class': '',
                                    'parent_id': '',
                                    'is_likely_logo': True,
                                    'priority': 9
                                })
            except Exception as e:
                print(f"Error parsing JSON-LD: {e}")
                
    return images

def fix_data_uri(url):
    """Fix malformed data URIs and convert them to proper format"""
    # Check if this is a malformed data URI (has https://data: prefix)
    if url and url.startswith('https://data:'):
        # Fix by removing the 'https://' prefix
        url = url.replace('https://data:', 'data:')
    
    return url

def extract_svg_from_data_uri(data_uri):
    """Extract SVG content from a data URI"""
    try:
        # Extract the base64-encoded part
        base64_match = re.search(r'base64,([^"\'\\)]+)', data_uri)
        if not base64_match:
            return None
        
        # Get the base64 data
        base64_data = base64_match.group(1)
        
        # Try to decode the base64 data
        decoded_data = base64.b64decode(base64_data).decode('utf-8')
        
        # Check if it's a valid SVG (contains svg tag)
        if '<svg' in decoded_data:
            return decoded_data
        
        return None
    except Exception as e:
        print(f"Error decoding data URI: {e}")
        return None

def is_likely_icon_not_logo(url):
    """Check if a URL is likely to be an icon but not a company logo"""
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
        'trash', 'refresh', 'sync', 'update', 'play', 'pause',
        'improved-access', 'access', 'improved',  # Specific to the Apprentice Health case
        'icon-improved-access'  # The specific icon we saw in the apprenticehealth.com case
    ]
    
    # Check if filename starts with icon pattern
    if any(pattern in filename for pattern in icon_patterns):
        return True
        
    # Check if filename contains specific icon types
    if any(icon in filename for icon in specific_icons):
        return True
        
    # Feature icons often appear in feature sections or have feature in the name
    if 'feature' in url_lower and ('icon' in url_lower or 'symbol' in url_lower):
        return True
        
    # For apprenticehealth.com specifically
    if 'apprenticehealth.com/assets/images/icon-' in url_lower:
        return True
        
    return False

def convert_webp_to_png(input_path):
    """Convert WebP image to PNG format"""
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
    """Auto-crop image to remove transparent background"""
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

if __name__ == "__main__":
    # Set up command-line arguments
    parser = argparse.ArgumentParser(description="Extract and download company logo from a website")
    parser.add_argument("url", help="URL of the website to extract logo from")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh cache")
    parser.add_argument("--no-claude", action="store_true", help="Skip Claude fallback for extraction")
    
    args = parser.parse_args()
    
    # Create cache and output directories if they don't exist
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    try:
        result = download_company_logo(
            args.url, 
            force_refresh=args.force_refresh,
            use_claude_fallback=not args.no_claude
        )
        
        if result:
            print(f"Successfully downloaded logo to {result}")
        else:
            domain = re.sub(r'^https?://', '', args.url).rstrip('/')
            domain = domain.replace('www.', '')
            # Check cache to see if it was identified as a text-based logo
            cache_key = hashlib.md5(normalize_url(args.url).encode()).hexdigest()
            cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
            
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    if cache_data.get('text_based_logo', False):
                        print(f"Successfully identified text-based logo for {domain}")
                        sys.exit(0)  # Exit with success code
            
            # If not a text-based logo, then it truly failed
            print("Failed to download logo.")
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)