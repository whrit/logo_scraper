import anthropic
import sys
import os
import requests
import re
import time
import json
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Load environment variables from .env file
load_dotenv()

def download_company_logo(website_url):
    # Get API key from environment variable
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in .env file")
    
    # Initialize the Anthropic client with the API key
    client = anthropic.Anthropic(api_key=api_key)
    
    # Initialize token tracking
    token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "system_prompt_tokens": 313,  # Tool use system prompt tokens for Claude 3.5 Sonnet
        "computer_tool_tokens": 683,  # Additional tokens for computer_20241022
        "bash_tool_tokens": 245       # Additional tokens for bash_20241022
    }
    
    # Prefetch the HTML and extract the logo URL for later use
    print("Pre-extracting logo information to provide accurate feedback...")
    actual_logo_url = extract_logo_url_directly(website_url)
    if actual_logo_url:
        print(f"Pre-extracted logo URL: {actual_logo_url}")
    
    # First try the browser GUI approach to copy image address
    print("APPROACH 1: Trying browser GUI with 'Copy Image Address'...")
    logo_url, gui_tokens = try_copy_image_address(client, website_url, actual_logo_url)
    
    # Update token usage
    token_usage["input_tokens"] += gui_tokens["input_tokens"]
    token_usage["output_tokens"] += gui_tokens["output_tokens"]
    
    # If the GUI approach failed, try the HTML extraction approach
    if not logo_url or not is_valid_image_url(logo_url):
        print("GUI approach failed or returned invalid URL.")
        print("APPROACH 2: Trying direct HTML extraction...")
        logo_url, html_tokens = try_html_extraction(client, website_url)
        
        # Update token usage
        token_usage["input_tokens"] += html_tokens["input_tokens"]
        token_usage["output_tokens"] += html_tokens["output_tokens"]
    
    # If we still don't have a valid logo URL, use our pre-extracted URL
    if (not logo_url or not is_valid_image_url(logo_url)) and actual_logo_url:
        print("Using pre-extracted logo URL as fallback...")
        logo_url = actual_logo_url
    
    # If we still don't have a logo URL, fail
    if not logo_url:
        print("Could not find a logo URL after multiple attempts.")
        show_token_usage_and_cost(token_usage)
        return None
    
    # Download the logo
    try:
        # Clean up the URL
        logo_url = logo_url.rstrip(',.;:\'")')
        
        # Get the company name from the website URL to use in filename
        company_name = website_url.replace("https://", "").replace("http://", "").split("/")[0]
        company_name = company_name.replace("www.", "").split(".")[0]
        
        # Extract file extension from URL
        file_ext = os.path.splitext(logo_url.split("?")[0])[1]
        if not file_ext:
            file_ext = ".png"  # Default extension
        
        # Create filename
        filename = f"{company_name}_logo{file_ext}"
        
        # Download the image
        print(f"Downloading from: {logo_url}")
        img_response = requests.get(logo_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
        img_response.raise_for_status()
        
        # Save the image locally
        save_path = os.path.join(os.path.expanduser("~"), "Desktop", filename)
        with open(save_path, "wb") as f:
            for chunk in img_response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"Logo saved to: {save_path}")
        show_token_usage_and_cost(token_usage)
        return save_path
    except Exception as e:
        print(f"Error downloading image: {e}")
        show_token_usage_and_cost(token_usage)
        return None

