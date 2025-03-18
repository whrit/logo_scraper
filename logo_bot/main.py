#!/usr/bin/env python3
import argparse
import os
import sys
import json
from typing import Optional, Tuple, Dict, Any
from dotenv import load_dotenv
import uvicorn
import re
import io

from .extractors.beautifulsoup import BeautifulSoupExtractor
from .extractors.claude import ClaudeExtractor
from .extractors.google import GoogleExtractor
from .config import TEXT_BASED_LOGO
from .utils.qa import select_best_logo
from .utils import url as url_utils

# Load environment variables from .env file
load_dotenv()

def process_multiple_logos(url_list, base_domain, source_name="multiple"):
    """
    Process multiple logo URLs, download them, and return their paths
    
    Args:
        url_list (list): List of URLs to process
        base_domain (str): Base domain for naming the files
        source_name (str): Source name for logging
        
    Returns:
        list: List of downloaded logo file paths
    """
    from .utils.image import download_image, process_logo_image, is_valid_image_url
    import os
    from .config import OUTPUT_DIR
    
    logo_paths = []
    
    print(f"Processing {len(url_list)} logo URLs from {source_name}...")
    
    # First, ensure we're only working with a list of strings (URLs)
    # In some cases we might get a list of characters or other invalid values
    clean_url_list = []
    for item in url_list:
        # Skip if not a string
        if not isinstance(item, str):
            continue
            
        # Skip if too short to be a URL
        if len(item) < 8:  # http://a would be 8 chars
            continue
            
        # Skip if it doesn't start with http
        if not item.startswith(('http://', 'https://')):
            continue
            
        clean_url_list.append(item)
    
    # If we filtered out all URLs, exit early
    if not clean_url_list:
        print(f"No valid URLs found in the provided list from {source_name}")
        return []
    
    print(f"Found {len(clean_url_list)} properly formatted URLs")
    
    # Next, try to validate URLs as image sources before downloading
    validated_urls = []
    for url in clean_url_list:
        try:
            # Check if URL directly points to an image
            if is_valid_image_url(url):
                validated_urls.append(url)
            # Check if it's a URL to a website that might contain an image 
            # (like trust.new-innov.com with a logo.png endpoint)
            elif any(ext in url.lower() for ext in ['logo', '.png', '.jpg', '.svg']):
                print(f"Adding potentially valid URL: {url}")
                validated_urls.append(url)
            else:
                print(f"Skipping URL that doesn't appear to be an image: {url}")
        except Exception as e:
            print(f"Error validating URL {url}: {e}")
    
    if not validated_urls:
        print(f"No valid image URLs found from {source_name}")
        return []
        
    print(f"Found {len(validated_urls)} potential valid URLs to download")
    
    # Remove duplicates while preserving order
    def remove_duplicates(seq):
        seen = set()
        return [x for x in seq if not (x in seen or seen.add(x))]
    
    validated_urls = remove_duplicates(validated_urls)
    
    for i, logo_url in enumerate(validated_urls):
        try:
            # Create a descriptive filename
            domain = base_domain.replace(".", "_").replace("-", "_")
            
            # Extract filename from URL if possible
            url_path = logo_url.split('?')[0]
            filename_from_url = os.path.basename(url_path)
            
            # Use filename from URL if it looks like an image file
            if any(filename_from_url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.svg', '.webp']):
                # Keep the original filename but add our prefix and sanitize
                # Remove special characters from filename
                safe_filename = re.sub(r'[^a-zA-Z0-9.-]', '_', filename_from_url)
                filename = f"{domain}_{source_name}_{i+1}_{safe_filename}"
            else:
                # Detect file extension from URL or default to png
                _, ext = os.path.splitext(url_path)
                ext = ext.lower() if ext else '.png'
                
                # Clean up extension
                if not ext.startswith('.'):
                    ext = '.' + ext
                    
                valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff']
                if ext not in valid_extensions:
                    ext = '.png'  # Default to png for unrecognized extensions
                    
                # Create unique filename
                filename = f"{domain}_{source_name}_{i+1}{ext}"
                
            output_path = os.path.join(OUTPUT_DIR, filename)
            
            print(f"Downloading {source_name} logo #{i+1} from {logo_url}")
            
            # Use the advanced image downloader that can handle protected URLs
            downloaded_path = download_image(logo_url, output_path, max_retries=3, timeout=15)
            
            if downloaded_path:
                # Process the image
                processed_path, is_valid, issues = process_logo_image(downloaded_path)
                
                if processed_path and is_valid:
                    print(f"Successfully processed {source_name} logo #{i+1}: {processed_path}")
                    logo_paths.append(processed_path)
                else:
                    if issues:
                        print(f"Logo #{i+1} has quality issues: {', '.join(issues)}")
            else:
                print(f"Failed to download logo from {logo_url}")
        except Exception as e:
            print(f"Error processing logo URL {logo_url}: {e}")
    
    print(f"Successfully downloaded and processed {len(logo_paths)} logos from {source_name}")
    return logo_paths

def extract_logo_cli(url: str, force_refresh: bool = False, use_claude_fallback: bool = True, 
                     use_google: bool = True, chromedriver_path: Optional[str] = None) -> Optional[str]:
    """
    Extract logo from a website (CLI version)
    
    Args:
        url (str): URL of the website to extract logo from
        force_refresh (bool): Whether to bypass cache
        use_claude_fallback (bool): Whether to use Claude as fallback if direct extraction fails
        use_google (bool): Whether to use Google Images as an additional source
        chromedriver_path (str): Path to ChromeDriver executable (for Google extraction)
        
    Returns:
        str: Path to the downloaded logo, TEXT_BASED_LOGO constant, or None if not found
    """
    # Create a StringIO object to capture stdout
    captured_output = io.StringIO()
    original_stdout = sys.stdout
    
    try:
        print(f"Extracting logo from {url}")
        domain = url_utils.get_domain_name(url)
        
        # Use ChromeDriver from PATH if not specified
        if not chromedriver_path:
            import shutil
            chromedriver_path = shutil.which('chromedriver')
            if chromedriver_path:
                print(f"Using ChromeDriver from: {chromedriver_path}")
        
        # List to collect all valid logo candidates
        all_logos = []
        
        # Step 1: Try BeautifulSoup extraction (fastest method)
        print("\nAPPROACH 1: Using direct BeautifulSoup extraction...")
        bs_extractor = BeautifulSoupExtractor(url)
        bs_result = bs_extractor.extract_logo(force_refresh=force_refresh)
        
        if bs_result == TEXT_BASED_LOGO:
            print("Website uses a text-based logo with no image file.")
            return TEXT_BASED_LOGO
        elif bs_result:
            print(f"Successfully downloaded logo from website to {bs_result}")
            # Process the logo and perform QA checks
            from .utils.image import process_logo_image
            processed_path, is_valid, issues = process_logo_image(bs_result)
            
            if not is_valid:
                print(f"WARNING: Logo from website has quality issues: {', '.join(issues)}")
                print("Will try other sources for better options...")
            else:
                print("Logo from website passed quality checks!")
                # Add to candidate list
                final_path = processed_path if processed_path else bs_result
                all_logos.append({"path": final_path, "source": "website"})
        
        # Step 2: Try Google Images (get multiple options)
        if use_google:
            print("\nAPPROACH 2: Searching Google Images for logos...")
            
            # Redirect stdout to capture output
            sys.stdout = captured_output
            
            try:
                google_extractor = GoogleExtractor(url, chromedriver_path)
                google_logo_urls = google_extractor.extract_logo(force_refresh=force_refresh)
            finally:
                # Always restore stdout
                sys.stdout = original_stdout
                
                # Get the captured output
                output_text = captured_output.getvalue()
                print(output_text, end='')  # Print the captured output
            
            # Check for auto-cropped path in the output
            auto_crop_match = re.search(r"Auto-cropped image to remove transparent background: ([^\n]+)", output_text)
            if auto_crop_match:
                cropped_path = auto_crop_match.group(1).strip()
                if os.path.exists(cropped_path):
                    print(f"Found auto-cropped logo path: {cropped_path}")
                    all_logos.append({"path": cropped_path, "source": "google"})
                    
                    # If we're explicitly told to skip Claude, return now
                    if not use_claude_fallback:
                        return cropped_path
            
            # Check if we got direct successful results from Selenium in Google extractor
            if not all_logos and google_logo_urls and len(google_logo_urls) > 0:
                # First, try to directly download the first URL which is most likely the best one
                first_url = google_logo_urls[0]
                
                # Validate URL before attempting download
                if first_url and first_url.startswith(('http://', 'https://')):
                    print(f"Successfully found logo URL in list using google: {first_url}")
                    
                    try:
                        # Use the image utils to download and process
                        from .utils.image import download_image, process_logo_image
                        from .config import OUTPUT_DIR  # Ensure OUTPUT_DIR is imported
                        
                        # Get file extension from URL or default to .png
                        url_path = first_url.split('?')[0]
                        file_ext = os.path.splitext(url_path)[1].lower() or '.png'
                        
                        # Clean up extension
                        if not file_ext.startswith('.'):
                            file_ext = '.' + file_ext
                        
                        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff']
                        if file_ext not in valid_extensions:
                            file_ext = '.png'  # Default to png for unrecognized extensions
                        
                        output_name = f"{domain.replace('.', '_')}_logo{file_ext}"
                        output_path = os.path.join(OUTPUT_DIR, output_name)
                        
                        # Download the image
                        downloaded_path = download_image(first_url, output_path)
                        
                        # Check multiple possible output paths
                        potential_paths = [
                            downloaded_path,
                            output_path,
                            os.path.join(OUTPUT_DIR, f"{domain}_logo{file_ext}"),
                            os.path.join(OUTPUT_DIR, f"{domain.replace('.', '_')}_logo{file_ext}"),
                            os.path.join(OUTPUT_DIR, f"{domain}_logo.png"),
                            os.path.join(OUTPUT_DIR, f"{domain.replace('.', '_')}_logo.png")
                        ]
                        
                        # Find the first path that exists
                        found_path = None
                        for path in potential_paths:
                            if path and os.path.exists(path):
                                found_path = path
                                break
                        
                        if found_path:
                            all_logos.append({"path": found_path, "source": "google"})
                            print(f"Found logo file at: {found_path}")
                            
                            # If we're explicitly told to skip Claude, return now
                            if not use_claude_fallback:
                                return found_path
                        else:
                            print(f"Failed to find downloaded logo from {first_url}")
                    except Exception as e:
                        print(f"Error processing primary logo URL: {str(e)}")
                        import traceback
                        traceback.print_exc()  # Print full error details
                else:
                    print(f"Skipping invalid URL: {first_url}")
                
                # If we didn't succeed with the first URL, try others as backup
                if not all_logos and len(google_logo_urls) > 1:
                    print("Trying alternative logo URLs...")
                    valid_urls = [url for url in google_logo_urls[1:] if url and url.startswith(('http://', 'https://'))]
                    
                    if valid_urls:
                        # Download and process each Google logo
                        google_logo_paths = process_multiple_logos(valid_urls, domain, "google")
                        
                        # Add Google logo paths to candidates
                        for path in google_logo_paths:
                            all_logos.append({"path": path, "source": "google"})
                    else:
                        print("No valid alternative URLs found.")

        # Before proceeding to Step 3, check if we found any valid logos already
        if all_logos:
            print(f"\nFound {len(all_logos)} logo candidates from different sources")
            print("Comparing logo quality to select the best one...")
            
            # Select the best logo from candidates
            # If we only have one logo candidate, just return it
            if len(all_logos) == 1:
                print(f"Only one logo candidate available (from {all_logos[0]['source']}), using it.")
                return all_logos[0]['path']
                
            # Otherwise select the best one
            best_logo = select_best_logo(all_logos)
            
            if best_logo:
                # The best_logo might be a string path or a dictionary
                if isinstance(best_logo, dict):
                    source_name = best_logo.get("source", "unknown")
                    path = best_logo.get("path")
                    print(f"Selected best logo from {source_name} source: {path}")
                    return path
                else:
                    # Find which logo this corresponds to
                    source = next((logo['source'] for logo in all_logos if logo['path'] == best_logo), "unknown")
                    print(f"Selected best logo from {source} source: {best_logo}")
                    return best_logo
        
        # Debug: Check if all_logos has items
        print(f"DEBUG: all_logos has {len(all_logos)} items before Claude approach")
        if all_logos:
            print(f"DEBUG: Logo paths in all_logos: {[logo.get('path') for logo in all_logos]}")
            
        # Step 3: If both BeautifulSoup and Google failed or found low quality logos, try Claude as final fallback
        if use_claude_fallback and not all_logos:
            print("\nAPPROACH 3: Using Claude GUI approach as final fallback...")
            claude_extractor = ClaudeExtractor(url)
            claude_result = claude_extractor.extract_logo(force_refresh=force_refresh)
            
            if claude_result == TEXT_BASED_LOGO:
                print("Claude determined website uses a text-based logo.")
                return TEXT_BASED_LOGO
            elif claude_result:
                print(f"Successfully downloaded logo from website (via Claude) to {claude_result}")
                # Process the logo and perform QA checks
                from .utils.image import process_logo_image
                processed_path, is_valid, issues = process_logo_image(claude_result)
                
                if not is_valid:
                    print(f"WARNING: Logo from Claude has quality issues: {', '.join(issues)}")
                else:
                    print("Logo from Claude passed quality checks!")
                    final_path = processed_path if processed_path else claude_result
                    all_logos.append({"path": final_path, "source": "claude"})
        
        # Compare all logo candidates and select the best one
        if all_logos:
            print(f"\nFound {len(all_logos)} logo candidates from different sources")
            print("Comparing logo quality to select the best one...")
            
            # If we only have one logo candidate, just return it
            if len(all_logos) == 1:
                print(f"Only one logo candidate available (from {all_logos[0]['source']}), using it.")
                return all_logos[0]['path']
                
            # Otherwise, use the quality comparator to select the best logo
            best_logo = select_best_logo(all_logos)
            if best_logo:
                # The best_logo might be a string path or a dictionary
                if isinstance(best_logo, dict):
                    source_name = best_logo.get("source", "unknown")
                    path = best_logo.get("path")
                    print(f"Selected the highest quality logo from {source_name}: {path}")
                    # Copy to the standard output location with the domain name
                    from shutil import copy
                    final_path = os.path.join(OUTPUT_DIR, f"{domain}_logo{os.path.splitext(path)[1]}")
                    copy(path, final_path)
                    return final_path
                else:
                    # Find which logo this corresponds to
                    source = next((logo['source'] for logo in all_logos if logo['path'] == best_logo), "unknown")
                    print(f"Selected the highest quality logo from {source}: {best_logo}")
                    # Copy to the standard output location with the domain name
                    from shutil import copy
                    final_path = os.path.join(OUTPUT_DIR, f"{domain}_logo{os.path.splitext(best_logo)[1]}")
                    copy(best_logo, final_path)
                    return final_path
            
        # If we get here, no logo was found with any method
        print("\nFailed to extract logo with any method")
        return None
        
    except Exception as e:
        # Ensure stdout is restored
        if sys.stdout != original_stdout:
            sys.stdout = original_stdout
            
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def main_cli():
    """
    Main CLI entry point for the application
    """
    parser = argparse.ArgumentParser(description="Extract and download company logo from a website")
    parser.add_argument("url", help="URL of the website to extract logo from")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh cache")
    parser.add_argument("--no-claude", action="store_true", help="Skip Claude fallback for extraction")
    parser.add_argument("--no-google", action="store_true", help="Skip Google Images extraction")
    parser.add_argument("--chromedriver", help="Path to ChromeDriver executable (for Google extraction)")
    parser.add_argument("--api", action="store_true", help="Start the API server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the API server to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind the API server to")
    
    args = parser.parse_args()
    
    # If --api flag is set, start the API server
    if args.api:
        uvicorn.run(
            "logo_bot.api.routes:app", 
            host=args.host, 
            port=args.port, 
            reload=True
        )
        return 0
    
    # Otherwise, run the CLI version
    result = extract_logo_cli(
        args.url, 
        force_refresh=args.force_refresh,
        use_claude_fallback=not args.no_claude,
        use_google=not args.no_google,
        chromedriver_path=args.chromedriver
    )
    
    # If we found a logo, return success
    if result:
        # Check if it's a text-based logo
        if result == TEXT_BASED_LOGO:
            domain = args.url.replace("https://", "").replace("http://", "").rstrip("/").replace("www.", "")
            print(f"Successfully identified text-based logo for {domain}")
            return 0
        else:
            # It's a regular logo file
            print(f"Successfully downloaded logo to {result}")
            return 0
    
    # If we didn't find a logo, return error
    print("Failed to download logo.")
    return 1

def main_api(host: str = "127.0.0.1", port: int = 8000):
    """
    Start the API server
    
    Args:
        host (str): Host to bind the API server to
        port (int): Port to bind the API server to
    """
    uvicorn.run(
        "logo_bot.api.routes:app", 
        host=host, 
        port=port, 
        reload=True
    )

if __name__ == "__main__":
    sys.exit(main_cli()) 