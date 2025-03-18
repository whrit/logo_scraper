import os
import time
import unittest
from pathlib import Path

from logo_bot.extractors.google import GoogleExtractor
from logo_bot.config import OUTPUT_DIR

class TestGoogleExtractor(unittest.TestCase):
    """Test case for GoogleExtractor"""
    
    def setUp(self):
        """Set up test environment"""
        # Ensure output directory exists
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Remove any test output files
        for f in Path(OUTPUT_DIR).glob("test_domain_logo.*"):
            f.unlink()
            
    def tearDown(self):
        """Clean up after test"""
        # Remove any test output files
        for f in Path(OUTPUT_DIR).glob("test_domain_logo.*"):
            f.unlink()
    
    def test_extraction_speed(self):
        """Test that Google extraction is fast"""
        # Test domains
        test_domains = [
            "apple.com",
            "microsoft.com",
            "amazon.com"
        ]
        
        for domain in test_domains:
            # Create a test URL
            url = f"https://{domain}"
            
            # Time the extraction
            start_time = time.time()
            
            # Create extractor
            extractor = GoogleExtractor(url)
            
            # Extract logo
            result = extractor.extract_logo(force_refresh=True)
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Output results
            print(f"\nGoogle extraction for {domain}:")
            print(f"  Elapsed time: {elapsed_time:.2f} seconds")
            print(f"  Result: {result}")
            
            # Verify that the extraction took less than 10 seconds
            # This is much faster than the Selenium-based version which typically takes 30-60 seconds
            self.assertLess(elapsed_time, 10, f"Extraction for {domain} took too long: {elapsed_time:.2f} seconds")
            
            # If a logo was found, verify the file exists
            if result:
                self.assertTrue(os.path.exists(result), f"Logo file does not exist: {result}")

if __name__ == "__main__":
    unittest.main() 