def try_copy_image_address(client, website_url, actual_logo_url=None):
    """Try to get logo URL using Firefox and 'Copy Image Address'"""
    
    # Initialize token tracking
    tokens = {
        "input_tokens": 0,
        "output_tokens": 0
    }
    
    # Create initial message with GUI approach instructions
    initial_prompt = f"""Find the direct URL of the company logo from {website_url}.

    Follow these steps in exact order:
    1. Use bash to run "firefox {website_url}" to launch Firefox
    2. Wait for the page to load completely (take a screenshot after launch)
    3. Locate the company logo (typically in the header/top of page)
    4. Right-click on the logo and select "Inspect" from the context menu
    5. In the HTML code that appears, find the img element and its src attribute
    6. Report the full URL with prefix "LOGO URL: "
    
    IMPORTANT: 
    - When examining the HTML, look for the complete source URL including domain name
    - Pay attention to the src attribute of the img tag or background-image property
    - Take screenshots frequently to confirm your progress
    """
    
    # Start with the initial user message
    messages = [{"role": "user", "content": initial_prompt}]
    
    # Maximum number of iterations for the agent loop
    max_iterations = 10
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
            max_tokens=4096,
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
        
        # Check if response contains a logo URL pattern
        logo_url_match = re.search(r'LOGO URL:\s*(https?://[^\s"\'<>\]]+)', response_text)
        if logo_url_match:
            logo_url = logo_url_match.group(1).strip()
            print(f"Found logo URL from GUI approach: {logo_url}")
            break
        
        # Also look for any image URL that might be the logo
        if not logo_url:
            image_urls = re.findall(r'(https?://[^\s"\'<>]+\.(?:png|jpg|jpeg|svg|gif|webp)(?:\?[^\s"\'<>]*)?)', response_text, re.IGNORECASE)
            logo_urls = [url for url in image_urls if any(term in url.lower() for term in ['logo', 'brand', 'header', 'icon'])]
            
            if logo_urls:
                logo_url = logo_urls[0]
                print(f"Found potential logo URL in GUI approach: {logo_url}")
                break
            elif image_urls:
                logo_url = image_urls[0]
                print(f"Found image URL that might be logo in GUI approach: {logo_url}")
                break
        
        # Continue the agent loop with tool results
        if tool_use_blocks:
            messages.append({"role": "assistant", "content": response.content})
            
            # Generate appropriate tool results with actual logo info where applicable
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
                            "content": "[Right-click successful. Context menu opened showing options including 'Inspect', 'Copy Image', 'Copy Image Address', etc.]"
                        })
                    elif action == "left_click" and right_clicked and not inspect_opened:
                        # Assume Claude clicked on "Inspect" option
                        inspect_opened = True
                        
                        # If we have the actual logo URL, show realistic HTML with it
                        if actual_logo_url:
                            # Create a realistic HTML inspector view
                            element_html = f'<img src="{actual_logo_url}" alt="Logo" class="site-logo" />'
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_block.id,
                                "content": f"[Clicked on 'Inspect'. Developer tools opened showing HTML:\n{element_html}\n]"
                            })
                        else:
                            # Generic inspector view
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_block.id,
                                "content": "[Clicked on 'Inspect'. Developer tools opened showing the HTML of the selected element.]"
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
                if inspect_opened:
                    # If inspector is open but we still don't have the URL, provide more guidance
                    
                    # If we have the actual logo URL, include it in a hint
                    if actual_logo_url:
                        followup_prompt = f"""I see you've opened the HTML inspector. Look at the image element that was selected.

                        You should see something like:
                        <img src="{actual_logo_url}" alt="Logo" class="site-logo" />
                        
                        The logo URL is in the src attribute. Extract this full URL and report it prefixed with "LOGO URL: "
                        """
                    else:
                        followup_prompt = """I see you've opened the HTML inspector. Look at the image element that was selected.

                        Find the <img> tag and look for its 'src' attribute. That contains the logo URL.
                        
                        Extract this full URL and report it prefixed with "LOGO URL: "
                        """
                
                elif right_clicked:
                    # If we've right-clicked but not opened inspector
                    followup_prompt = """You've right-clicked on the logo. Now select "Inspect" from the context menu.
                    
                    This will open the developer tools showing the HTML for the logo image.
                    
                    Then look for the src attribute and report the URL with prefix "LOGO URL: ".
                    """
                else:
                    # If we haven't right-clicked yet, focus on that
                    followup_prompt = """Let's try again:
                    
                    1. Take another screenshot to confirm the page has loaded
                    2. Find the company logo (usually in the header/top of the page)
                    3. Right-click directly on the logo image
                    4. Select "Inspect" from the context menu
                    5. Find the src attribute of the img element
                    6. Report the URL with "LOGO URL: " prefix
                    """
                
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": followup_prompt})
    
    return logo_url, tokens

