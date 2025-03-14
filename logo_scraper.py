import os
import time
import requests
import warnings
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import concurrent.futures
import xml.etree.ElementTree as ET
import re

from io import BytesIO
import cairosvg
from PIL import Image

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Set up the Chrome WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # Run Chrome in headless mode
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

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
        # Calculate padding in pixel space: at least 20% of the dimension or at least 50 pixels
        pad_x = max((right - left) * 0.05, 10)
        pad_y = max((lower - upper) * 0.05, 10)
        
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

# Function to download SVG file
def download_svg(logo_url, logo_name, download_folder):
    try:
        response = requests.get(logo_url, timeout=10)
        if response.status_code == 200:
            svg_path = os.path.join(download_folder, f"{logo_name}.svg")
            
            # Process the SVG to crop whitespace if it's an SVG file
            if logo_url.endswith('.svg') or 'image/svg+xml' in response.headers.get('Content-Type', ''):
                processed_content = crop_svg_accurate(response.content)
            else:
                processed_content = response.content

            # Save SVG file
            with open(svg_path, 'wb') as f:
                f.write(processed_content)

            print(f"Downloaded and cropped {logo_name} to {download_folder}")
        else:
            print(f"Failed to download {logo_name}")
    except Exception as e:
        print(f"Error downloading {logo_name}: {e}")

# Function to extract logos from a page
def extract_logos_from_page(download_folder):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # Find all logo elements
    logos = soup.find_all('a', class_='svelte-1wqkjra')

    logo_tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        for logo in logos:
            try:
                logo_img_tag = logo.find('img')
                logo_name_tag = logo.find('h4', class_='title')

                if logo_img_tag and logo_name_tag:
                    logo_url = 'https://www.logo.wine' + logo_img_tag['src']
                    logo_name = logo_name_tag.text.strip()

                    # Replace spaces with underscores in the logo name for the filename
                    logo_name_sanitized = logo_name.replace(" ", "_")

                    # Download the logo image in parallel
                    logo_tasks.append(executor.submit(download_svg, logo_url, logo_name_sanitized, download_folder))
            except Exception as e:
                print(f"Error processing logo: {e}")

        # Wait for all download tasks to complete
        concurrent.futures.wait(logo_tasks)

# Function to navigate through pages
def scrape_logos_from_all_pages(start_page_url, download_folder):
    driver.get(start_page_url)

    while True:
        extract_logos_from_page(download_folder)

        try:
            # Wait until the "Next" button is clickable and click it
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Next')]"))
            )
            next_button.click()
        except Exception as e:
            print("No more pages to scrape.")
            break

# Create main download folder if it doesn't exist
main_download_folder = "downloaded_logos"
os.makedirs(main_download_folder, exist_ok=True)

# List of URLs to scrape
urls_to_scrape = [
    "https://www.logo.wine/Technology",
    "https://www.logo.wine/Airlines",
    "https://www.logo.wine/Beverage",
    "https://www.logo.wine/Cars",
    "https://www.logo.wine/Education",
    "https://www.logo.wine/Entertainment",
    "https://www.logo.wine/Fashion",
    "https://www.logo.wine/Finance",
    "https://www.logo.wine/Food",
    "https://www.logo.wine/Government",
    "https://www.logo.wine/Legal",
    "https://www.logo.wine/Medical",
    "https://www.logo.wine/Petroleum",
    "https://www.logo.wine/Real_Estate",
    "https://www.logo.wine/Retail",
    "https://www.logo.wine/Sports",
    "https://www.logo.wine/Travel",
    # Add more URLs as needed
]

# Start scraping from each URL in the list
for url in urls_to_scrape:
    # Extract category name from URL
    category = url.split('/')[-1]
    
    # Create category-specific folder
    category_folder = os.path.join(main_download_folder, f"downloaded_logos_{category.lower()}")
    os.makedirs(category_folder, exist_ok=True)
    
    print(f"Starting to scrape logos from {category} into {category_folder}")
    scrape_logos_from_all_pages(url, category_folder)

# Quit the WebDriver
driver.quit()