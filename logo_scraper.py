import os
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import cairosvg
import concurrent.futures

# Set up the Chrome WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # Run Chrome in headless mode
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

# Function to download and convert SVG to PNG
def download_and_convert_svg(logo_url, logo_name, download_folder):
    try:
        response = requests.get(logo_url, timeout=10)
        if response.status_code == 200:
            svg_path = os.path.join(download_folder, f"{logo_name}.svg")
            png_path = os.path.join(download_folder, f"{logo_name}.png")

            # Save SVG file
            with open(svg_path, 'wb') as f:
                f.write(response.content)

            # Convert SVG to PNG
            cairosvg.svg2png(url=svg_path, write_to=png_path)
            print(f"Downloaded and converted {logo_name}")

            # Remove the SVG file after conversion
            os.remove(svg_path)
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for logo in logos:
            try:
                logo_img_tag = logo.find('img')
                logo_name_tag = logo.find('h4', class_='title')

                if logo_img_tag and logo_name_tag:
                    logo_url = 'https://www.logo.wine' + logo_img_tag['src']
                    logo_name = logo_name_tag.text.strip()

                    # Replace spaces with underscores in the logo name for the filename
                    logo_name_sanitized = logo_name.replace(" ", "_")

                    # Download and convert the logo image in parallel
                    logo_tasks.append(executor.submit(download_and_convert_svg, logo_url, logo_name_sanitized, download_folder))
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

# Create download folder if it doesn't exist
download_folder = "downloaded_logos"
os.makedirs(download_folder, exist_ok=True)

# Start scraping from the first page
start_page_url = "https://www.logo.wine/Technology"
scrape_logos_from_all_pages(start_page_url, download_folder)

# Quit the WebDriver
driver.quit()