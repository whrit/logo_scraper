import os
import imghdr
import numpy as np
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import requests

def is_corrupted_image(image_path):
    """
    Check if an image file is corrupted
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        bool: True if image is corrupted, False otherwise
    """
    # Check if file exists
    if not os.path.exists(image_path):
        print(f"File does not exist: {image_path}")
        return True
        
    # Check if file is empty
    if os.path.getsize(image_path) == 0:
        print(f"File is empty: {image_path}")
        return True
    
    # Special handling for SVG files
    if image_path.lower().endswith('.svg'):
        try:
            # Check if file contains SVG content
            with open(image_path, 'rb') as f:
                content = f.read(1024)  # Read first 1KB
                if b'<svg' in content or b'<?xml' in content:
                    return False  # SVG content found, not corrupted
                else:
                    print(f"SVG file doesn't contain SVG content: {image_path}")
                    return True
        except Exception as e:
            print(f"Error checking SVG file: {e}")
            return True
    
    # For non-SVG files, check using imghdr
    image_type = imghdr.what(image_path)
    if image_type is None:
        print(f"File is not a valid image: {image_path}")
        return True
    
    # Try to open the image with PIL
    try:
        with Image.open(image_path) as img:
            # Force image processing to check for corruption
            img.verify()
            
        # Need to reopen after verify
        with Image.open(image_path) as img:
            img.load()
        
        return False
    except (UnidentifiedImageError, OSError, IOError) as e:
        print(f"Failed to process image: {e}")
        return True

def is_all_white_or_transparent(image_path, white_threshold=0.98):
    """
    Check if an image is entirely or almost entirely white/transparent
    
    Args:
        image_path (str): Path to the image file
        white_threshold (float): Threshold for considering an image all white (0.0-1.0)
        
    Returns:
        bool: True if image is all white or transparent, False otherwise
    """
    try:
        with Image.open(image_path) as img:
            # If image has alpha channel, convert to RGBA
            if img.mode in ('LA', 'RGBA'):
                # Check if it's mostly transparent
                if img.mode == 'RGBA':
                    rgba = np.array(img)
                    # If average alpha < 0.1 (mostly transparent), consider it invalid
                    if np.mean(rgba[:, :, 3]) / 255 < 0.1:
                        print(f"Image is mostly transparent: {image_path}")
                        return True
                
                # Convert image to RGB for white check (removing alpha)
                img = img.convert('RGB')
            
            # Convert to grayscale and analyze histogram
            gray_img = img.convert('L')
            histogram = gray_img.histogram()
            
            # Find the percentage of white-ish pixels (values 240-255)
            white_pixel_count = sum(histogram[240:])
            total_pixels = gray_img.width * gray_img.height
            
            white_ratio = white_pixel_count / total_pixels
            
            if white_ratio > white_threshold:
                print(f"Image is {white_ratio:.1%} white pixels: {image_path}")
                return True
            
            return False
    except Exception as e:
        print(f"Error analyzing image: {e}")
        # If we can't analyze, consider it potentially problematic
        return True

