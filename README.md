# Logo Bot

A modular toolkit for extracting and downloading logos from websites, with support for both CLI and API interfaces.

## Features

- Extract logos from websites using multiple approaches
- Handle text-based logos and image-based logos
- Convert WebP images to PNG format
- Auto-crop logos to remove transparent backgrounds
- Cache extraction results for improved performance
- API endpoints for integration with other applications
- Quality assurance checks for downloaded logos
- Google Image Search integration for higher quality logos
- Intelligent logo comparison and selection

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/logo_bot.git
cd logo_bot
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file for the Anthropic API key (optional, for Claude-based extraction):
```bash
echo "ANTHROPIC_API_KEY=your_api_key_here" > .env
```

## Usage

### Command Line Interface (CLI)

Extract a logo from a website:
```bash
python run.py example.com
```

Force refresh the cache:
```bash
python run.py example.com --force-refresh
```

Skip Claude-based extraction fallback:
```bash
python run.py example.com --no-claude
```

Skip Google Images extraction:
```bash
python run.py example.com --no-google
```

Specify a ChromeDriver path (only needed if using the slower Selenium-based version):
```bash
python run.py example.com --chromedriver /path/to/chromedriver
```

### API Server

Start the API server:
```bash
python run.py --api
```

Configure host and port:
```bash
python run.py --api --host 0.0.0.0 --port 8080
```

### API Endpoints

The API server provides the following endpoints:

- `GET /` - Information about the API
- `POST /extract` - Extract a logo from a website
- `GET /cache` - Get cached information for a website
- `DELETE /cache` - Clear cache for a website or all websites
- `GET /logos` - List all downloaded logos
- `DELETE /logos/{domain}` - Delete a logo for a domain

### API Example

Extract a logo from a website using the API:
```bash
curl -X POST "http://localhost:8000/extract" \
  -H "Content-Type: application/json" \
  -d '{"url": "example.com", "force_refresh": false, "use_claude_fallback": true}'
```

## Architecture

- `logo_bot/` - Main package
  - `config.py` - Configuration and constants
  - `main.py` - Main entry point
  - `api/` - API module
    - `routes.py` - API endpoints
  - `extractors/` - Logo extraction modules
    - `base.py` - Base extractor class
    - `beautifulsoup.py` - BeautifulSoup-based extraction
    - `claude.py` - Claude-based extraction
    - `google.py` - Google Image Search extraction
  - `utils/` - Utility modules
    - `cache.py` - Caching utilities
    - `image.py` - Image processing utilities
    - `url.py` - URL handling utilities
    - `qa.py` - Quality assurance utilities

## Logo Quality Assurance

The logo bot performs several quality checks on downloaded logos:

- **Corruption detection**: Verifies the image file is valid and not corrupted
- **All-white/transparent detection**: Checks if the logo is entirely white or transparent
- **Size validation**: Ensures the logo meets minimum size requirements
- **Format prioritization**: Prefers SVG > PNG > JPG for better quality
- **Similarity comparison**: When multiple sources provide logos, compares them for consistency

When both website extraction and Google Image Search find logos, they are compared to:
1. Verify they represent the same logo (preventing incorrect logos)
2. Select the best quality version based on format and resolution
3. Provide quality metrics in the API response

## License

MIT 