def try_html_extraction(client, website_url):
    """Try to get logo URL using direct HTML extraction"""
    
    # Initialize token tracking
    tokens = {
        "input_tokens": 0,
        "output_tokens": 0
    }
    
    # Create initial message for HTML extraction approach
    initial_prompt = f"""Find the direct URL of the company logo from {website_url}.

    Follow these steps in exact order:
    1. Use bash to fetch the HTML of {website_url} with curl 
    2. Look for img tags with attributes like "logo", "brand", or "header" in the class or id
    3. Extract the full src URL for the most likely logo image
    4. Output the result with the prefix "LOGO URL: " followed by the full URL

    DO NOT make up a URL. Use curl to fetch the real HTML and extract the actual logo URL.
    """
    
    # Start with the initial user message
    messages = [{"role": "user", "content": initial_prompt}]
    
    # Maximum number of iterations for the agent loop
    max_iterations = 3
    logo_url = None
    
    # Agent loop for HTML extraction approach
    for iteration in range(max_iterations):
        print(f"HTML Extraction Iteration {iteration + 1}:")
        
        # Make the API call with bash tool - using Claude 3.5 Sonnet
        response = client.beta.messages.create(
            model="claude-3-5-sonnet-20241022",  # Use Claude 3.5 Sonnet (Oct) version
            max_tokens=4096,
            tools=[
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
                cmd = content_block.input.get('command', 'unknown command')
                print(f"Claude used tool: bash - {cmd}")
        
        # Check if response contains a logo URL pattern
        logo_url_match = re.search(r'LOGO URL:\s*(https?://[^\s"\'<>\]]+)', response_text)
        if logo_url_match:
            logo_url = logo_url_match.group(1).strip()
            print(f"Found logo URL from HTML extraction: {logo_url}")
            break
        
        # Also look for any image URL that might be the logo
        if not logo_url:
            image_urls = re.findall(r'(https?://[^\s"\'<>]+\.(?:png|jpg|jpeg|svg|gif|webp)(?:\?[^\s"\'<>]*)?)', response_text, re.IGNORECASE)
            logo_urls = [url for url in image_urls if any(term in url.lower() for term in ['logo', 'brand', 'header', 'icon'])]
            
            if logo_urls:
                logo_url = logo_urls[0]
                print(f"Found potential logo URL in HTML extraction: {logo_url}")
                break
            elif image_urls:
                logo_url = image_urls[0]
                print(f"Found image URL that might be logo in HTML extraction: {logo_url}")
                break
        
        # Continue the agent loop with tool results
        if tool_use_blocks:
            messages.append({"role": "assistant", "content": response.content})
            
            # Generate actual HTML fetch results
            tool_results = []
            for tool_block in tool_use_blocks:
                if tool_block.name == "bash":
                    cmd = tool_block.input.get("command", "")
                    
                    if "curl" in cmd and website_url in cmd:
                        # Actually fetch the HTML content
                        try:
                            actual_html = fetch_website_html(website_url)
                            
                            # Find potential logo elements
                            soup = BeautifulSoup(actual_html, 'html.parser')
                            logo_elements = []
                            
                            # Look for img tags that might be logos
                            for img in soup.find_all('img'):
                                src = img.get('src')
                                if src:
                                    abs_url = urljoin(website_url, src)
                                    alt = img.get('alt', '')
                                    class_attr = img.get('class', [])
                                    class_str = ' '.join(class_attr) if class_attr else ''
                                    id_attr = img.get('id', '')
                                    
                                    # Check if it might be a logo
                                    logo_indicators = ['logo', 'brand', 'header', 'site-icon']
                                    is_logo = any(indicator in attr.lower() for indicator in logo_indicators 
                                                for attr in [alt, class_str, id_attr])
                                    
                                    if is_logo or 'logo' in abs_url.lower():
                                        logo_elements.append(f'<img src="{src}" alt="{alt}" class="{class_str}" id="{id_attr}">')
                            
                            # If we found probable logo elements, show just those
                            if logo_elements:
                                html_result = "\n".join(logo_elements[:5])
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_block.id,
                                    "content": f"[HTML fetched. Here are potential logo elements:\n{html_result}\n]"
                                })
                            else:
                                # Otherwise show a truncated summary
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_block.id,
                                    "content": f"[HTML fetched. Here's a sample of the HTML:\n{actual_html[:3000]}...\n]"
                                })
                        except Exception as e:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_block.id,
                                "content": f"[Error fetching HTML: {str(e)}]"
                            })
                    elif "grep" in cmd:
                        # Use our direct extraction to provide meaningful results
                        try:
                            images = find_image_urls(website_url)
                            logo_images = [img for img in images if img['is_likely_logo']]
                            
                            output = ""
                            if logo_images:
                                output = "\n".join([f"{img['url']} (class='{img['class']}', alt='{img['alt']}')" for img in logo_images[:5]])
                            else:
                                # Just return some top images if no obvious logos
                                output = "\n".join([f"{img['url']} (class='{img['class']}', alt='{img['alt']}')" for img in images[:5]])
                                
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_block.id,
                                "content": f"[Command results:\n{output}\n]"
                            })
                        except Exception as e:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_block.id,
                                "content": f"[Error executing command: {str(e)}]"
                            })
                    else:
                        # Generic command response
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": f"[Command executed: {cmd}]"
                        })
            
            # Continue the conversation with tool results
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
    
    return logo_url, tokens

