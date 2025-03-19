import os
import time
import re
import json
import requests
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from urllib.parse import urlparse, quote_plus
import random
import traceback
import base64

# Import config first to ensure constants are available
from ..config import OUTPUT_DIR, CACHE_DIR, HEADERS

# Add Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium not installed. Advanced Google extraction will be limited.")

from .base import BaseExtractor
from ..utils import url as url_utils
from ..utils import cache as cache_utils
from ..utils import image as image_utils


class GoogleExtractor(BaseExtractor):
    """
    Logo extractor using Google Image Search
    
    This class extracts logos from Google Image Search results
    using direct HTTP requests or browser automation.
    """
    
    def __init__(self, website_url, chromedriver_path=None):
        """
        Initialize the Google extractor
        
        Args:
            website_url (str): URL of the website to extract logo from
            chromedriver_path (str): Path to the ChromeDriver executable (optional)
        """
        super().__init__(website_url)
        self.domain = url_utils.get_domain_name(website_url)
        self.chromedriver_path = chromedriver_path
        
    def _create_folder_if_not_exists(self, folder_path):
        """Create folder if it doesn't exist"""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

    def _download_image(self, image_url, output_path):
        """
        Download an image from a URL and save it to a file
        
        Args:
            image_url (str): URL of the image to download
            output_path (str): Path to save the image to
            
        Returns:
            str: Path to the downloaded image, or None on error
        """
        # Try multiple strategies to download the image, with different headers and approaches
        download_strategies = [
            self._download_with_standard_headers,
            self._download_with_browser_headers,
            self._download_with_selenium,
            self._download_with_advanced_selenium  # Add new advanced strategy
        ]
        
        for i, strategy in enumerate(download_strategies):
            try:
                print(f"Trying download strategy {i+1}/{len(download_strategies)} for {image_url}")
                result = strategy(image_url, output_path)
                if result:
                    print(f"Successfully downloaded image using strategy {i+1}")
                    return result
            except Exception as e:
                print(f"Strategy {i+1} failed: {str(e)}")
                continue
        
        print(f"All download strategies failed for {image_url}")
        return None
    
    def _download_with_standard_headers(self, image_url, output_path):
        """Simple download strategy with minimal headers"""
        try:
            headers = HEADERS.copy()
            
            response = requests.get(image_url, headers=headers, stream=True, timeout=10)
            return self._process_download_response(response, image_url, output_path)
        except Exception as e:
            print(f"Standard download failed: {str(e)}")
            return None
    
    def _download_with_browser_headers(self, image_url, output_path):
        """Download with full browser headers to mimic a real browser"""
        try:
            parsed_url = urlparse(image_url)
            domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # More comprehensive headers that mimic a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Referer': domain,
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
                'Cache-Control': 'max-age=0',
                'DNT': '1',
            }
            
            session = requests.Session()
            # First visit the referring domain to set cookies
            try:
                session.get(domain, headers=headers, timeout=5)
            except:
                pass  # Ignore errors here, just trying to set cookies
                
            # Now get the image
            response = session.get(image_url, headers=headers, stream=True, timeout=10)
            return self._process_download_response(response, image_url, output_path)
        except Exception as e:
            print(f"Browser headers download failed: {str(e)}")
            return None
    
    def _download_with_selenium(self, image_url, output_path):
        """Use Selenium to download the image if available"""
        if not SELENIUM_AVAILABLE:
            print("Selenium not available, skipping this strategy")
            return None
            
        try:
            # Initialize Chrome WebDriver
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            service = ChromeService(executable_path=self.chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            try:
                # Navigate directly to the image URL
                driver.get(image_url)
                
                # Wait for the image to load
                time.sleep(5)
                
                # Get the page source which should be just the image
                page_source = driver.page_source
                
                # For images loaded directly, take a screenshot
                image_path_with_ext = f"{os.path.splitext(output_path)[0]}.png"
                driver.save_screenshot(image_path_with_ext)
                
                # Verify this is actually an image by trying to open it
                try:
                    img = Image.open(image_path_with_ext)
                    img.verify()  # Verify it's a valid image
                    print(f"Successfully saved screenshot to {image_path_with_ext}")
                    return image_path_with_ext
                except:
                    # Not a valid image, remove the file
                    if os.path.exists(image_path_with_ext):
                        os.remove(image_path_with_ext)
                        
                    # Try to find an img tag and get its source
                    img_elements = driver.find_elements(By.TAG_NAME, "img")
                    if img_elements:
                        img_src = img_elements[0].get_attribute("src")
                        if img_src and img_src.startswith("data:image"):
                            # Handle data URI
                            try:
                                data_uri = img_src
                                header, encoded = data_uri.split(",", 1)
                                data = BytesIO(base64.b64decode(encoded))
                                image = Image.open(data)
                                
                                # Determine extension
                                if "png" in header:
                                    ext = "png"
                                elif "jpeg" in header or "jpg" in header:
                                    ext = "jpg" 
                                else:
                                    ext = "png"
                                    
                                image_path_with_ext = f"{os.path.splitext(output_path)[0]}.{ext}"
                                image.save(image_path_with_ext)
                                return image_path_with_ext
                            except Exception as e:
                                print(f"Error saving data URI: {str(e)}")
            finally:
                driver.quit()
                
            return None
        except Exception as e:
            print(f"Selenium download failed: {str(e)}")
            return None
    
    def _download_with_advanced_selenium(self, image_url, output_path):
        """
        Advanced Selenium strategy that mimics a user visiting the page and downloading the image
        This works better for sites with strict anti-scraping measures
        """
        if not SELENIUM_AVAILABLE:
            print("Selenium not available, skipping advanced Selenium strategy")
            return None
            
        try:
            # Initialize Chrome with download settings
            chrome_options = Options()
            # Don't run headless for this approach to handle more complex scenarios
            # chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")  # Hide automation
            
            # Set user agent to look like a real browser
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            # Prepare download path
            image_dir = os.path.dirname(output_path)
            
            service = ChromeService(executable_path=self.chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            try:
                # First try to visit the referring domain to establish cookies
                parsed_url = urlparse(image_url)
                domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
                
                print(f"Visiting domain: {domain}")
                driver.get(domain)
                time.sleep(2)  # Let the page load and cookies establish
                
                # Now navigate to the image URL
                print(f"Navigating to image URL: {image_url}")
                driver.get(image_url)
                time.sleep(3)  # Give more time for protected images to load
                
                # Try multiple approaches to get the image
                
                # 1. First, try to find and capture the image element directly
                img_elements = driver.find_elements(By.TAG_NAME, "img")
                if img_elements and len(img_elements) > 0:
                    print("Found image element on page")
                    for i, img in enumerate(img_elements):
                        try:
                            # Scroll to make sure the image is in view
                            driver.execute_script("arguments[0].scrollIntoView(true);", img)
                            time.sleep(1)
                            
                            # Try to get the image source
                            src = img.get_attribute("src")
                            if src:
                                print(f"Found image source: {src}")
                                
                                # Handle data URIs
                                if src.startswith("data:image"):
                                    try:
                                        header, encoded = src.split(",", 1)
                                        data = BytesIO(base64.b64decode(encoded))
                                        image = Image.open(data)
                                        
                                        # Determine extension
                                        if "png" in header:
                                            ext = "png"
                                        elif "jpeg" in header or "jpg" in header:
                                            ext = "jpg" 
                                        else:
                                            ext = "png"
                                            
                                        image_path_with_ext = f"{os.path.splitext(output_path)[0]}.{ext}"
                                        image.save(image_path_with_ext)
                                        return image_path_with_ext
                                    except Exception as e:
                                        print(f"Error saving data URI: {str(e)}")
                                
                                # Check if the image has good dimensions
                                try:
                                    width = int(img.get_attribute("width") or 0)
                                    height = int(img.get_attribute("height") or 0)
                                    
                                    # Take screenshot of the image element if it has reasonable dimensions
                                    if width > 50 and height > 50:
                                        # Take a screenshot of this specific element
                                        print(f"Taking screenshot of image element {i+1}")
                                        image_path_with_ext = f"{os.path.splitext(output_path)[0]}.png"
                                        img.screenshot(image_path_with_ext)
                                        
                                        # Verify it's a valid image
                                        try:
                                            Image.open(image_path_with_ext).verify()
                                            return image_path_with_ext
                                        except Exception as verify_error:
                                            print(f"Screenshot verification failed: {str(verify_error)}")
                                            if os.path.exists(image_path_with_ext):
                                                os.remove(image_path_with_ext)
                                except Exception as dim_error:
                                    print(f"Error getting image dimensions: {str(dim_error)}")
                            
                        except Exception as element_error:
                            print(f"Error processing image element {i+1}: {str(element_error)}")
                
                # 2. If we couldn't extract from img elements, try using JavaScript to download it
                try:
                    print("Trying JavaScript download method")
                    image_path_with_ext = f"{os.path.splitext(output_path)[0]}.png"
                    
                    # JavaScript to create a canvas from the image and download it
                    js_script = f"""
                    var img = document.querySelector('img');
                    if(img) {{
                        var canvas = document.createElement('canvas');
                        canvas.width = img.naturalWidth;
                        canvas.height = img.naturalHeight;
                        canvas.getContext('2d').drawImage(img, 0, 0);
                        
                        // Create a data URL and download it
                        var dataURL = canvas.toDataURL('image/png');
                        return dataURL;
                    }}
                    return null;
                    """
                    
                    data_url = driver.execute_script(js_script)
                    if data_url and data_url.startswith('data:image'):
                        header, encoded = data_url.split(",", 1)
                        data = BytesIO(base64.b64decode(encoded))
                        image = Image.open(data)
                        image.save(image_path_with_ext)
                        
                        # Verify this is a valid image with content
                        if os.path.getsize(image_path_with_ext) > 1000:
                            return image_path_with_ext
                        else:
                            os.remove(image_path_with_ext)  # Remove empty/invalid image
                            print("Downloaded image was too small or invalid")
                except Exception as js_error:
                    print(f"JavaScript download failed: {str(js_error)}")
                
                # 3. Last resort: Take a full page screenshot and post-process
                try:
                    print("Taking full page screenshot as last resort")
                    image_path_with_ext = f"{os.path.splitext(output_path)[0]}.png"
                    driver.save_screenshot(image_path_with_ext)
                    
                    # Check if this actually got us a valid image
                    if os.path.exists(image_path_with_ext) and os.path.getsize(image_path_with_ext) > 5000:
                        img = Image.open(image_path_with_ext)
                        # If we got just a basic error page, this won't help
                        if img.width > 200 and img.height > 200:
                            return image_path_with_ext
                        else:
                            os.remove(image_path_with_ext)
                except Exception as screenshot_error:
                    print(f"Full screenshot failed: {str(screenshot_error)}")
                    
            finally:
                driver.quit()
                
            return None
        except Exception as e:
            print(f"Advanced Selenium download failed: {str(e)}")
            traceback.print_exc()
            return None
    
    def _process_download_response(self, response, image_url, output_path):
        """Process the download response and save the image if valid"""
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '').lower()
            
            # Check if the content is an image
            is_image = False
            if 'image' in content_type:
                is_image = True
            elif content_type in ['application/octet-stream', 'binary/octet-stream']:
                # Some servers don't set the correct content type, try to determine from URL
                if any(ext in image_url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']):
                    is_image = True
            
            if is_image or len(response.content) > 1000:  # Likely a valid image if size is substantial
                # Determine file extension based on content type or URL
                if 'png' in content_type or '.png' in image_url.lower():
                    ext = 'png'
                elif 'jpeg' in content_type or 'jpg' in content_type or '.jpg' in image_url.lower() or '.jpeg' in image_url.lower():
                    ext = 'jpg'
                elif 'gif' in content_type or '.gif' in image_url.lower():
                    ext = 'gif'
                elif 'svg' in content_type or '.svg' in image_url.lower():
                    ext = 'svg'
                elif 'webp' in content_type or '.webp' in image_url.lower():
                    ext = 'webp'
                else:
                    ext = 'png'  # Default to PNG if unsure
                
                image_path_with_ext = f"{os.path.splitext(output_path)[0]}.{ext}"
                
                # For SVG, save directly without using PIL
                if ext == 'svg':
                    with open(image_path_with_ext, 'wb') as f:
                        for chunk in response.iter_content(8192):
                            f.write(chunk)
                    return image_path_with_ext
                else:
                    # For other image types, use PIL
                    try:
                        image = Image.open(BytesIO(response.content))
                        image.save(image_path_with_ext)
                        return image_path_with_ext
                    except UnidentifiedImageError:
                        print(f"PIL could not identify the image from {image_url}")
                        # Fallback: save the raw content
                        try:
                            with open(image_path_with_ext, 'wb') as f:
                                for chunk in response.iter_content(8192):
                                    f.write(chunk)
                            # Verify it's an actual image
                            try:
                                Image.open(image_path_with_ext).verify()
                                return image_path_with_ext
                            except:
                                # Not a valid image, remove the file
                                if os.path.exists(image_path_with_ext):
                                    os.remove(image_path_with_ext)
                                return None
                        except Exception as save_error:
                            print(f"Error saving raw content: {str(save_error)}")
                            return None
            else:
                print(f"The URL does not point to a valid image: {image_url} (Content-Type: {content_type})")
                return None
        else:
            print(f"Failed to download image, status code: {response.status_code}")
            return None

    def _get_image_file_size(self, image_path):
        """Get file size of an image"""
        return os.path.getsize(image_path) if os.path.exists(image_path) else 0

    def _extract_logo_urls_with_selenium(self, search_query):
        """Use Selenium to extract logo URLs from Google Images."""
        try:
            # Initialize Chrome WebDriver
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            service = ChromeService(executable_path=self.chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Set timeout for finding elements
            wait = WebDriverWait(driver, 3)
            
            # Format the search query for the URL
            formatted_query = search_query.replace(" ", "+")
            url = f"https://www.google.com/search?q={formatted_query}&tbm=isch"
            
            print(f"Search query: {search_query}")
            print(f"Navigating to Google Images search URL: {url}")
            
            # Navigate to Google Images
            driver.get(url)
            
            # Wait for the image thumbnails to load
            # First try to find the clickable parent containers instead of just the images
            try:
                thumbs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.eA0Zlc.WghbWd")))
                print(f"Found {len(thumbs)} thumbnail containers")
            except:
                # Fall back to previous selectors if the main one doesn't work
                possible_selectors = [
                    "div[jsname='dTDiAc']",
                    "div.eA0Zlc", 
                    "div.eA0Zlc.WghbWd",
                    "div.eA0Zlc.WghbWd.FnEtTd",
                    "div.WghbWd img",
                    "div.FnEtTd img",
                    "div[jsname='dTDiAc'] img",
                    "div.wH6SXe img"
                ]
                
                for selector in possible_selectors:
                    try:
                        print(f"Trying selector: {selector}")
                        thumbs = driver.find_elements(By.CSS_SELECTOR, selector)
                        if thumbs and len(thumbs) > 0:
                            print(f"Found {len(thumbs)} thumbnail results using selector: {selector}")
                            break
                    except Exception as e:
                        print(f"Error with selector {selector}: {str(e)}")
                        continue
            
            high_quality_urls = []
            image_data = []  # Store image data with dimensions when available
            
            # Process the first 3 images (or fewer if less are available)
            max_images = min(3, len(thumbs))
            for i in range(max_images):
                try:
                    print(f"Clicking on thumbnail #{i+1}")
                    
                    # Try multiple click methods until one works
                    try:
                        # Method 1: Standard click
                        thumbs[i].click()
                    except Exception as e1:
                        try:
                            # Method 2: JavaScript click
                            driver.execute_script("arguments[0].click();", thumbs[i])
                        except Exception as e2:
                            try:
                                # Method 3: Action chains
                                ActionChains(driver).move_to_element(thumbs[i]).click().perform()
                            except Exception as e3:
                                # Method 4: Find clickable child element
                                try:
                                    clickable = thumbs[i].find_element(By.CSS_SELECTOR, "a, div[role='button'], div.F0uyec")
                                    driver.execute_script("arguments[0].click();", clickable)
                                except Exception as e4:
                                    print(f"All click methods failed: {str(e1)}, {str(e2)}, {str(e3)}, {str(e4)}")
                                    continue
                    
                    # Wait for the larger image to appear with multiple possible selectors
                    try:
                        # Give a moment for the image to fully load
                        time.sleep(3)
                        
                        # Print page title to confirm we're in the image viewer
                        print(f"Current page title: {driver.title}")
                        
                        # Initialize found_url flag for this iteration
                        found_url = False
                        
                        # Focus on the main image first since we know the exact class
                        try:
                            # Primary selector - exactly matching what we're seeing
                            main_img = driver.find_element(By.CSS_SELECTOR, "img.sFlh5c.FyHeAf.iPVvYb")
                            if main_img:
                                src = main_img.get_attribute("src")
                                if src and src.startswith("http") and not src.startswith("data:"):
                                    # Skip Google's own logos
                                    if "google" in src.lower() or "gstatic" in src.lower():
                                        print(f"Skipping Google's own logo: {src}")
                                    else:
                                        print(f"Found primary image URL: {src}")
                                        if self._is_valid_url(src):
                                            # Try to get image dimensions
                                            width = None
                                            height = None
                                            try:
                                                width = int(main_img.get_attribute("width") or 0)
                                                height = int(main_img.get_attribute("height") or 0)
                                            except:
                                                pass
                                            
                                            # Add image data with dimensions and format
                                            image_format = self._get_image_format_from_url(src)
                                            image_data.append({
                                                'url': src,
                                                'width': width,
                                                'height': height,
                                                'format': image_format
                                            })
                                            
                                            high_quality_urls.append(src)
                                            found_url = True
                                        else:
                                            print(f"Skipping invalid URL: {src}")
                        except Exception as e:
                            print(f"Could not find primary image element: {str(e)}")
                        
                        # If primary method didn't work, try alternatives
                        if not found_url:
                            # Try different selectors for the high-quality image
                            possible_selectors = [
                                "img.sFlh5c.FyHeAf.iPVvYb",  # Exact match for what user is seeing
                                "img.sFlh5c",  # More general selector
                                "div.p7sI2 img",  # Parent div's img
                                "a.YsLeY img",  # Another parent selector
                                "img.r48jcc.pT0Scc.iPVvYb",  # Previous common one
                                "div.v4dQwb img:not([class*='Q4LuWd'])",  # Alternative
                                "a.eHAdSb img",  # Another alternative
                                "img.n3VNCb.KAlRDb",  # Another possibility
                                "div[jsname='UQIr0'] img",  # New possible container
                                "div[jsname='figiqf'] img"  # From the HTML example
                            ]
                            
                            for selector in possible_selectors:
                                try:
                                    print(f"Trying selector: {selector}")
                                    img_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                    print(f"Found {len(img_elements)} elements with selector {selector}")
                                    
                                    if img_elements and len(img_elements) > 0:
                                        # Get the source URL from the image
                                        for img in img_elements:
                                            try:
                                                src = img.get_attribute("src")
                                                print(f"Found image src: {src}")
                                                
                                                if src and src.startswith("http") and not src.startswith("data:"):
                                                    # Skip Google's own logos
                                                    if "google" in src.lower() or "gstatic" in src.lower():
                                                        print(f"Skipping Google's own logo: {src}")
                                                        continue
                                                    
                                                    if self._is_valid_url(src):
                                                        # Try to get image dimensions
                                                        width = None
                                                        height = None
                                                        try:
                                                            width = int(img.get_attribute("width") or 0)
                                                            height = int(img.get_attribute("height") or 0)
                                                        except:
                                                            pass
                                                        
                                                        # Add image data with dimensions and format
                                                        image_format = self._get_image_format_from_url(src)
                                                        image_data.append({
                                                            'url': src,
                                                            'width': width,
                                                            'height': height,
                                                            'format': image_format
                                                        })
                                                        
                                                        high_quality_urls.append(src)
                                                        print(f"Found high-quality image URL: {src}")
                                                        found_url = True
                                                        break
                                            except Exception as img_error:
                                                print(f"Error getting src attribute: {str(img_error)}")
                                                continue
                                        
                                        if found_url:
                                            break  # Break once we've found a working URL
                                except Exception as selector_error:
                                    print(f"Error with image selector {selector}: {str(selector_error)}")
                                    continue
                        
                        # If no URL was found, try to extract it from page source
                        if not found_url:
                            try:
                                # Extract the direct image URL from the page
                                # Look for high-resolution URLs in the page source
                                page_source = driver.page_source
                                
                                # If specific pattern didn't work, try more general approaches
                                if not found_url:
                                    # First try to extract URLs from imgres redirects
                                    imgres_pattern = r'imgurl=([^&]+)'
                                    imgres_matches = re.findall(imgres_pattern, page_source)
                                    
                                    if imgres_matches:
                                        for match in imgres_matches:
                                            import urllib.parse
                                            url = urllib.parse.unquote(match)
                                            if url.startswith('http') and ('logo' in url.lower() or self.domain in url.lower()):
                                                # Skip Google's own logos
                                                if "google" in url.lower() or "gstatic" in url.lower():
                                                    print(f"Skipping Google's own logo from imgres: {url}")
                                                    continue
                                                    
                                                # Add image URL without knowing dimensions
                                                image_format = self._get_image_format_from_url(url)
                                                image_data.append({
                                                    'url': url,
                                                    'width': None,
                                                    'height': None,
                                                    'format': image_format
                                                })
                                                
                                                high_quality_urls.append(url)
                                                print(f"Found image URL from imgres: {url}")
                                                found_url = True
                                                break
                                    
                                    # If no imgres URL was found, try direct image URLs
                                    if not found_url:
                                        # First, look specifically for likely logo URLs
                                        logo_pattern = r'(https?://[^"\']+/[^"\']*logo[^"\']*\.(png|jpg|jpeg|svg|webp))'
                                        logo_matches = re.findall(logo_pattern, page_source)
                                        
                                        if logo_matches:
                                            for match in logo_matches:
                                                url = match[0]
                                                # Skip Google's own logos
                                                if "google" in url.lower() or "gstatic" in url.lower():
                                                    print(f"Skipping Google's own logo: {url}")
                                                    continue
                                                    
                                                # Add image URL with format extracted from URL
                                                image_format = match[1]
                                                image_data.append({
                                                    'url': url,
                                                    'width': None,
                                                    'height': None,
                                                    'format': image_format
                                                })
                                                
                                                high_quality_urls.append(url)
                                                print(f"Found logo URL from page source: {url}")
                                                found_url = True
                                                break
                                        
                                        # If still no URL found, try any image URL
                                        if not found_url:
                                            url_pattern = r'(https?://[^"\']+\.(png|jpg|jpeg|svg|webp))'
                                            matches = re.findall(url_pattern, page_source)
                                            
                                            if matches:
                                                for match in matches:
                                                    url = match[0]
                                                    # Skip Google's own logos and icons
                                                    if "google" in url.lower() or "gstatic" in url.lower():
                                                        continue
                                                    
                                                    if self.domain in url.lower():
                                                        # Add image URL with format extracted from URL
                                                        image_format = match[1]
                                                        image_data.append({
                                                            'url': url,
                                                            'width': None,
                                                            'height': None,
                                                            'format': image_format
                                                        })
                                                        
                                                        high_quality_urls.append(url)
                                                        print(f"Found domain-matching image URL from page source: {url}")
                                                        found_url = True
                                                        break
                            except Exception as page_error:
                                print(f"Error extracting URL from page source: {str(page_error)}")
                                
                        # Additional fallback: Try to get an image URL from the current URL
                        if not found_url:
                            try:
                                current_url = driver.current_url
                                if "imgurl=" in current_url:
                                    import urllib.parse
                                    url_param = re.search(r'imgurl=([^&]+)', current_url)
                                    if url_param:
                                        url = urllib.parse.unquote(url_param.group(1))
                                        if url.startswith('http'):
                                            # Add image URL with format
                                            image_format = self._get_image_format_from_url(url)
                                            image_data.append({
                                                'url': url,
                                                'width': None,
                                                'height': None,
                                                'format': image_format
                                            })
                                            
                                            high_quality_urls.append(url)
                                            print(f"Found image URL from current URL: {url}")
                                            found_url = True
                            except Exception as url_error:
                                print(f"Error extracting URL from current URL: {str(url_error)}")
                    
                    except TimeoutException:
                        print("Timed out waiting for image to appear")
                        # Continue with next steps anyway
                    
                    # Close the image viewer to go back to search results
                    # Find and click the close button
                    try:
                        close_buttons = driver.find_elements(By.CSS_SELECTOR, "button[aria-label='Close'], a.hm60ue")
                        if close_buttons:
                            driver.execute_script("arguments[0].click();", close_buttons[0])
                        else:
                            # If can't find close button, press ESC key
                            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    except Exception as close_error:
                        print(f"Error closing image viewer: {str(close_error)}")
                        # Try ESC key as fallback
                        try:
                            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                        except:
                            pass
                    
                    # Wait a moment for the UI to return to the grid view
                    time.sleep(1)
                
                except Exception as e:
                    print(f"Error processing thumbnail {i+1}: {str(e)}")
                    # Continue with the next thumbnail
            
            print(f"Closed Chrome WebDriver")
            driver.quit()
            
            # If we have image data, use it for prioritization, otherwise use the high_quality_urls directly
            if image_data:
                # Import the should_prefer_png function from utils.qa
                try:
                    from ..utils.qa import should_prefer_png
                    has_preference_function = True
                except ImportError:
                    has_preference_function = False
                
                # First, filter out any duplicates and invalid URLs
                filtered_image_data = []
                seen_urls = set()
                
                for img in image_data:
                    url = img['url']
                    
                    # Skip Google's own logos, icons, redirects, and duplicates
                    if (any(pattern in url.lower() for pattern in ["google", "gstatic", "googleusercontent", "fonts.googleapis"]) or
                        any(pattern in url.lower() for pattern in ["icon", "favicon"]) or
                        "imgres?" in url or "url?" in url or
                        url in seen_urls):
                        continue
                    
                    # Only include valid URLs
                    if url.startswith('http'):
                        filtered_image_data.append(img)
                        seen_urls.add(url)
                
                # Now apply advanced prioritization
                prioritized_image_data = []
                remaining_image_data = filtered_image_data.copy()
                
                # Look for SVG images first (absolute top priority)
                svg_images = [img for img in remaining_image_data if img['format'] and img['format'].lower() == 'svg']
                if svg_images:
                    # SVGs found, always use them first
                    print("Found SVG images - prioritizing these first (gold standard)")
                    for img in svg_images:
                        prioritized_image_data.append(img)
                        if img in remaining_image_data:
                            remaining_image_data.remove(img)
                
                # Apply domain-based prioritization as before
                # Priority 1: Company domain + 'logo' in filename
                domain_logo_images = [img for img in remaining_image_data 
                                    if self.domain in img['url'].lower() and 'logo' in img['url'].lower()]
                
                for img in domain_logo_images:
                    if img in remaining_image_data:
                        prioritized_image_data.append(img)
                        remaining_image_data.remove(img)
                        print(f"Priority 1 - Domain+Logo URL: {img['url']}")
                
                # Priority 2: Any URL from company domain
                domain_images = [img for img in remaining_image_data if self.domain in img['url'].lower()]
                for img in domain_images:
                    if img in remaining_image_data:
                        prioritized_image_data.append(img)
                        remaining_image_data.remove(img)
                        print(f"Priority 2 - Domain URL: {img['url']}")
                
                # Priority 3: URLs with 'logo' in path (excluding social media)
                social_domains = ["twitter.com", "facebook.com", "linkedin.com", "instagram.com", 
                                "youtube.com", "pinterest.com", "tumblr.com"]
                
                logo_images = [img for img in remaining_image_data 
                            if 'logo' in img['url'].lower() 
                            and not any(social in img['url'].lower() for social in social_domains)]
                
                for img in logo_images:
                    if img in remaining_image_data:
                        prioritized_image_data.append(img)
                        remaining_image_data.remove(img)
                        print(f"Priority 3 - Logo URL: {img['url']}")
                
                # Priority 4: Remaining URLs (excluding social media)
                other_images = [img for img in remaining_image_data 
                             if not any(social in img['url'].lower() for social in social_domains)]
                
                for img in other_images:
                    prioritized_image_data.append(img)
                    print(f"Priority 4 - Other URL: {img['url']}")
                
                # Apply PNG preference logic if we have the function and dimensions
                if has_preference_function and len(prioritized_image_data) > 1:
                    # Look for potential PNG preference candidates
                    png_images = [img for img in prioritized_image_data 
                                if img['format'] and img['format'].lower() == 'png']
                    other_images = [img for img in prioritized_image_data 
                                  if img['format'] and img['format'].lower() in ['jpg', 'jpeg', 'webp']]
                    
                    if png_images and other_images:
                        # Check for cases where PNG should be preferred over similar-sized JPG/WEBP
                        for png_img in png_images:
                            for other_img in other_images:
                                # Skip if either doesn't have dimensions
                                if not (png_img.get('width') and png_img.get('height') and 
                                        other_img.get('width') and other_img.get('height')):
                                    continue
                                
                                # If dimensions are similar and PNG is not already higher priority
                                png_idx = prioritized_image_data.index(png_img)
                                other_idx = prioritized_image_data.index(other_img)
                                
                                if other_idx < png_idx and should_prefer_png(png_img, other_img):
                                    print(f"Promoting PNG ({png_img['url']}) over {other_img['format']} ({other_img['url']}) due to similar dimensions")
                                    # Promote PNG by swapping positions
                                    prioritized_image_data[other_idx], prioritized_image_data[png_idx] = prioritized_image_data[png_idx], prioritized_image_data[other_idx]
                
                # Extract just the URLs in the newly prioritized order
                prioritized_urls = [img['url'] for img in prioritized_image_data]
                
                if prioritized_urls:
                    filtered_urls = prioritized_urls
                    print(f"Final prioritized URLs: {filtered_urls[:3]}")
                    # Return top 3 URLs
                    return filtered_urls[:3]
            
            # If no image data or processing failed, fall back to the original prioritization
            # Filter out any duplicates while preserving order
            filtered_urls = []
            for url in high_quality_urls:
                # Skip Google's own logos and other unwanted images
                if any(pattern in url.lower() for pattern in [
                    "google", "gstatic", "googleusercontent", "fonts.googleapis"
                ]):
                    print(f"Filtering out Google image: {url}")
                    continue
                
                # Skip common icon and thumbnail URLs
                if any(pattern in url.lower() for pattern in ["icon", "favicon"]):
                    print(f"Filtering out icon image: {url}")
                    continue
                
                # Skip redirects and ensure we have direct image URLs
                if "imgres?" in url or "url?" in url:
                    print(f"Filtering out redirect URL: {url}")
                    continue
                
                # Add valid URLs to our filtered list
                if url not in filtered_urls and url.startswith('http'):
                    filtered_urls.append(url)
            
            print(f"Found {len(filtered_urls)} high-quality logo URLs using Selenium")
            
            # Create priority ordered list of URLs
            prioritized_urls = []
            remaining_urls = filtered_urls.copy()
            
            # General logo prioritization algorithm
            # 1. First priority: URLs from company's own domain with 'logo' in filename
            # 2. Second priority: Any URL from company's domain
            # 3. Third priority: URLs with 'logo' in the path but not from social media
            # 4. Last priority: Other URLs, excluding social media profile images
            
            # Priority 1: Company domain + 'logo' in filename
            domain_logo_urls = [url for url in remaining_urls 
                              if self.domain in url.lower() and 'logo' in url.lower()]
            
            for url in domain_logo_urls:
                if url in remaining_urls:
                    prioritized_urls.append(url)
                    remaining_urls.remove(url)
                    print(f"Priority 1 - Domain+Logo URL: {url}")
            
            # Priority 2: Any URL from company domain
            domain_urls = [url for url in remaining_urls if self.domain in url.lower()]
            for url in domain_urls:
                if url in remaining_urls:
                    prioritized_urls.append(url)
                    remaining_urls.remove(url)
                    print(f"Priority 2 - Domain URL: {url}")
            
            # Priority 3: URLs with 'logo' in path (excluding social media)
            social_domains = ["twitter.com", "facebook.com", "linkedin.com", "instagram.com", 
                            "youtube.com", "pinterest.com", "tumblr.com"]
            
            logo_urls = [url for url in remaining_urls 
                        if 'logo' in url.lower() 
                        and not any(social in url.lower() for social in social_domains)]
            
            for url in logo_urls:
                if url in remaining_urls:
                    prioritized_urls.append(url)
                    remaining_urls.remove(url)
                    print(f"Priority 3 - Logo URL: {url}")
            
            # Priority 4: Remaining URLs (excluding social media)
            other_urls = [url for url in remaining_urls 
                         if not any(social in url.lower() for social in social_domains)]
            
            for url in other_urls:
                prioritized_urls.append(url)
                print(f"Priority 4 - Other URL: {url}")
            
            # If we have URLs, use the prioritized list
            if prioritized_urls:
                filtered_urls = prioritized_urls
                print(f"Final prioritized URLs: {filtered_urls[:3]}")
            
            # Return top 3 URLs
            return filtered_urls[:3]
            
        except Exception as e:
            print(f"Selenium extraction failed: {str(e)}")
            traceback.print_exc()
            return []

    def _get_image_format_from_url(self, url):
        """Extract image format from URL"""
        if not url:
            return None
            
        # Try to extract extension from URL
        extensions = {
            '.svg': 'svg',
            '.png': 'png',
            '.jpg': 'jpg',
            '.jpeg': 'jpg',
            '.webp': 'webp',
            '.gif': 'gif'
        }
        
        for ext, format_name in extensions.items():
            if ext in url.lower():
                return format_name
                
        # If no extension found, check content type in URL if present
        content_types = {
            'image/svg': 'svg',
            'image/png': 'png',
            'image/jpeg': 'jpg',
            'image/webp': 'webp',
            'image/gif': 'gif'
        }
        
        for content_type, format_name in content_types.items():
            if content_type in url.lower():
                return format_name
                
        return None

    def _extract_logo_urls_with_selenium_fast(self, search_query):
        """Use Selenium to extract logo URLs from Google Images quickly without clicking thumbnails."""
        try:
            # Initialize Chrome WebDriver
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            service = ChromeService(executable_path=self.chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Set short timeout for finding elements
            wait = WebDriverWait(driver, 2)
            
            # Format the search query for the URL
            formatted_query = quote_plus(search_query)
            url = f"https://www.google.com/search?q={formatted_query}&tbm=isch"
            
            print(f"Fast extraction - Search query: {search_query}")
            print(f"Navigating to Google Images search URL: {url}")
            
            # Navigate to Google Images
            driver.get(url)
            time.sleep(1)  # Brief pause to let the page load
            
            # Collect all image URLs directly from the search results page
            image_urls = []
            image_data = []  # Store image data with dimensions and format
            
            # Try multiple selectors for image thumbnails
            selectors = [
                "img.Q4LuWd",  # Common thumbnail class
                "div.bRMDJf img",  # Another common container
                "img.rg_i",  # Alternative class
                "div.fR6src img"  # Another possible container
            ]
            
            for selector in selectors:
                try:
                    thumbnails = driver.find_elements(By.CSS_SELECTOR, selector)
                    if thumbnails and len(thumbnails) > 0:
                        print(f"Found {len(thumbnails)} thumbnails with selector {selector}")
                        
                        # Extract source and data-src attributes from thumbnails
                        for img in thumbnails[:10]:  # Limit to first 10 results
                            try:
                                # Check for full-size image URL in data attributes
                                src = img.get_attribute("src")
                                data_src = img.get_attribute("data-src")
                                
                                # Sometimes the image URL is stored in different attributes
                                url_candidates = [
                                    src,
                                    data_src,
                                    img.get_attribute("data-iurl")
                                ]
                                
                                for candidate in url_candidates:
                                    if candidate and candidate.startswith("http") and not candidate.startswith("data:"):
                                        # Skip Google's own logos
                                        if "google" in candidate.lower() or "gstatic" in candidate.lower():
                                            continue
                                        
                                        if self._is_valid_url(candidate) and candidate not in image_urls:
                                            # Try to get dimensions
                                            width = None
                                            height = None
                                            try:
                                                width = int(img.get_attribute("width") or 0)
                                                height = int(img.get_attribute("height") or 0)
                                            except:
                                                pass
                                            
                                            # Add image data with format
                                            image_format = self._get_image_format_from_url(candidate)
                                            image_data.append({
                                                'url': candidate,
                                                'width': width,
                                                'height': height,
                                                'format': image_format
                                            })
                                            
                                            image_urls.append(candidate)
                            except Exception as e:
                                continue
                                
                        if image_urls:
                            break  # Stop if we found enough images
                except Exception:
                    continue
            
            # If we didn't find enough images, try extracting from page source
            if len(image_urls) < 3:
                try:
                    page_source = driver.page_source
                    
                    # Look for full-size image URLs in the page source
                    url_pattern = r'"ou":"(https?://[^"]+)"'
                    matches = re.findall(url_pattern, page_source)
                    
                    for url in matches:
                        if url.startswith('http') and url not in image_urls:
                            # Skip Google's own logos
                            if "google" in url.lower() or "gstatic" in url.lower():
                                continue
                                
                            if self._is_valid_url(url):
                                # Add to image data with format
                                image_format = self._get_image_format_from_url(url)
                                image_data.append({
                                    'url': url,
                                    'width': None,
                                    'height': None,
                                    'format': image_format
                                })
                                
                                image_urls.append(url)
                                if len(image_urls) >= 10:
                                    break
                except Exception:
                    pass
            
            driver.quit()
            
            # If we have image data, use it for prioritization
            if image_data:
                # Import the should_prefer_png function from utils.qa
                try:
                    from ..utils.qa import should_prefer_png
                    has_preference_function = True
                except ImportError:
                    has_preference_function = False
                
                # First, filter out any duplicates and invalid URLs
                filtered_image_data = []
                seen_urls = set()
                
                for img in image_data:
                    url = img['url']
                    
                    # Skip Google's own logos, icons, redirects, and duplicates
                    if (any(pattern in url.lower() for pattern in ["google", "gstatic", "googleusercontent", "fonts.googleapis"]) or
                        any(pattern in url.lower() for pattern in ["icon", "favicon"]) or
                        "imgres?" in url or "url?" in url or
                        url in seen_urls):
                        continue
                    
                    # Only include valid URLs
                    if url.startswith('http'):
                        filtered_image_data.append(img)
                        seen_urls.add(url)
                
                # Now apply advanced prioritization
                prioritized_image_data = []
                remaining_image_data = filtered_image_data.copy()
                
                # Look for SVG images first (absolute top priority)
                svg_images = [img for img in remaining_image_data if img['format'] and img['format'].lower() == 'svg']
                if svg_images:
                    # SVGs found, always use them first
                    print("Found SVG images - prioritizing these first (gold standard)")
                    for img in svg_images:
                        prioritized_image_data.append(img)
                        if img in remaining_image_data:
                            remaining_image_data.remove(img)
                
                # Priority 1: Company domain + 'logo' in filename
                domain_logo_images = [img for img in remaining_image_data 
                                    if self.domain in img['url'].lower() and 'logo' in img['url'].lower()]
                
                for img in domain_logo_images:
                    if img in remaining_image_data:
                        prioritized_image_data.append(img)
                        remaining_image_data.remove(img)
                
                # Priority 2: Any URL from company domain
                domain_images = [img for img in remaining_image_data if self.domain in img['url'].lower()]
                for img in domain_images:
                    if img in remaining_image_data:
                        prioritized_image_data.append(img)
                        remaining_image_data.remove(img)
                
                # Priority 3: URLs with 'logo' in path (excluding social media)
                social_domains = ["twitter.com", "facebook.com", "linkedin.com", "instagram.com", 
                                "youtube.com", "pinterest.com", "tumblr.com"]
                
                logo_images = [img for img in remaining_image_data 
                            if 'logo' in img['url'].lower() 
                            and not any(social in img['url'].lower() for social in social_domains)]
                
                for img in logo_images:
                    if img in remaining_image_data:
                        prioritized_image_data.append(img)
                        remaining_image_data.remove(img)
                
                # Priority 4: Remaining URLs (excluding social media)
                other_images = [img for img in remaining_image_data 
                             if not any(social in img['url'].lower() for social in social_domains)]
                
                for img in other_images:
                    prioritized_image_data.append(img)
                
                # Apply PNG preference logic if we have the function and dimensions
                if has_preference_function and len(prioritized_image_data) > 1:
                    # Look for potential PNG preference candidates
                    png_images = [img for img in prioritized_image_data 
                                if img['format'] and img['format'].lower() == 'png']
                    other_images = [img for img in prioritized_image_data 
                                  if img['format'] and img['format'].lower() in ['jpg', 'jpeg', 'webp']]
                    
                    if png_images and other_images:
                        # Check for cases where PNG should be preferred over similar-sized JPG/WEBP
                        for png_img in png_images:
                            for other_img in other_images:
                                # Skip if either doesn't have dimensions
                                if not (png_img.get('width') and png_img.get('height') and 
                                        other_img.get('width') and other_img.get('height')):
                                    continue
                                
                                # If dimensions are similar and PNG is not already higher priority
                                png_idx = prioritized_image_data.index(png_img)
                                other_idx = prioritized_image_data.index(other_img)
                                
                                if other_idx < png_idx and should_prefer_png(png_img, other_img):
                                    print(f"Promoting PNG ({png_img['url']}) over {other_img['format']} ({other_img['url']}) due to similar dimensions")
                                    # Promote PNG by swapping positions
                                    prioritized_image_data[other_idx], prioritized_image_data[png_idx] = prioritized_image_data[png_idx], prioritized_image_data[other_idx]
                
                # Extract just the URLs in the newly prioritized order
                prioritized_urls = [img['url'] for img in prioritized_image_data]
                
                if prioritized_urls:
                    # Return top 3 URLs
                    return prioritized_urls[:3]
            
            # If image data approach failed, fall back to original method
            # Create priority ordered list of URLs
            prioritized_urls = []
            remaining_urls = image_urls.copy()
            
            # Priority 1: Company domain + 'logo' in filename
            domain_logo_urls = [url for url in remaining_urls 
                              if self.domain in url.lower() and 'logo' in url.lower()]
            
            for url in domain_logo_urls:
                if url in remaining_urls:
                    prioritized_urls.append(url)
                    remaining_urls.remove(url)
            
            # Priority 2: Any URL from company domain
            domain_urls = [url for url in remaining_urls if self.domain in url.lower()]
            for url in domain_urls:
                if url in remaining_urls:
                    prioritized_urls.append(url)
                    remaining_urls.remove(url)
            
            # Priority 3: URLs with 'logo' in path (excluding social media)
            social_domains = ["twitter.com", "facebook.com", "linkedin.com", "instagram.com", 
                            "youtube.com", "pinterest.com", "tumblr.com"]
            
            logo_urls = [url for url in remaining_urls 
                        if 'logo' in url.lower() 
                        and not any(social in url.lower() for social in social_domains)]
            
            for url in logo_urls:
                if url in remaining_urls:
                    prioritized_urls.append(url)
                    remaining_urls.remove(url)
            
            # Priority 4: Remaining URLs (excluding social media)
            other_urls = [url for url in remaining_urls 
                         if not any(social in url.lower() for social in social_domains)]
            
            for url in other_urls:
                prioritized_urls.append(url)
            
            # Return top 3 URLs
            return prioritized_urls[:3]
            
        except Exception as e:
            print(f"Fast Selenium extraction failed: {str(e)}")
            try:
                driver.quit()
            except:
                pass
            return []
            
    def _extract_image_urls_from_google(self, query, num_images=5):
        """
        Extract image URLs from Google Image search results using HTTP requests
        
        Note: This approach is kept for compatibility but often fails due to Google's anti-scraping measures.
        Use Selenium approach instead.
        
        Args:
            query (str): Search query
            num_images (int): Number of images to extract
            
        Returns:
            list: List of image URLs
        """
        print("HTTP-based Google image search is not reliable. Using Selenium approach instead.")
        return []  # Return empty list, let the Selenium approach handle it
        
    def _is_valid_url(self, url):
        """Check if a URL is valid and has a proper scheme"""
        if not url:
            return False
        if not isinstance(url, str):
            return False
        if url == '/':
            return False
        if not url.startswith(('http://', 'https://')):
            return False
        return True
        
    def _perform_extraction(self):
        """
        Extract logo from Google Image Search
        
        Returns:
            list: List of top 3 logo URLs, or empty list if none found
        """
        print(f"Searching Google Images for logo of {self.domain}")
        
        # Prepare folder path
        folder_path = os.path.join(CACHE_DIR, "google", self.domain.replace(".", "_").replace("-", "_"))
        self._create_folder_if_not_exists(folder_path)
        
        # Use Selenium for highest quality results
        if SELENIUM_AVAILABLE:
            try:
                # Try the fast extraction method first
                selenium_urls = self._extract_logo_urls_with_selenium_fast(f"{self.domain} logo")
                
                if selenium_urls:
                    # Filter out any invalid URLs
                    valid_urls = [url for url in selenium_urls if self._is_valid_url(url)]
                    if valid_urls:
                        print(f"Found {len(valid_urls)} logo URLs using fast Selenium method")
                        # Download and check all candidate images first
                        return self._download_and_prioritize_logos(valid_urls, folder_path)
                    else:
                        print("No valid URLs found from fast Selenium method.")
                else:
                    print("No results found with fast Selenium method.")
                    
                # If fast method fails, try the original more thorough method
                print("Falling back to original Selenium method...")
                selenium_urls = self._extract_logo_urls_with_selenium(f"{self.domain} logo")
                
                if selenium_urls:
                    # Filter out any invalid URLs
                    valid_urls = [url for url in selenium_urls if self._is_valid_url(url)]
                    if valid_urls:
                        print(f"Found {len(valid_urls)} high-quality logo URLs using original Selenium method")
                        # Download and check all candidate images first
                        return self._download_and_prioritize_logos(valid_urls, folder_path)
                    else:
                        print("No valid URLs found from original Selenium method.")
                else:
                    print("No results found with original Selenium method.")
            except Exception as e:
                print(f"Error using Selenium: {e}")
                print("Selenium approach failed.")
        else:
            print("Selenium not available. Install selenium package for better results.")
        
        return []  # Return empty list if all approaches fail
        
    def _download_and_prioritize_logos(self, urls, folder_path):
        """
        Download all candidate logo images and prioritize them based on actual dimensions and format
        
        Args:
            urls (list): List of image URLs to download
            folder_path (str): Path to folder where images should be saved
            
        Returns:
            list: List of prioritized URLs, with best options first
        """
        # Import the should_prefer_png function from utils.qa
        try:
            from ..utils.qa import should_prefer_png, get_image_dimensions
            has_preference_function = True
        except ImportError:
            has_preference_function = False
            
        # Download all images and collect metadata
        downloaded_images = []
        
        for i, url in enumerate(urls):
            try:
                print(f"Downloading candidate logo {i+1}/{len(urls)}: {url}")
                output_path = os.path.join(folder_path, f"logo_candidate_{i}.tmp")
                downloaded_path = self._download_image(url, output_path)
                
                if downloaded_path:
                    # Get actual image dimensions and format from the downloaded file
                    width, height = 0, 0
                    if has_preference_function:
                        try:
                            width, height = get_image_dimensions(downloaded_path)
                        except:
                            pass
                            
                    # Get format from file extension
                    _, ext = os.path.splitext(downloaded_path)
                    image_format = ext.lower().lstrip('.')
                    
                    # Add to downloaded images list
                    downloaded_images.append({
                        'url': url,
                        'path': downloaded_path,
                        'width': width,
                        'height': height,
                        'format': image_format
                    })
                    
                    print(f"Successfully downloaded: {url}, dimensions: {width}x{height}, format: {image_format}")
            except Exception as e:
                print(f"Error downloading {url}: {e}")
        
        # If no images were downloaded successfully, return empty list
        if not downloaded_images:
            return []
        
        # Now apply advanced prioritization
        prioritized_images = []
        remaining_images = downloaded_images.copy()
        
        # Look for SVG images first (absolute top priority)
        svg_images = [img for img in remaining_images if img['format'] and img['format'].lower() == 'svg']
        if svg_images:
            # SVGs found, always use them first
            print("Found SVG images - prioritizing these first (gold standard)")
            for img in svg_images:
                prioritized_images.append(img)
                if img in remaining_images:
                    remaining_images.remove(img)
        
        # Apply domain-based prioritization as before
        # Priority 1: Company domain + 'logo' in filename
        domain_logo_images = [img for img in remaining_images 
                            if self.domain in img['url'].lower() and 'logo' in img['url'].lower()]
        
        for img in domain_logo_images:
            if img in remaining_images:
                prioritized_images.append(img)
                remaining_images.remove(img)
                print(f"Priority 1 - Domain+Logo URL: {img['url']}")
        
        # Priority 2: Any URL from company domain
        domain_images = [img for img in remaining_images if self.domain in img['url'].lower()]
        for img in domain_images:
            if img in remaining_images:
                prioritized_images.append(img)
                remaining_images.remove(img)
                print(f"Priority 2 - Domain URL: {img['url']}")
        
        # Priority 3: URLs with 'logo' in path (excluding social media)
        social_domains = ["twitter.com", "facebook.com", "linkedin.com", "instagram.com", 
                        "youtube.com", "pinterest.com", "tumblr.com"]
        
        logo_images = [img for img in remaining_images 
                    if 'logo' in img['url'].lower() 
                    and not any(social in img['url'].lower() for social in social_domains)]
        
        for img in logo_images:
            if img in remaining_images:
                prioritized_images.append(img)
                remaining_images.remove(img)
                print(f"Priority 3 - Logo URL: {img['url']}")
        
        # Priority 4: Remaining URLs (excluding social media)
        other_images = [img for img in remaining_images 
                     if not any(social in img['url'].lower() for social in social_domains)]
        
        for img in other_images:
            prioritized_images.append(img)
            print(f"Priority 4 - Other URL: {img['url']}")
        
        # Apply PNG preference logic if we have the function and dimensions
        if has_preference_function and len(prioritized_images) > 1:
            # Look for potential PNG preference candidates
            png_images = [img for img in prioritized_images 
                        if img['format'] and img['format'].lower() == 'png']
            other_images = [img for img in prioritized_images 
                          if img['format'] and img['format'].lower() in ['jpg', 'jpeg', 'webp']]
            
            if png_images and other_images:
                # Check for cases where PNG should be preferred over similar-sized JPG/WEBP
                for png_img in png_images:
                    for other_img in other_images:
                        # Skip if either doesn't have dimensions
                        if not (png_img.get('width') and png_img.get('height') and 
                                other_img.get('width') and other_img.get('height')):
                            continue
                        
                        # If dimensions are similar and PNG is not already higher priority
                        png_idx = prioritized_images.index(png_img)
                        other_idx = prioritized_images.index(other_img)
                        
                        if other_idx < png_idx and should_prefer_png(png_img, other_img):
                            print(f"Promoting PNG ({png_img['url']}) over {other_img['format']} ({other_img['url']}) due to similar dimensions")
                            print(f"PNG: {png_img['width']}x{png_img['height']}, Other: {other_img['width']}x{other_img['height']}")
                            # Promote PNG by swapping positions
                            prioritized_images[other_idx], prioritized_images[png_idx] = prioritized_images[png_idx], prioritized_images[other_idx]
        
        # Extract just the URLs in the newly prioritized order
        prioritized_urls = [img['url'] for img in prioritized_images]
        
        # Cleanup temporary files
        for img in downloaded_images:
            try:
                if os.path.exists(img['path']):
                    os.remove(img['path'])
            except:
                pass
                
        if prioritized_urls:
            print(f"Final prioritized URLs after download analysis: {prioritized_urls[:3]}")
            # Return top 3 URLs
            return prioritized_urls[:3]
            
        return [] 