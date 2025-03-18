from abc import ABC, abstractmethod
import os
import time
import re

from ..utils import url as url_utils
from ..utils import cache as cache_utils
from ..utils import image as image_utils
from ..config import OUTPUT_DIR, TEXT_BASED_LOGO

class BaseExtractor(ABC):
    """
    Base class for logo extractors
    
    This abstract base class defines the interface for logo extractors.
    All concrete extractor classes should inherit from this class.
    """
    
    def __init__(self, website_url):
        """
        Initialize the extractor
        
        Args:
            website_url (str): URL of the website to extract logo from
        """
        self.website_url = url_utils.normalize_url(website_url)
        self.domain = url_utils.get_domain_name(website_url)
        self.start_time = None
    
    def extract_logo(self, force_refresh=False):
        """
        Extract logo from the website
        
        Args:
            force_refresh (bool): Whether to bypass cache
            
        Returns:
            str: Path to the downloaded logo image, or None if not found
        """
        self.start_time = time.time()
        
        # Check cache first
        if not force_refresh:
            cached_result = cache_utils.get_cached_result(self.website_url)
            if cached_result:
                # Check if we previously determined this is a text-based logo
                if cached_result.get('text_based_logo', False):
                    print("Cached result indicates this site uses a text-based logo with no image file.")
                    self._log_execution_time()
                    return TEXT_BASED_LOGO
                
                cached_logo_url = cached_result.get('logo_url')
                if cached_logo_url and cache_utils.is_cache_valid(cached_result):
                    print(f"Found cached logo URL: {cached_logo_url}")
                    
                    # Check if the cached URL has hero/banner terms that indicate it's not a real logo
                    if image_utils.is_likely_hero_image(cached_logo_url):
                        print("Cached URL appears to be a hero image, not a logo. Clearing cache for this URL.")
                        cache_utils.clear_cache(self.website_url)
                    # If it's not a hero image, check if it's valid
                    elif image_utils.is_valid_image_url(cached_logo_url):
                        return self._download_and_process_logo(cached_logo_url)
                    else:
                        print("Cached logo URL is invalid. Clearing cache entry.")
                        cache_utils.clear_cache(self.website_url)
        
        # Perform extraction
        extraction_result = self._perform_extraction()
        self._log_execution_time()
        
        # Check if we determined this is a text-based logo site
        if extraction_result == TEXT_BASED_LOGO:
            print("This site uses a text-based logo with no image file.")
            cache_utils.cache_text_based_logo(self.website_url, method=self._get_method_name())
            return TEXT_BASED_LOGO
        
        # Check if the extraction result is a list (from Google extractor)
        if isinstance(extraction_result, list):
            # Process each URL in the list until we find a valid one
            for logo_url in extraction_result:
                if logo_url and image_utils.is_valid_image_url(logo_url) and not image_utils.is_likely_hero_image(logo_url) and not image_utils.is_likely_icon_not_logo(logo_url):
                    print(f"Successfully found logo URL in list using {self._get_method_name()}: {logo_url}")
                    
                    # Cache the URL
                    cache_utils.cache_logo_url(self.website_url, logo_url, method=self._get_method_name())
                    
                    # Download and return
                    return self._download_and_process_logo(logo_url)
                    
            # If we get here, none of the URLs were valid
            print(f"No valid logo found in URL list using {self._get_method_name()}.")
            return None
        
        # Handle the case where it's a single URL (traditional extractors)
        logo_url = extraction_result
        
        # If we found a valid logo URL, use it
        if logo_url and image_utils.is_valid_image_url(logo_url) and not image_utils.is_likely_hero_image(logo_url) and not image_utils.is_likely_icon_not_logo(logo_url):
            print(f"Successfully found logo URL using {self._get_method_name()}: {logo_url}")
            
            # Cache the URL
            cache_utils.cache_logo_url(self.website_url, logo_url, method=self._get_method_name())
            
            # Download and return
            return self._download_and_process_logo(logo_url)
        
        # If extraction failed, return None
        print(f"No valid logo found using {self._get_method_name()}.")
        return None
    
    @abstractmethod
    def _perform_extraction(self):
        """
        Perform the actual logo extraction
        
        This method should be implemented by concrete extractor classes.
        
        Returns:
            str: Logo URL, special constant TEXT_BASED_LOGO, or None if not found
        """
        pass
    
    def _download_and_process_logo(self, logo_url):
        """
        Download and process a logo image
        
        Args:
            logo_url (str): URL of the logo to download
            
        Returns:
            str: Path to the downloaded logo image, or None on error
        """
        try:
            # Create a filename based on the website domain
            domain = self.domain
            
            # Handle special characters in domain
            domain = re.sub(r'[^a-zA-Z0-9\.]', '_', domain)
            
            # Detect file extension from URL or default to png if not found
            file_ext = os.path.splitext(logo_url.split('?')[0])[1].lower() or '.png'
            
            # Clean up file extension
            if not file_ext.startswith('.'):
                file_ext = '.' + file_ext
                
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff']
            if file_ext not in valid_extensions:
                file_ext = '.png'  # Default to png for unrecognized extensions
                
            filename = f"{domain}_logo{file_ext}"
            output_path = os.path.join(OUTPUT_DIR, filename)
            
            # Download the image
            downloaded_path = image_utils.download_image(logo_url, output_path)
            
            if downloaded_path:
                # Process the image (convert WebP to PNG and auto-crop)
                result = image_utils.process_logo_image(downloaded_path)
                # Extract only the processed path from the result tuple
                processed_path, is_valid, issues = result
                
                # Log issues if any
                if issues:
                    print(f"Processing issues: {', '.join(issues)}")
                
                return processed_path
            
            return None
            
        except Exception as e:
            print(f"Error downloading and processing logo: {e}")
            return None
    
    def _get_method_name(self):
        """
        Get the name of the extraction method
        
        Returns:
            str: Name of the extraction method
        """
        return self.__class__.__name__.replace('Extractor', '').lower()
    
    def _log_execution_time(self):
        """
        Log the execution time
        """
        if self.start_time:
            execution_time = time.time() - self.start_time
            print(f"Execution time for {self._get_method_name()}: {execution_time:.2f} seconds") 