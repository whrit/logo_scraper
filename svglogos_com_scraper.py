import os
import time
import re
import warnings
import requests
import concurrent.futures
import xml.etree.ElementTree as ET
from io import BytesIO
import cairosvg
from PIL import Image
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

def crop_svg_accurate(svg_content):
    """
    Renders the SVG to a high-resolution PNG, computes the bounding box of non-transparent
    pixels, converts that bbox to SVG coordinate space, adds padding, and updates the viewBox.
    """
    try:
        # Ensure we have a string representation of the SVG
        if isinstance(svg_content, bytes):
            svg_text = svg_content.decode('utf-8')
        else:
            svg_text = svg_content

        # Parse the SVG XML
        root = ET.fromstring(svg_text)
        
        # Determine the original coordinate system from viewBox or width/height attributes
        viewbox = root.get('viewBox')
        if viewbox:
            vb_vals = list(map(float, viewbox.split()))
            orig_x, orig_y, orig_width, orig_height = vb_vals
        else:
            width_attr = root.get('width')
            height_attr = root.get('height')
            if width_attr and height_attr:
                orig_width = float(re.sub(r'[^0-9.]', '', width_attr))
                orig_height = float(re.sub(r'[^0-9.]', '', height_attr))
                orig_x, orig_y = 0.0, 0.0
            else:
                # Cannot determine dimensions, so return original content
                return svg_content
        
        # Render the SVG to a PNG at a high resolution for accurate pixel analysis
        output_width = 1000  # Adjust for higher resolution if needed
        scale = output_width / orig_width
        output_height = int(orig_height * scale)
        png_bytes = cairosvg.svg2png(bytestring=svg_content, output_width=output_width, output_height=output_height)
        
        # Open the rendered PNG with Pillow and convert to RGBA
        img = Image.open(BytesIO(png_bytes)).convert("RGBA")
        # Get the bounding box of non-transparent pixels: (left, upper, right, lower)
        bbox = img.getbbox()
        if not bbox:
            # If nothing is found, return the original content
            return svg_content

        left, upper, right, lower = bbox
        # Calculate padding in pixel space: at least 5% of the dimension or at least 10 pixels
        pad_x = max((right - left) * 0.20, 50)
        pad_y = max((lower - upper) * 0.20, 50)

        
        # Expand the bounding box by the padding, without exceeding image bounds
        left = max(left - pad_x, 0)
        upper = max(upper - pad_y, 0)
        right = min(right + pad_x, output_width)
        lower = min(lower + pad_y, output_height)
        
        # Convert the pixel coordinates back to the SVG coordinate system
        new_x = orig_x + (left / scale)
        new_y = orig_y + (upper / scale)
        new_width = (right - left) / scale
        new_height = (lower - upper) / scale
        
        # Update the viewBox with the new cropped region
        new_viewbox = f"{new_x} {new_y} {new_width} {new_height}"
        root.set('viewBox', new_viewbox)
        return ET.tostring(root)
    except Exception as e:
        print(f"Error in crop_svg_accurate: {e}")
        return svg_content

def download_svg(logo_url, logo_name, download_folder):
    try:
        response = requests.get(logo_url, timeout=10)
        if response.status_code == 200:
            svg_path = os.path.join(download_folder, f"{logo_name}.svg")
            # Use the new, more accurate cropping method
            if logo_url.endswith('.svg') or 'image/svg+xml' in response.headers.get('Content-Type', ''):
                processed_content = crop_svg_accurate(response.content)
            else:
                processed_content = response.content
            with open(svg_path, 'wb') as f:
                f.write(processed_content)
            print(f"Downloaded and saved {logo_name}")
        else:
            print(f"Failed to download {logo_name}: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error downloading {logo_name}: {e}")

def incremental_scroll_and_extract(driver, download_folder, scroll_increment=500, pause_time=1, max_no_new=10, max_workers=20):
    try:
        # Find the scrollable container based on the page's structure
        container = driver.find_element(By.CSS_SELECTOR, "main > div > div[style*='overflow: auto']")
        print("Scrollable container found.")
    except Exception as e:
        print("Scrollable container not found; falling back to window scrolling.")
        container = None

    downloaded_logos = set()
    no_new_scrolls = 0

    while no_new_scrolls < max_no_new:
        if container:
            current_scroll = driver.execute_script("return arguments[0].scrollTop;", container)
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + arguments[1];", container, scroll_increment)
            new_scroll = driver.execute_script("return arguments[0].scrollTop;", container)
        else:
            current_scroll = driver.execute_script("return window.pageYOffset;")
            driver.execute_script("window.scrollBy(0, arguments[0]);", scroll_increment)
            new_scroll = driver.execute_script("return window.pageYOffset;")
        
        time.sleep(pause_time)
        if new_scroll == current_scroll:
            print("Reached the end of the scrollable area.")
            break

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        logos = soup.find_all('a', class_='Item_itemImage__qFoCb')
        new_logo_found = False

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for logo in logos:
                try:
                    img = logo.find('img')
                    if not img:
                        continue
                    logo_src = img.get('src', '')
                    if '-icon' in logo_src:
                        continue
                    logo_name = logo.get('data-shortname', img.get('alt', 'logo')).strip()
                    if logo_src in downloaded_logos:
                        continue
                    downloaded_logos.add(logo_src)
                    new_logo_found = True
                    futures.append(executor.submit(download_svg, logo_src, logo_name, download_folder))
                except Exception as e:
                    print(f"Error processing a logo: {e}")
            if futures:
                concurrent.futures.wait(futures)

        if not new_logo_found:
            no_new_scrolls += 1
            print(f"No new logos found on this scroll ({no_new_scrolls}/{max_no_new}).")
        else:
            no_new_scrolls = 0

def main():
    download_folder = "downloaded_logos_svglogos_com"
    os.makedirs(download_folder, exist_ok=True)

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=chrome_options
    )

    driver.get("https://svglogos.dev/")
    time.sleep(10)  # Allow time for the initial content to load
    
    incremental_scroll_and_extract(
        driver, 
        download_folder, 
        scroll_increment=500,
        pause_time=1,
        max_no_new=10, 
        max_workers=20
    )
    
    driver.quit()

if __name__ == '__main__':
    main()