def is_too_small(image_path, min_width=32, min_height=32, min_total_pixels=1024):
    """
    Check if an image is too small to be a useful logo
    
    Args:
        image_path (str): Path to the image file
        min_width (int): Minimum acceptable width in pixels
        min_height (int): Minimum acceptable height in pixels
        min_total_pixels (int): Minimum acceptable total pixel count
        
    Returns:
        bool: True if image is too small, False otherwise
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            total_pixels = width * height
            
            if width < min_width or height < min_height or total_pixels < min_total_pixels:
                print(f"Image is too small: {width}x{height} pixels ({total_pixels} total pixels)")
                return True
            
            return False
    except Exception as e:
        print(f"Error checking image size: {e}")
        # If we can't analyze, consider it potentially problematic
        return True

def check_logo_quality(image_path):
    """
    Perform a complete quality check on a logo image
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        tuple: (is_valid, issues) where is_valid is a boolean and issues is a list of strings
    """
    issues = []
    
    # Special handling for SVG files (they're vector, so size and other checks don't apply)
    if image_path.lower().endswith('.svg'):
        # For SVG, we only check if it's corrupted
        if is_corrupted_image(image_path):
            issues.append("SVG file is corrupted or invalid")
        return len(issues) == 0, issues
    
    # For raster images, do full checks
    # Check if image is corrupted
    if is_corrupted_image(image_path):
        issues.append("Image is corrupted or not a valid image file")
    
    # Only continue checks if the image isn't corrupted
    if not issues:
        # Check if image is all white or transparent
        if is_all_white_or_transparent(image_path):
            issues.append("Image is entirely or almost entirely white/transparent")
        
        # Check if image is too small
        if is_too_small(image_path):
            issues.append("Image is too small to be a useful logo")
    
    # Return results
    is_valid = len(issues) == 0
    return is_valid, issues

def validate_and_fix_logo(image_path):
    """
    Validate a logo and attempt to fix common issues
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        tuple: (fixed_path, is_valid, issues) where fixed_path is the path to the fixed image or None,
               is_valid is a boolean, and issues is a list of strings
    """
    # First check if there are any issues
    is_valid, issues = check_logo_quality(image_path)
    
    # If the image is valid, return it as is
    if is_valid:
        return image_path, True, []
    
    # Try to fix the issues
    fixed_path = None
    
    try:
        # Handle corrupted images
        if "corrupted" in issues[0]:
            # Cannot fix corrupted images
            return None, False, issues
        
        # Handle white/transparent images - nothing to do here as they're valid but not useful
        if any("white" in issue or "transparent" in issue for issue in issues):
            # Cannot fix all-white or transparent images
            return None, False, issues
        
        # Handle too small images - nothing we can do to add actual content
        if any("too small" in issue for issue in issues):
            # Cannot fix too small images
            return None, False, issues
        
        # If we couldn't fix anything, return the original path
        if fixed_path is None:
            return image_path, False, issues
            
        return fixed_path, True, []
        
    except Exception as e:
        print(f"Error attempting to fix image: {e}")
        # If we can't fix it, add this as an issue
        issues.append(f"Failed to fix image: {str(e)}")
        return None, False, issues 

def is_better_format(format1, format2):
    """
    Compare two image formats and determine which one is better
    
    Args:
        format1 (str): First image format (e.g. 'svg', 'png', 'jpg')
        format2 (str): Second image format (e.g. 'svg', 'png', 'jpg')
        
    Returns:
        bool: True if format1 is better than format2, False otherwise
    """
    # Define format priorities (higher is better)
    format_priority = {
        'svg': 3,
        'png': 2,
        'jpg': 1,
        'jpeg': 1,
        'gif': 0,
        'webp': 1.5  # Between JPG and PNG
    }
    
    # Get format priorities, defaulting to 0 for unknown formats
    priority1 = format_priority.get(format1.lower(), 0)
    priority2 = format_priority.get(format2.lower(), 0)
    
    # Return True if format1 has higher priority
    return priority1 > priority2

def should_prefer_png(png_url, other_url, width_threshold=200, height_threshold=200):
    """
    Determine if we should prefer a PNG over another format when dimensions are similar
    
    Args:
        png_url (dict): Image data containing URL and dimensions for PNG
        other_url (dict): Image data containing URL and dimensions for another format
        width_threshold (int): Maximum width difference to consider images similar
        height_threshold (int): Maximum height difference to consider images similar
        
    Returns:
        bool: True if PNG should be preferred, False otherwise
    """
    # If either URL doesn't have dimensions, we can't compare them
    if not (png_url.get('width') and png_url.get('height') and 
            other_url.get('width') and other_url.get('height')):
        return False
    
    # Get dimensions
    png_width = png_url['width']
    png_height = png_url['height']
    other_width = other_url['width']
    other_height = other_url['height']
    
    # Check if dimensions are similar (within thresholds)
    width_similar = abs(png_width - other_width) <= width_threshold
    height_similar = abs(png_height - other_height) <= height_threshold
    
    # If dimensions are similar, prefer PNG over JPG or WEBP
    return width_similar and height_similar

def get_image_dimensions(image_path):
    """
    Get dimensions of an image
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        tuple: (width, height) or (0, 0) if the image cannot be opened
    """
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        print(f"Error getting image dimensions: {e}")
        return (0, 0)

def get_image_pixels(image_path):
    """
    Get total number of pixels in an image
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        int: Total number of pixels, or 0 if the image cannot be opened
    """
    width, height = get_image_dimensions(image_path)
    return width * height

def is_significantly_larger(img1_path, img2_path, threshold_factor=1.5):
    """
    Check if first image has significantly more pixels than the second
    
    Args:
        img1_path (str): Path to the first image
        img2_path (str): Path to the second image
        threshold_factor (float): How much larger img1 needs to be to be considered "significantly" larger
        
    Returns:
        bool: True if img1 is significantly larger than img2, False otherwise
    """
    pixels1 = get_image_pixels(img1_path)
    pixels2 = get_image_pixels(img2_path)
    
    # Avoid division by zero
    if pixels2 == 0:
        return pixels1 > 0
    
    return (pixels1 / pixels2) > threshold_factor

def compare_logos(img1_path, img2_path, similarity_threshold=0.6):
    """
    Compare two logos to see if they are similar
    
    Args:
        img1_path (str): Path to the first image
        img2_path (str): Path to the second image
        similarity_threshold (float): Threshold for considering images similar (0.0-1.0)
        
    Returns:
        float: Similarity score (0.0-1.0) or None if images cannot be compared
    """
    try:
        # Handle SVG files (can't compare directly)
        if img1_path.lower().endswith('.svg') or img2_path.lower().endswith('.svg'):
            print("SVG comparison is not supported, assuming logos are similar")
            return 1.0  # Assume maximum similarity for SVGs
            
        # Open images
        img1 = Image.open(img1_path)
        img2 = Image.open(img2_path)
        
        # Convert to same mode for comparison
        if img1.mode != img2.mode:
            img1 = img1.convert('RGBA')
            img2 = img2.convert('RGBA')
        
        # Resize images to same dimensions for comparison
        # Choose the smaller of the two to avoid upscaling
        width1, height1 = img1.size
        width2, height2 = img2.size
        
        # Use minimum dimensions to avoid upscaling artifacts
        target_width = min(width1, width2, 300)  # Cap at 300px for performance
        target_height = min(height1, height2, 300)
        
        # Skip tiny images
        if target_width < 10 or target_height < 10:
            print("Images too small for meaningful comparison")
            return None
            
        img1_resized = img1.resize((target_width, target_height), Image.LANCZOS)
        img2_resized = img2.resize((target_width, target_height), Image.LANCZOS)
        
        # Convert to arrays for comparison
        arr1 = np.array(img1_resized)
        arr2 = np.array(img2_resized)
        
        # If images have alpha channel, calculate similarity for visible parts
        if arr1.shape[-1] == 4:  # RGBA
            # Calculate mask of non-transparent pixels in both images
            mask1 = arr1[..., 3] > 10  # Alpha > 10
            mask2 = arr2[..., 3] > 10
            
            # Only compare pixels that are visible in both images
            common_mask = mask1 & mask2
            
            # If no common visible pixels, consider them different
            if not np.any(common_mask):
                return 0.0
                
            # Calculate mean absolute difference in RGB channels for visible pixels
            diff = np.abs(arr1[common_mask][:, :3] - arr2[common_mask][:, :3])
            mae = np.mean(diff) / 255.0  # Normalize to 0-1
            
            # Convert mean absolute error to similarity (1.0 = identical, 0.0 = completely different)
            similarity = 1.0 - min(mae, 1.0)
        else:
            # For RGB images, calculate difference across all pixels
            diff = np.abs(arr1 - arr2)
            mae = np.mean(diff) / 255.0
            similarity = 1.0 - min(mae, 1.0)
        
        return similarity
        
    except Exception as e:
        print(f"Error comparing logos: {e}")
        import traceback
        traceback.print_exc()
        return None

def select_best_logo(logo_candidates):
    """
    Compare multiple logo candidates and select the best one
    
    Args:
        logo_candidates (list): List of dictionaries with 'path' and 'source' keys
        
    Returns:
        str: Path to the best logo
    """
    if not logo_candidates:
        return None
        
    # If only one logo, return it
    if len(logo_candidates) == 1:
        return logo_candidates[0]['path']
    
    # List to store logo scores
    scored_logos = []
    
    for logo in logo_candidates:
        path = logo['path']
        source = logo['source']
        
        # Initialize score with quality metrics
        score = 0
        
        try:
            # Get the file extension
            _, ext = os.path.splitext(path)
            ext = ext.lower().lstrip('.')
            
            # Format score
            if ext == 'svg':
                score += 30  # SVG is vector, highest quality
                format_name = "SVG (vector)"
            elif ext == 'png':
                score += 20  # PNG usually has transparency
                format_name = "PNG"
            elif ext == 'jpg' or ext == 'jpeg':
                score += 10  # JPG/JPEG is acceptable
                format_name = "JPEG"
            elif ext == 'webp':
                score += 15  # WEBP is good quality with compression
                format_name = "WEBP"
            else:
                score += 5   # Other formats
                format_name = ext.upper()
                
            # Additional checks for raster images
            if ext != 'svg':
                # Open the image to get details
                with Image.open(path) as img:
                    width, height = img.size
                    
                    # Resolution score (higher is better)
                    pixels = width * height
                    if pixels > 40000:  # Larger than 200x200
                        score += min(pixels / 10000, 30)  # Cap at 30 points
                    
                    # Transparency score (PNG with alpha channel is better)
                    if ext == 'png' and img.mode == 'RGBA':
                        # Check if transparency is actually used
                        has_transparency = False
                        data = np.array(img)
                        if np.any(data[:, :, 3] < 250):
                            has_transparency = True
                            
                        if has_transparency:
                            score += 15
                            print(f"  {source} logo has useful transparency")
                    
                    # Aspect ratio score (closer to square is often better for logos)
                    aspect_ratio = max(width, height) / max(1, min(width, height))
                    if aspect_ratio < 3:  # Not extremely elongated
                        score += max(0, 10 - (aspect_ratio - 1) * 5)
                    else:
                        # Penalty for extremely elongated logos
                        score -= min(10, aspect_ratio - 3)
                    
                    # Quality description for logging
                    quality_desc = f"{width}x{height} ({pixels} pixels)"
            else:
                # For SVG, we can't easily analyze the content, but it's vector
                quality_desc = "Vector format (infinite resolution)"
            
            # Preference for website's own logo vs Google search results
            if source == 'website':
                score += 5  # Small bonus for the website's own logo
            
            # Calculate logo quality score (higher is better)
            scored_logos.append({
                'path': path,
                'source': source,
                'score': score,
                'format': format_name,
                'quality': quality_desc
            })
            
            print(f"  {source} logo ({format_name}, {quality_desc}) - Score: {score:.1f}")
            
        except Exception as e:
            print(f"Error analyzing {source} logo: {e}")
            # Add with minimal score
            scored_logos.append({
                'path': path,
                'source': source,
                'score': 0,
                'format': 'unknown',
                'quality': 'error analyzing'
            })
    
    # Sort by score (highest first)
    scored_logos.sort(key=lambda x: x['score'], reverse=True)
    
    # Get the best logo
    best_logo = scored_logos[0]
    
    print(f"\nBest logo: {best_logo['source']} ({best_logo['format']}, {best_logo['quality']}) - Score: {best_logo['score']:.1f}")
    
    return best_logo['path'] 