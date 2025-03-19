#!/usr/bin/env python
import os
import sys
import re
import logging
import json
import traceback
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# Add parent directory to path so we can import logo_bot modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from logo_bot.config import CACHE_DIR
from logo_bot.monitoring.check_extractors import main as check_extractors, TEST_DOMAINS

# Configure logging
log_dir = os.path.join(CACHE_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "selector_update.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('selector_update')

# Path to Google extractor file
GOOGLE_EXTRACTOR_PATH = Path(__file__).parent.parent / 'extractors' / 'google.py'

def get_current_selectors():
    """Extract the current selectors from the Google extractor file"""
    with open(GOOGLE_EXTRACTOR_PATH, 'r') as f:
        content = f.read()
    
    # Find the selectors list in the fast extraction method
    selector_match = re.search(r'selectors\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if not selector_match:
        logger.error("Could not find selectors list in Google extractor file")
        return []
    
    selector_text = selector_match.group(1)
    # Extract individual selectors
    selectors = []
    for line in selector_text.split('\n'):
        # Extract string between quotes
        match = re.search(r'"([^"]+)"', line)
        if match:
            selectors.append(match.group(1))
    
    logger.info(f"Found {len(selectors)} current selectors: {selectors}")
    return selectors

def analyze_google_images_page():
    """Fetch Google Images page and analyze for possible selectors"""
    logger.info("Analyzing Google Images page for current selectors")
    
    # Use a test query
    query = "apple logo"
    url = f"https://www.google.com/search?q={query}&tbm=isch"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to fetch Google Images page: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all img tags
        img_tags = soup.find_all('img')
        
        # Analyze image tags and their classes
        img_classes = {}
        for img in img_tags:
            if img.get('class'):
                class_str = ' '.join(img.get('class'))
                selector = f"img.{class_str.replace(' ', '.')}"
                img_classes[selector] = img_classes.get(selector, 0) + 1
        
        # Find all divs that might contain images
        div_tags = soup.find_all('div')
        div_selectors = {}
        for div in div_tags:
            if div.find('img') and div.get('class'):
                class_str = ' '.join(div.get('class'))
                selector = f"div.{class_str.replace(' ', '.')} img"
                div_selectors[selector] = div_selectors.get(selector, 0) + 1
        
        # Combine results and sort by frequency
        all_selectors = {**img_classes, **div_selectors}
        sorted_selectors = sorted(all_selectors.items(), key=lambda x: x[1], reverse=True)
        
        # Filter to likely thumbnail selectors
        thumbnail_selectors = []
        for selector, count in sorted_selectors:
            # Keep only selectors with multiple occurrences
            if count >= 2 and len(selector) < 50:  # Avoid overly specific selectors
                thumbnail_selectors.append(selector)
        
        logger.info(f"Found {len(thumbnail_selectors)} potential selectors from page analysis")
        return thumbnail_selectors[:10]  # Return top 10 selectors
        
    except Exception as e:
        logger.error(f"Error analyzing Google Images page: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def update_selectors_in_file(selectors):
    """Update the selectors in the Google extractor file"""
    with open(GOOGLE_EXTRACTOR_PATH, 'r') as f:
        content = f.read()
    
    # Format the new selectors list
    selectors_str = ',\n                '.join([f'"{s}"  # Auto-updated' for s in selectors])
    new_selectors_block = f"""            selectors = [
                {selectors_str}
            ]"""
    
    # Replace the selectors list in the file
    updated_content = re.sub(
        r'selectors\s*=\s*\[.*?\]',
        new_selectors_block,
        content, 
        flags=re.DOTALL
    )
    
    # Backup the original file
    backup_path = str(GOOGLE_EXTRACTOR_PATH) + '.bak'
    with open(backup_path, 'w') as f:
        f.write(content)
    
    # Write the updated content
    with open(GOOGLE_EXTRACTOR_PATH, 'w') as f:
        f.write(updated_content)
    
    logger.info(f"Updated selectors in {GOOGLE_EXTRACTOR_PATH}")
    logger.info(f"Original file backed up to {backup_path}")

def main():
    """Main function to update selectors if needed"""
    logger.info("Starting selector update check")
    
    # First check if extractors are working
    is_working = check_extractors()
    
    if not is_working:
        logger.info("Google extractor is not working well, attempting to update selectors")
        
        # Get current selectors
        current_selectors = get_current_selectors()
        
        # Get potential new selectors from page analysis
        new_selectors = analyze_google_images_page()
        
        # Combine current and new selectors, keeping current ones first
        updated_selectors = current_selectors.copy()
        for selector in new_selectors:
            if selector not in updated_selectors:
                updated_selectors.append(selector)
        
        # Limit to a reasonable number
        updated_selectors = updated_selectors[:10]
        
        if updated_selectors != current_selectors:
            logger.info(f"Updating selectors from {len(current_selectors)} to {len(updated_selectors)}")
            update_selectors_in_file(updated_selectors)
            
            # Test if the update fixed the issue
            logger.info("Testing updated selectors")
            is_fixed = check_extractors()
            
            if is_fixed:
                logger.info("✅ Selector update was successful!")
            else:
                logger.warning("❌ Selector update did not fix the issue")
        else:
            logger.info("No new selectors found to update")
    else:
        logger.info("Google extractor is working well, no need to update selectors")
    
    logger.info("Selector update check completed")

if __name__ == "__main__":
    main() 