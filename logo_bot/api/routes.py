import os
import base64
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Union
import time
import json
from pathlib import Path

from ..extractors.beautifulsoup import BeautifulSoupExtractor
from ..extractors.claude import ClaudeExtractor
from ..utils import url as url_utils
from ..utils import cache as cache_utils
from ..config import TEXT_BASED_LOGO, OUTPUT_DIR

app = FastAPI(
    title="Logo Bot API",
    description="API for extracting company logos from websites",
    version="1.0.0"
)

# Define request and response models
class LogoExtractionRequest(BaseModel):
    url: str = Field(..., description="URL of the website to extract logo from")
    force_refresh: bool = Field(False, description="Whether to bypass cache")
    use_claude_fallback: bool = Field(True, description="Whether to use Claude as fallback if direct extraction fails")
    use_google: bool = Field(True, description="Whether to use Google Images as an additional source")
    chromedriver_path: Optional[str] = Field(None, description="Path to ChromeDriver executable (for Google extraction)")
    
class LogoExtractionResponse(BaseModel):
    url: str = Field(..., description="URL of the website that was processed")
    success: bool = Field(..., description="Whether logo extraction was successful")
    logo_url: Optional[str] = Field(None, description="URL of the extracted logo")
    logo_path: Optional[str] = Field(None, description="Path to the downloaded logo file")
    logo_data: Optional[str] = Field(None, description="Base64-encoded logo image data")
    text_based_logo: bool = Field(False, description="Whether the website uses a text-based logo")
    message: str = Field(..., description="Status message")
    execution_time: float = Field(..., description="Execution time in seconds")
    quality: Optional[dict] = Field(None, description="Logo quality information if available")
    source: Optional[str] = Field(None, description="Source of the selected logo (website, google, or mixed)")
    similarity_score: Optional[float] = Field(None, description="Similarity score between logos if multiple sources were used")

# API routes
@app.get("/")
async def root():
    """Root endpoint returning API information"""
    return {
        "name": "Logo Bot API",
        "version": "1.0.0",
        "description": "API for extracting company logos from websites",
        "documentation": "/docs"
    }