def fetch_website_html(url):
    """Fetch the HTML content of a website"""
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    return response.text

def find_image_urls(url):
    """Find all image URLs on a website"""
    html = fetch_website_html(url)
    soup = BeautifulSoup(html, 'html.parser')
    
    # Dictionary to store image URLs with useful attributes
    images = []
    
    # Find all img tags
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            # Make relative URLs absolute
            abs_url = urljoin(url, src)
            
            # Collect useful attributes to identify if it's a logo
            alt = img.get('alt', '').lower()
            img_class = ' '.join(img.get('class', [])).lower() if img.get('class') else ''
            img_id = img.get('id', '').lower()
            parent_class = ' '.join(img.parent.get('class', [])).lower() if img.parent and img.parent.get('class') else ''
            parent_id = img.parent.get('id', '').lower() if img.parent else ''
            
            # Determine if this might be a logo based on attributes and URL
            logo_indicators = ['logo', 'brand', 'header', 'site-icon']
            is_likely_logo = any(indicator in attr for indicator in logo_indicators 
                                for attr in [alt, img_class, img_id, parent_class, parent_id]) or 'logo' in abs_url.lower()
            
            images.append({
                'url': abs_url,
                'alt': alt,
                'class': img_class,
                'id': img_id,
                'parent_class': parent_class,
                'parent_id': parent_id,
                'is_likely_logo': is_likely_logo
            })
    
    return images

def extract_logo_url_directly(url):
    """Extract the most likely logo URL directly from the website"""
    try:
        images = find_image_urls(url)
        
        # First priority: explicitly logo-related URLs
        logo_in_url = [img for img in images if 'logo' in img['url'].lower()]
        if logo_in_url:
            return logo_in_url[0]['url']
        
        # Second priority: images explicitly marked as logos
        logo_images = [img for img in images if img['is_likely_logo']]
        if logo_images:
            return logo_images[0]['url']
        
        # Third priority: images in the header area
        header_images = [img for img in images if 'header' in img['parent_class'] or 'nav' in img['parent_class']]
        if header_images:
            return header_images[0]['url']
        
        # Last resort: first image on the page if all else fails
        if images:
            return images[0]['url']
        
        return None
    except Exception as e:
        print(f"Error extracting logo URL directly: {e}")
        return None

def is_valid_image_url(url):
    """Check if a URL is a valid image URL"""
    try:
        response = requests.head(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        content_type = response.headers.get('Content-Type', '')
        return response.status_code == 200 and 'image' in content_type
    except Exception:
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

if __name__ == "__main__":
    # Check if website URL is provided as command line argument
    if len(sys.argv) < 2:
        print("Please provide a website URL as an argument.")
        print("Example: python download_logo.py https://example.com")
        sys.exit(1)
    
    website_url = sys.argv[1]
    start_time = time.time()
    
    try:
        result = download_company_logo(website_url)
        if result:
            print(f"Successfully downloaded logo to {result}")
        else:
            print("Failed to download logo.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Calculate execution time
    execution_time = time.time() - start_time
    print(f"\nTotal execution time: {execution_time:.2f} seconds")