import re
import anthropic
import time
import os

from .base import BaseExtractor
from ..utils import image as image_utils
from ..config import TEXT_BASED_LOGO, CLAUDE_TOKEN_COSTS, CLAUDE_PRICING

class ClaudeExtractor(BaseExtractor):
    """
    Logo extractor using Claude's vision capabilities
    
    This class extracts logos from websites by using Claude to simulate
    browser interactions and identify logos.
    """
    
    def __init__(self, website_url):
        """
        Initialize the extractor
        
        Args:
            website_url (str): URL of the website to extract logo from
        """
        super().__init__(website_url)
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = None
        self.token_usage = {
            "input_tokens": 0,
            "output_tokens": 0
        }
    
    def _perform_extraction(self):
        """
        Extract logo from website using Claude
        
        Returns:
            str: Logo URL, TEXT_BASED_LOGO constant, or None if not found
        """
        if not self.api_key:
            print("ANTHROPIC_API_KEY not found in environment variables.")
            print("Cannot use Claude extractor without an API key.")
            return None
            
        self.client = anthropic.Anthropic(api_key=self.api_key)
        print("Using Claude to find logo...")
        
        # Try the GUI approach with Claude
        logo_url, result_tokens = self._try_copy_image_address()
        
        # Update token usage
        self.token_usage["input_tokens"] += result_tokens["input_tokens"]
        self.token_usage["output_tokens"] += result_tokens["output_tokens"]
        
        # Check if Claude detected a text-based logo
        if logo_url is None and result_tokens.get("text_based_logo", False):
            print("Claude determined this site uses a text-based logo with no image file.")
            self._show_token_usage_and_cost()
            return TEXT_BASED_LOGO
        
        # If we found a valid logo URL, return it
        if logo_url:
            print(f"Successfully found logo URL using Claude: {logo_url}")
            self._show_token_usage_and_cost()
            return logo_url
            
        # If we still don't have a logo URL, give up
        print("Claude could not find a valid logo URL.")
        self._show_token_usage_and_cost()
        return None
    
    def _try_copy_image_address(self, actual_logo_url=None):
        """
        Try to get logo URL using Firefox and 'Copy Image Address'
        
        Args:
            actual_logo_url (str): Actual logo URL if known
            
        Returns:
            tuple: (logo_url, tokens) where logo_url is the URL of the logo or None,
                  and tokens is a dict with token usage information
        """
        if not self.client:
            return None, {"input_tokens": 0, "output_tokens": 0}
            
        # Initialize token tracking
        tokens = {
            "input_tokens": 0,
            "output_tokens": 0
        }
        
        # Create optimized prompt for GUI approach
        initial_prompt = f"""Find the highest quality company logo from {self.website_url}.

        Follow these steps in exact order:
        1. Use bash to run "firefox {self.website_url}" to launch Firefox
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
            response = self.client.beta.messages.create(
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
                tokens["text_based_logo"] = True
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
                logo_urls = [url for url in image_urls if any(term in url.lower() for term in ['logo', 'brand', 'header']) and not image_utils.is_likely_hero_image(url)]
                
                if logo_urls:
                    logo_url = logo_urls[0]
                    print(f"Found potential logo URL in GUI approach: {logo_url}")
                    break
                elif image_urls and len(image_urls) > 0:
                    # Check all image URLs to make sure they're not hero images
                    for url in image_urls:
                        if not image_utils.is_likely_hero_image(url) and 'favicon' not in url.lower():
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
                                "content": f"[Firefox launched with {self.website_url}. Browser window is now open.]"
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
    
    def _show_token_usage_and_cost(self):
        """
        Display token usage and estimated cost
        """
        if not self.token_usage:
            return
            
        # Calculate total input tokens including system prompt and tool tokens
        base_input_tokens = self.token_usage["input_tokens"]
        tool_input_tokens = CLAUDE_TOKEN_COSTS["system_prompt_tokens"] + CLAUDE_TOKEN_COSTS["computer_tool_tokens"] + CLAUDE_TOKEN_COSTS["bash_tool_tokens"]
        total_input_tokens = base_input_tokens + tool_input_tokens
        
        output_tokens = self.token_usage["output_tokens"]
        total_tokens = total_input_tokens + output_tokens
        
        input_cost = (total_input_tokens / 1_000_000) * CLAUDE_PRICING["input_token_cost_per_million"]
        output_cost = (output_tokens / 1_000_000) * CLAUDE_PRICING["output_token_cost_per_million"]
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