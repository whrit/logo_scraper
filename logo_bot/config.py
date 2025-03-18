import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent

# Cache directory
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "logo_bot")
os.makedirs(CACHE_DIR, exist_ok=True)

# Output directory for logo files
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

# Return types for logo extraction
TEXT_BASED_LOGO = "TEXT_BASED_LOGO"

# Claude API configuration
CLAUDE_TOKEN_COSTS = {
    "system_prompt_tokens": 313,  # Tool use system prompt tokens for Claude 3.5 Sonnet
    "computer_tool_tokens": 683,  # Additional tokens for computer_20241022
    "bash_tool_tokens": 245       # Additional tokens for bash_20241022
}

# Pricing per million tokens (as of Oct 2024)
CLAUDE_PRICING = {
    "input_token_cost_per_million": 3.00,  # $3.00 per million input tokens
    "output_token_cost_per_million": 15.00  # $15.00 per million output tokens
} 