import re
import requests
from urllib.parse import urljoin, urlparse

from ..config import HEADERS

def normalize_url(url):
    """
    Normalize URL by adding https:// prefix if missing
    
    Args:
        url (str): URL to normalize
        
    Returns:
        str: Normalized URL
    """
    if url and not url.startswith(('http://', 'https://')):
        return 'https://' + url
    return url

def fetch_website_html(url, timeout=10):
    """
    Fetch the HTML content of a website with timeout and error handling
    
    Args:
        url (str): URL to fetch
        timeout (int): Timeout in seconds
        
    Returns:
        str: HTML content of the website, or empty string on error
    """
    # Normalize URL by adding https:// if missing
    url = normalize_url(url)
    
    # Special handling for Asigra website
    if 'asigra.com' in url:
        try:
            print("Using specialized fetching for Asigra website...")
            
            # Try with standard request first but no special headers
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200 and response.text and len(response.text.strip()) > 1000:
                return response.text
                
            # Try with specific User-Agent that works well
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br'
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response.text
        except Exception as e:
            print(f"Error with specialized fetching for Asigra: {e}")
    
    # Standard approach for other websites
    for attempt in range(3):  # Try up to 3 times
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Check if the response is successfully decoded
            if not response.text or len(response.text.strip()) < 100:
                # If response content looks binary or compressed, try with different approach
                print(f"Response may be compressed, trying with different method (attempt {attempt+1})")
                session = requests.Session()
                # Explicitly set accept-encoding to receive uncompressed content
                headers = HEADERS.copy()
                headers['Accept-Encoding'] = 'identity'
                r = session.get(url, headers=headers, timeout=timeout)
                if r.status_code == 200 and r.text and len(r.text.strip()) > 100:
                    return r.text
                    
                # If that fails, try with a standard GET without custom headers
                r = requests.get(url, timeout=timeout)
                if r.status_code == 200:
                    return r.text
            else:
                return response.text
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching HTML (attempt {attempt+1}): {e}")
            if attempt == 2:  # Last attempt
                return ""
    
    return ""

def get_domain_name(url):
    """
    Extract domain name from a URL
    
    Args:
        url (str): URL to extract domain from
        
    Returns:
        str: Domain name
    """
    url = normalize_url(url)
    domain = re.sub(r'^https?://', '', url).rstrip('/')
    domain = domain.replace('www.', '')
    return domain

def get_base_url(url):
    """
    Get base URL (scheme + netloc) from a URL
    
    Args:
        url (str): URL to get base from
        
    Returns:
        str: Base URL
    """
    url = normalize_url(url)
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"

def make_absolute_url(base_url, relative_url):
    """
    Make a relative URL absolute using a base URL
    
    Args:
        base_url (str): Base URL
        relative_url (str): Relative URL
        
    Returns:
        str: Absolute URL
    """
    if relative_url.startswith('//'):
        return 'https:' + relative_url
    elif relative_url.startswith('/'):
        base = get_base_url(base_url)
        return base + relative_url
    elif not relative_url.startswith(('http://', 'https://', 'data:')):
        return urljoin(base_url, relative_url)
    else:
        return relative_url

def fix_data_uri(url):
    """
    Fix malformed data URIs and convert them to proper format
    
    Args:
        url (str): URL to fix
        
    Returns:
        str: Fixed URL
    """
    # Check if this is a malformed data URI (has https://data: prefix)
    if url and url.startswith('https://data:'):
        # Fix by removing the 'https://' prefix
        url = url.replace('https://data:', 'data:')
    
    return url 