@app.post("/extract", response_model=LogoExtractionResponse)
async def extract_logo(request: LogoExtractionRequest):
    """
    Extract logo from a website
    
    This endpoint extracts a company logo from a website, 
    downloads it, and returns information about the logo.
    """
    start_time = time.time()
    
    try:
        # Normalize URL
        website_url = url_utils.normalize_url(request.url)
        domain = url_utils.get_domain_name(website_url)
        
        website_logo = None
        google_logo = None
        quality_info = None
        
        # First try BeautifulSoup extraction (faster and cheaper)
        print(f"Extracting logo from {website_url}")
        bs_extractor = BeautifulSoupExtractor(website_url)
        result = bs_extractor.extract_logo(force_refresh=request.force_refresh)
        
        # Check if we found a logo or determined it's text-based
        if result == TEXT_BASED_LOGO:
            # If text-based logo but Google is enabled, try that
            if request.use_google:
                from ..extractors.google import GoogleExtractor
                google_extractor = GoogleExtractor(website_url, request.chromedriver_path)
                google_result = google_extractor.extract_logo(force_refresh=request.force_refresh)
                
                if google_result:
                    # Process the logo and check quality
                    from ..utils.image import process_logo_image
                    processed_path, is_valid, issues = process_logo_image(google_result)
                    
                    # Use the processed path if available
                    google_logo = processed_path if processed_path else google_result
                    
                    quality_info = {
                        "is_valid": is_valid,
                        "issues": issues
                    }
                    
                    # Get the file content as base64
                    logo_data = None
                    if os.path.exists(google_logo):
                        with open(google_logo, "rb") as logo_file:
                            logo_content = logo_file.read()
                            logo_data = base64.b64encode(logo_content).decode("utf-8")
                    
                    # Get the cached logo URL
                    cache_data = cache_utils.get_cached_result(website_url)
                    logo_url = cache_data.get("logo_url") if cache_data else None
                    
                    # Set the message
                    message = "Website uses text-based logo, but found logo image via Google"
                    if not is_valid:
                        message += f" (with quality issues: {', '.join(issues)})"
                    
                    return LogoExtractionResponse(
                        url=website_url,
                        success=True,
                        logo_url=logo_url,
                        logo_path=google_logo,
                        logo_data=logo_data,
                        message=message,
                        execution_time=time.time() - start_time,
                        quality=quality_info,
                        source="google",
                        similarity_score=None
                    )
                
            # Return text-based logo result if no Google results
            return LogoExtractionResponse(
                url=website_url,
                success=True,
                text_based_logo=True,
                message="Website uses a text-based logo with no image file",
                execution_time=time.time() - start_time
            )
            
        elif result:
            # We found a logo with BeautifulSoup
            # Process the logo and check quality
            from ..utils.image import process_logo_image
            processed_path, is_valid, issues = process_logo_image(result)
            
            # Use the processed path if available
            website_logo = processed_path if processed_path else result
            
            website_quality_info = {
                "is_valid": is_valid,
                "issues": issues
            }
        
        # If BeautifulSoup failed and Claude fallback is enabled, try Claude
        if not website_logo and request.use_claude_fallback:
            print("BeautifulSoup extraction failed, trying Claude...")
            
            claude_extractor = ClaudeExtractor(website_url)
            result = claude_extractor.extract_logo(force_refresh=request.force_refresh)
            
            # Check if we found a logo or determined it's text-based with Claude
            if result == TEXT_BASED_LOGO:
                # If text-based logo but Google is enabled, try that
                if request.use_google:
                    from ..extractors.google import GoogleExtractor
                    google_extractor = GoogleExtractor(website_url, request.chromedriver_path)
                    google_result = google_extractor.extract_logo(force_refresh=request.force_refresh)
                    
                    if google_result:
                        # Process the logo and check quality
                        from ..utils.image import process_logo_image
                        processed_path, is_valid, issues = process_logo_image(google_result)
                        
                        # Use the processed path if available
                        google_logo = processed_path if processed_path else google_result
                        
                        quality_info = {
                            "is_valid": is_valid,
                            "issues": issues
                        }
                        
                        # Get the file content as base64
                        logo_data = None
                        if os.path.exists(google_logo):
                            with open(google_logo, "rb") as logo_file:
                                logo_content = logo_file.read()
                                logo_data = base64.b64encode(logo_content).decode("utf-8")
                        
                        # Get the cached logo URL
                        cache_data = cache_utils.get_cached_result(website_url)
                        logo_url = cache_data.get("logo_url") if cache_data else None
                        
                        # Set the message
                        message = "Website uses text-based logo (determined by Claude), but found logo image via Google"
                        if not is_valid:
                            message += f" (with quality issues: {', '.join(issues)})"
                        
                        return LogoExtractionResponse(
                            url=website_url,
                            success=True,
                            logo_url=logo_url,
                            logo_path=google_logo,
                            logo_data=logo_data,
                            message=message,
                            execution_time=time.time() - start_time,
                            quality=quality_info,
                            source="google",
                            similarity_score=None
                        )
                
                # Return text-based logo result if no Google results
                return LogoExtractionResponse(
                    url=website_url,
                    success=True,
                    text_based_logo=True,
                    message="Website uses a text-based logo with no image file (determined by Claude)",
                    execution_time=time.time() - start_time
                )
                
            elif result:
                # We found a logo with Claude
                # Process the logo and check quality
                from ..utils.image import process_logo_image
                processed_path, is_valid, issues = process_logo_image(result)
                
                # Use the processed path if available
                website_logo = processed_path if processed_path else result
                
                website_quality_info = {
                    "is_valid": is_valid,
                    "issues": issues
                }
        
        # If Google extraction is enabled, try that too
        if request.use_google:
            from ..extractors.google import GoogleExtractor
            google_extractor = GoogleExtractor(website_url, request.chromedriver_path)
            google_result = google_extractor.extract_logo(force_refresh=request.force_refresh)
            
            if google_result:
                # Process the logo and check quality
                from ..utils.image import process_logo_image
                processed_path, is_valid, issues = process_logo_image(google_result)
                
                # Use the processed path if available
                google_logo = processed_path if processed_path else google_result
                
                google_quality_info = {
                    "is_valid": is_valid,
                    "issues": issues
                }
        
        # Compare and select the best logo
        if website_logo or google_logo:
            from ..utils.qa import select_best_logo
            best_logo_path, source, similarity = select_best_logo(website_logo, google_logo)
            
            # Use the quality info from the selected source
            if source == 'website':
                quality_info = website_quality_info
            elif source == 'google':
                quality_info = google_quality_info
            
            # Get the file content as base64
            logo_data = None
            if best_logo_path and os.path.exists(best_logo_path):
                with open(best_logo_path, "rb") as logo_file:
                    logo_content = logo_file.read()
                    logo_data = base64.b64encode(logo_content).decode("utf-8")
            
            # Get the cached logo URL
            cache_data = cache_utils.get_cached_result(website_url)
            logo_url = cache_data.get("logo_url") if cache_data else None
            
            # Prepare the message
            if source == 'website':
                message = "Successfully extracted logo from website"
            elif source == 'google':
                message = "Successfully extracted logo from Google Images"
            else:
                message = "Successfully extracted logo"
                
            if quality_info and not quality_info.get("is_valid", False):
                message += f" (with quality issues: {', '.join(quality_info.get('issues', []))})"
            
            if website_logo and google_logo and similarity < 0.6:
                message += f". WARNING: Logos from website and Google differ (similarity: {similarity:.2f})"
            
            return LogoExtractionResponse(
                url=website_url,
                success=True,
                logo_url=logo_url,
                logo_path=best_logo_path,
                logo_data=logo_data,
                message=message,
                execution_time=time.time() - start_time,
                quality=quality_info,
                source=source,
                similarity_score=similarity
            )
                
        # If all extraction methods failed
        return LogoExtractionResponse(
            url=website_url,
            success=False,
            message="Failed to extract logo with any method",
            execution_time=time.time() - start_time
        )
        
    except Exception as e:
        # Return error response
        return LogoExtractionResponse(
            url=request.url,
            success=False,
            message=f"Error: {str(e)}",
            execution_time=time.time() - start_time
        )

