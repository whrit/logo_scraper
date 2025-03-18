import os
import unittest
import tempfile
from PIL import Image
import numpy as np

from logo_bot.utils.qa import (
    is_better_format,
    compare_logos,
    select_best_logo,
    get_image_dimensions,
    is_significantly_larger
)

class TestLogoComparison(unittest.TestCase):
    """Test cases for logo comparison functions"""
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        
    def tearDown(self):
        """Clean up after tests"""
        # Remove temporary directory
        self.temp_dir.cleanup()
        
    def _create_test_image(self, width, height, color=(255, 0, 0), mode='RGB', format='PNG'):
        """Helper method to create a test image"""
        # Create image path
        filename = f"test_{width}x{height}_{color[0]}_{mode}.{format.lower()}"
        img_path = os.path.join(self.temp_dir.name, filename)
        
        # Create image with specified color
        if mode == 'RGBA':
            # For RGBA mode, we need a 4-tuple
            if len(color) == 3:
                color = color + (255,)  # Add alpha=255 (fully opaque)
            img_data = np.full((height, width, 4), color, dtype=np.uint8)
        else:
            img_data = np.full((height, width, 3), color, dtype=np.uint8)
        
        img = Image.fromarray(img_data, mode=mode)
        img.save(img_path, format=format)
        
        return img_path
    
    def _create_similar_logo_pair(self, width1, height1, width2, height2, 
                                  color1=(255, 0, 0), color2=(255, 0, 0),
                                  format1='PNG', format2='PNG'):
        """Create a pair of similar logos with different dimensions/formats"""
        path1 = self._create_test_image(width1, height1, color1, format=format1)
        path2 = self._create_test_image(width2, height2, color2, format=format2)
        return path1, path2
    
    def _create_different_logo_pair(self):
        """Create a pair of visually different logos"""
        path1 = self._create_test_image(100, 100, color=(255, 0, 0))
        path2 = self._create_test_image(100, 100, color=(0, 0, 255))
        return path1, path2
    
    def test_is_better_format(self):
        """Test is_better_format function"""
        # Test SVG > PNG > JPG
        self.assertTrue(is_better_format('svg', 'png'))
        self.assertTrue(is_better_format('png', 'jpg'))
        self.assertTrue(is_better_format('svg', 'jpg'))
        
        # Test case insensitivity
        self.assertTrue(is_better_format('PNG', 'jpg'))
        self.assertTrue(is_better_format('SVG', 'PNG'))
        
        # Test equal formats
        self.assertFalse(is_better_format('png', 'png'))
        self.assertFalse(is_better_format('jpg', 'jpg'))
        
        # Test inferior formats
        self.assertFalse(is_better_format('jpg', 'png'))
        self.assertFalse(is_better_format('png', 'svg'))
    
    def test_get_image_dimensions(self):
        """Test get_image_dimensions function"""
        path = self._create_test_image(100, 200)
        width, height = get_image_dimensions(path)
        self.assertEqual(width, 100)
        self.assertEqual(height, 200)
        
        # Test non-existent file
        width, height = get_image_dimensions("non_existent_file.png")
        self.assertEqual(width, 0)
        self.assertEqual(height, 0)
    
    def test_is_significantly_larger(self):
        """Test is_significantly_larger function"""
        small = self._create_test_image(100, 100)
        medium = self._create_test_image(150, 150)
        large = self._create_test_image(200, 200)
        
        # Medium is not significantly larger than small (2.25x)
        self.assertTrue(is_significantly_larger(medium, small))
        
        # Large is significantly larger than small (4x)
        self.assertTrue(is_significantly_larger(large, small))
        
        # Small is not significantly larger than large
        self.assertFalse(is_significantly_larger(small, large))
        
        # Non-existent file is not larger
        self.assertFalse(is_significantly_larger("non_existent_file.png", small))
        
        # But anything is larger than non-existent file
        self.assertTrue(is_significantly_larger(small, "non_existent_file.png"))
    
    def test_compare_logos_similar(self):
        """Test compare_logos function with similar logos"""
        # Create similar logos with different dimensions
        path1, path2 = self._create_similar_logo_pair(100, 100, 200, 200)
        
        # Compare them
        similarity = compare_logos(path1, path2)
        
        # Should be very similar
        self.assertGreater(similarity, 0.9)
    
    def test_compare_logos_different(self):
        """Test compare_logos function with different logos"""
        # Create different logos (red vs blue)
        path1, path2 = self._create_different_logo_pair()
        
        # Compare them
        similarity = compare_logos(path1, path2)
        
        # Should be very different
        self.assertLess(similarity, 0.5)
    
    def test_select_best_logo_svg_priority(self):
        """Test select_best_logo function with SVG priority"""
        # Create same logo in different formats
        png_path = self._create_test_image(100, 100, format='PNG')
        # Can't actually create an SVG, so let's rename a PNG
        svg_path = os.path.join(self.temp_dir.name, "logo.svg")
        with open(png_path, 'rb') as src:
            with open(svg_path, 'wb') as dst:
                dst.write(src.read())
        
        # SVG from website should win over PNG from Google
        best_path, source, similarity = select_best_logo(svg_path, png_path)
        self.assertEqual(best_path, svg_path)
        self.assertEqual(source, 'website')
        
        # SVG from Google should win over PNG from website
        best_path, source, similarity = select_best_logo(png_path, svg_path)
        self.assertEqual(best_path, svg_path)
        self.assertEqual(source, 'google')
    
    def test_select_best_logo_size_priority(self):
        """Test select_best_logo function with size priority"""
        # Create same logo in different sizes
        small_png = self._create_test_image(100, 100, format='PNG')
        large_jpg = self._create_test_image(300, 300, format='JPEG')
        
        # Large JPG should win over small PNG due to significant size difference
        best_path, source, similarity = select_best_logo(large_jpg, small_png)
        self.assertEqual(best_path, large_jpg)
        self.assertEqual(source, 'website')
        
        best_path, source, similarity = select_best_logo(small_png, large_jpg)
        self.assertEqual(best_path, large_jpg)
        self.assertEqual(source, 'google')
    
    def test_select_best_logo_format_priority(self):
        """Test select_best_logo function with format priority when size is similar"""
        # Create same logo in different formats but similar size
        jpg_path = self._create_test_image(100, 100, format='JPEG')
        png_path = self._create_test_image(110, 110, format='PNG')
        
        # PNG should win over JPG when sizes are similar
        best_path, source, similarity = select_best_logo(jpg_path, png_path)
        self.assertEqual(best_path, png_path)
        self.assertEqual(source, 'google')
        
        best_path, source, similarity = select_best_logo(png_path, jpg_path)
        self.assertEqual(best_path, png_path)
        self.assertEqual(source, 'website')
    
    def test_select_best_logo_different_logos(self):
        """Test select_best_logo function with different logos"""
        # Create different logos
        logo1, logo2 = self._create_different_logo_pair()
        
        # Should prefer website logo when they are different
        best_path, source, similarity = select_best_logo(logo1, logo2)
        self.assertEqual(best_path, logo1)
        self.assertEqual(source, 'website')
        self.assertLess(similarity, 0.6)  # Similarity should be low
    
    def test_select_best_logo_one_missing(self):
        """Test select_best_logo function when one logo is missing"""
        # Create a test logo
        logo_path = self._create_test_image(100, 100)
        
        # Website logo only
        best_path, source, similarity = select_best_logo(logo_path, None)
        self.assertEqual(best_path, logo_path)
        self.assertEqual(source, 'website')
        
        # Google logo only
        best_path, source, similarity = select_best_logo(None, logo_path)
        self.assertEqual(best_path, logo_path)
        self.assertEqual(source, 'google')

if __name__ == '__main__':
    unittest.main() 