#!/usr/bin/env python
import os
import sys
import datetime
import logging
import json
import time
import traceback
from pathlib import Path

# Add parent directory to path so we can import logo_bot modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from logo_bot.extractors.google import GoogleExtractor
from logo_bot.config import CACHE_DIR

# Configure logging
log_dir = os.path.join(CACHE_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"extractor_check_{datetime.datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('extractor_check')

# Test domains - include a variety of well-known sites that should have logos
TEST_DOMAINS = [
    "apple.com",
    "microsoft.com", 
    "amazon.com",
    "google.com",
    "facebook.com"
]

def test_google_extractor(domain, chromedriver_path=None):
    """Test the Google extractor for a given domain"""
    logger.info(f"Testing Google extraction for {domain}")
    
    try:
        extractor = GoogleExtractor(f"https://{domain}", chromedriver_path)
        
        # First test the fast method
        logger.info(f"Testing fast extraction method for {domain}")
        start_time = time.time()
        results = extractor._extract_logo_urls_with_selenium_fast(f"{domain} logo")
        elapsed_time = time.time() - start_time
        
        if results and len(results) > 0:
            logger.info(f"✅ Fast method succeeded for {domain} in {elapsed_time:.2f}s - found {len(results)} URLs")
            for i, url in enumerate(results):
                logger.info(f"  URL {i+1}: {url}")
            return True, "fast", results, elapsed_time
        else:
            logger.warning(f"❌ Fast method failed for {domain} in {elapsed_time:.2f}s")
            
            # Try the original method as fallback
            logger.info(f"Testing original extraction method for {domain}")
            start_time = time.time()
            results = extractor._extract_logo_urls_with_selenium(f"{domain} logo")
            elapsed_time = time.time() - start_time
            
            if results and len(results) > 0:
                logger.info(f"✅ Original method succeeded for {domain} in {elapsed_time:.2f}s - found {len(results)} URLs")
                for i, url in enumerate(results):
                    logger.info(f"  URL {i+1}: {url}")
                return True, "original", results, elapsed_time
            else:
                logger.error(f"❌ Both methods failed for {domain}")
                return False, None, [], elapsed_time
    
    except Exception as e:
        logger.error(f"Error testing Google extraction for {domain}: {str(e)}")
        logger.error(traceback.format_exc())
        return False, None, [], 0

def analyze_results(results):
    """Analyze test results and determine if selectors need updating"""
    success_count = sum(1 for r in results if r["success"])
    total_count = len(results)
    success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
    
    logger.info(f"Overall success rate: {success_rate:.1f}% ({success_count}/{total_count})")
    
    if success_rate < 60:
        logger.error("⚠️ CRITICAL: Google extraction success rate is too low! Selectors likely need updating.")
        return False
    elif success_rate < 80:
        logger.warning("⚠️ WARNING: Google extraction success rate is below optimal. Consider checking selectors.")
        return True
    else:
        logger.info("✅ Google extraction is working well.")
        return True
    
def generate_report(results):
    """Generate a report of the test results"""
    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "success_rate": (sum(1 for r in results if r["success"]) / len(results)) * 100,
        "results": results,
        "fast_method_success_rate": (sum(1 for r in results if r["method"] == "fast") / 
                                    max(1, sum(1 for r in results if r["success"]))) * 100,
        "average_time_fast": sum(r["time"] for r in results if r["method"] == "fast") / 
                            max(1, sum(1 for r in results if r["method"] == "fast")),
        "average_time_original": sum(r["time"] for r in results if r["method"] == "original") / 
                                max(1, sum(1 for r in results if r["method"] == "original")),
    }
    
    # Save report to file
    report_file = os.path.join(log_dir, f"extractor_report_{datetime.datetime.now().strftime('%Y%m%d')}.json")
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Report saved to {report_file}")
    return report

def suggest_selector_updates(report):
    """Analyze failures and suggest possible selector updates"""
    if report["success_rate"] > 80:
        return []
    
    # Sample suggestions based on common patterns
    suggestions = [
        "Try adding 'img.rg_i.Q4LuWd' to the fast extraction selectors",
        "Try adding 'div.isv-r img' to the fast extraction selectors", 
        "Try updating the page source regex pattern to include r'\"ou\":\"(https?://[^\"]+)\"' and r'\"tu\":\"(https?://[^\"]+)\"'"
    ]
    
    return suggestions

def main():
    """Main function to run the extractor check"""
    logger.info("Starting Google extractor check")
    
    results = []
    
    for domain in TEST_DOMAINS:
        success, method, urls, elapsed_time = test_google_extractor(domain)
        results.append({
            "domain": domain,
            "success": success,
            "method": method,
            "urls_found": len(urls),
            "time": elapsed_time
        })
    
    is_working = analyze_results(results)
    report = generate_report(results)
    
    if not is_working:
        suggestions = suggest_selector_updates(report)
        logger.info("Suggestions for fixing selectors:")
        for suggestion in suggestions:
            logger.info(f"- {suggestion}")
    
    logger.info("Extractor check completed")
    return is_working

if __name__ == "__main__":
    main() 