@app.get("/cache", response_model=dict)
async def get_cache_info(url: str = Query(..., description="URL to get cache info for")):
    """
    Get cached information for a website
    
    This endpoint returns cached logo extraction information for a website.
    """
    try:
        website_url = url_utils.normalize_url(url)
        cache_data = cache_utils.get_cached_result(website_url)
        
        if cache_data:
            return {
                "url": website_url,
                "has_cache": True,
                "cache_data": cache_data
            }
        else:
            return {
                "url": website_url,
                "has_cache": False,
                "message": "No cache found for this URL"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error accessing cache: {str(e)}")

@app.delete("/cache")
async def clear_cache(url: Optional[str] = Query(None, description="URL to clear cache for (optional, clears all if not provided)")):
    """
    Clear cache for a website or all websites
    
    This endpoint clears the logo extraction cache for a website or all websites.
    """
    try:
        if url:
            website_url = url_utils.normalize_url(url)
            count = cache_utils.clear_cache(website_url)
            
            return {
                "success": True,
                "message": f"Cleared cache for {website_url}",
                "files_removed": count
            }
        else:
            count = cache_utils.clear_cache()
            
            return {
                "success": True,
                "message": "Cleared all cache",
                "files_removed": count
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")

@app.get("/logos", response_model=List[dict])
async def list_logos():
    """
    List all downloaded logos
    
    This endpoint returns a list of all downloaded logos.
    """
    try:
        logos = []
        
        # Get all logo files in the output directory
        for file_path in Path(OUTPUT_DIR).glob("*_logo.*"):
            # Get file info
            file_name = file_path.name
            file_size = file_path.stat().st_size
            file_modified = file_path.stat().st_mtime
            
            # Extract domain from filename (domain_logo.ext)
            domain = file_name.split("_logo.")[0]
            
            logos.append({
                "domain": domain,
                "file_name": file_name,
                "file_path": str(file_path),
                "file_size": file_size,
                "file_modified": file_modified
            })
        
        return logos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing logos: {str(e)}")

@app.delete("/logos/{domain}")
async def delete_logo(domain: str):
    """
    Delete a downloaded logo
    
    This endpoint deletes a downloaded logo for a domain.
    """
    try:
        # Look for logo files matching the domain
        logo_pattern = f"{domain}_logo.*"
        found = False
        
        for file_path in Path(OUTPUT_DIR).glob(logo_pattern):
            file_path.unlink()
            found = True
        
        if found:
            return {
                "success": True,
                "message": f"Deleted logo for {domain}"
            }
        else:
            raise HTTPException(status_code=404, detail=f"No logo found for domain: {domain}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting logo: {str(e)}") 