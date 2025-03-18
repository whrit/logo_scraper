import os
import json
import hashlib
import time

from ..config import CACHE_DIR

def get_cache_key(url):
    """
    Generate a cache key for a URL
    
    Args:
        url (str): URL to generate cache key for
        
    Returns:
        str: Cache key (MD5 hash of URL)
    """
    return hashlib.md5(url.encode()).hexdigest()

def get_cache_path(url):
    """
    Get the cache file path for a URL
    
    Args:
        url (str): URL to get cache path for
        
    Returns:
        str: Path to cache file
    """
    cache_key = get_cache_key(url)
    return os.path.join(CACHE_DIR, f"{cache_key}.json")

def get_cached_result(url):
    """
    Get cached result for a URL if it exists
    
    Args:
        url (str): URL to get cached result for
        
    Returns:
        dict: Cached result, or None if not found
    """
    cache_file = get_cache_path(url)
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading cache file: {e}")
    
    return None

def cache_text_based_logo(url, method="beautifulsoup"):
    """
    Cache that a website uses a text-based logo
    
    Args:
        url (str): Website URL
        method (str): Method used to detect text-based logo
        
    Returns:
        bool: True if successful, False otherwise
    """
    cache_file = get_cache_path(url)
    
    try:
        with open(cache_file, 'w') as f:
            json.dump({
                'website_url': url,
                'text_based_logo': True,
                'timestamp': time.time(),
                'method': method
            }, f)
        return True
    except Exception as e:
        print(f"Error caching text-based logo: {e}")
        return False

def cache_logo_url(url, logo_url, method="beautifulsoup"):
    """
    Cache a logo URL for a website
    
    Args:
        url (str): Website URL
        logo_url (str): Logo URL
        method (str): Method used to find logo URL
        
    Returns:
        bool: True if successful, False otherwise
    """
    cache_file = get_cache_path(url)
    
    try:
        with open(cache_file, 'w') as f:
            json.dump({
                'website_url': url,
                'logo_url': logo_url,
                'timestamp': time.time(),
                'method': method
            }, f)
        return True
    except Exception as e:
        print(f"Error caching logo URL: {e}")
        return False

def is_cache_valid(cache_data, max_age=7*24*60*60):
    """
    Check if cached data is still valid (not too old)
    
    Args:
        cache_data (dict): Cached data
        max_age (int): Maximum age in seconds (default: 7 days)
        
    Returns:
        bool: True if cache is valid, False otherwise
    """
    if not cache_data or 'timestamp' not in cache_data:
        return False
        
    current_time = time.time()
    cache_time = cache_data['timestamp']
    
    return (current_time - cache_time) < max_age

def clear_cache(url=None):
    """
    Clear cache for a specific URL or all URLs
    
    Args:
        url (str): URL to clear cache for, or None to clear all
        
    Returns:
        int: Number of cache files removed
    """
    count = 0
    
    if url:
        # Clear cache for a specific URL
        cache_file = get_cache_path(url)
        if os.path.exists(cache_file):
            os.remove(cache_file)
            count = 1
    else:
        # Clear all cache files
        if os.path.exists(CACHE_DIR):
            for file in os.listdir(CACHE_DIR):
                if file.endswith('.json'):
                    os.remove(os.path.join(CACHE_DIR, file))
                    count += 1
    
    return count 