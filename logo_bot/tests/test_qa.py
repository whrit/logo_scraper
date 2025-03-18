import os
import unittest
import tempfile
from PIL import Image
import numpy as np
import io
import base64

from logo_bot.utils.qa import (
    is_corrupted_image,
    is_all_white_or_transparent,
    is_too_small,
    check_logo_quality,
    validate_and_fix_logo
)

class TestLogoQA(unittest.TestCase):
    """Test cases for logo quality assurance functions"""
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        
    def tearDown(self):
        """Clean up after tests"""
        # Remove temporary directory
        self.temp_dir.cleanup()
        
    def _create_test_image(self, width, height, color=(255, 255, 255), mode='RGB', format='PNG'):
        """Helper method to create a test image"""
        # Create image path
        img_path = os.path.join(self.temp_dir.name, f"test_{width}x{height}_{color[0]}_{mode}.{format.lower()}")
        
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
    
    def _create_corrupt_image(self):
        """Helper method to create a corrupt image file"""
        corrupt_path = os.path.join(self.temp_dir.name, "corrupt.png")
        with open(corrupt_path, 'wb') as f:
            f.write(b"This is not a valid image file")
        return corrupt_path
    
    def _create_empty_file(self):
        """Helper method to create an empty file"""
        empty_path = os.path.join(self.temp_dir.name, "empty.png")
        with open(empty_path, 'wb') as f:
            pass  # Create empty file
        return empty_path
    
    def _create_transparent_image(self, width, height, alpha=0):
        """Helper method to create a transparent image"""
        img_path = os.path.join(self.temp_dir.name, f"transparent_{width}x{height}_{alpha}.png")
        img_data = np.zeros((height, width, 4), dtype=np.uint8)
        img_data[:, :, 3] = alpha  # Set alpha channel
        img = Image.fromarray(img_data, 'RGBA')
        img.save(img_path, 'PNG')
        return img_path
    
    def test_is_corrupted_image(self):
        """Test is_corrupted_image function"""
        # Test valid image
        valid_path = self._create_test_image(100, 100)
        self.assertFalse(is_corrupted_image(valid_path))
        
        # Test corrupt image
        corrupt_path = self._create_corrupt_image()
        self.assertTrue(is_corrupted_image(corrupt_path))
        
        # Test empty file
        empty_path = self._create_empty_file()
        self.assertTrue(is_corrupted_image(empty_path))
        
        # Test non-existent file
        self.assertTrue(is_corrupted_image("non_existent_file.png"))
    
    def test_is_all_white_or_transparent(self):
        """Test is_all_white_or_transparent function"""
        # Test white image
        white_path = self._create_test_image(100, 100, color=(255, 255, 255))
        self.assertTrue(is_all_white_or_transparent(white_path))
        
        # Test colored image
        colored_path = self._create_test_image(100, 100, color=(255, 0, 0))
        self.assertFalse(is_all_white_or_transparent(colored_path))
        
        # Test transparent image
        transparent_path = self._create_transparent_image(100, 100, alpha=0)
        self.assertTrue(is_all_white_or_transparent(transparent_path))
        
        # Test semi-transparent image
        semi_transparent_path = self._create_transparent_image(100, 100, alpha=128)
        self.assertFalse(is_all_white_or_transparent(semi_transparent_path))
    
    def test_is_too_small(self):
        """Test is_too_small function"""
        # Test small image
        small_path = self._create_test_image(16, 16)
        self.assertTrue(is_too_small(small_path))
        
        # Test adequate size image
        adequate_path = self._create_test_image(64, 64)
        self.assertFalse(is_too_small(adequate_path))
        
        # Test image with one dimension too small
        narrow_path = self._create_test_image(16, 100)
        self.assertTrue(is_too_small(narrow_path))
    
    def test_check_logo_quality(self):
        """Test check_logo_quality function"""
        # Test good image
        good_path = self._create_test_image(100, 100, color=(0, 0, 255))
        is_valid, issues = check_logo_quality(good_path)
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)
        
        # Test white image
        white_path = self._create_test_image(100, 100, color=(255, 255, 255))
        is_valid, issues = check_logo_quality(white_path)
        self.assertFalse(is_valid)
        self.assertEqual(len(issues), 1)
        self.assertIn("white", issues[0].lower())
        
        # Test corrupt image
        corrupt_path = self._create_corrupt_image()
        is_valid, issues = check_logo_quality(corrupt_path)
        self.assertFalse(is_valid)
        self.assertEqual(len(issues), 1)
        self.assertIn("corrupt", issues[0].lower())
        
        # Test small image
        small_path = self._create_test_image(16, 16, color=(0, 0, 255))
        is_valid, issues = check_logo_quality(small_path)
        self.assertFalse(is_valid)
        self.assertEqual(len(issues), 1)
        self.assertIn("small", issues[0].lower())
    
    def test_validate_and_fix_logo(self):
        """Test validate_and_fix_logo function"""
        # Test good image
        good_path = self._create_test_image(100, 100, color=(0, 0, 255))
        fixed_path, is_valid, issues = validate_and_fix_logo(good_path)
        self.assertEqual(fixed_path, good_path)
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)
        
        # Test white image (cannot be fixed)
        white_path = self._create_test_image(100, 100, color=(255, 255, 255))
        fixed_path, is_valid, issues = validate_and_fix_logo(white_path)
        self.assertIsNone(fixed_path)
        self.assertFalse(is_valid)
        self.assertEqual(len(issues), 1)
        
        # Test corrupt image (cannot be fixed)
        corrupt_path = self._create_corrupt_image()
        fixed_path, is_valid, issues = validate_and_fix_logo(corrupt_path)
        self.assertIsNone(fixed_path)
        self.assertFalse(is_valid)
        self.assertEqual(len(issues), 1)

if __name__ == '__main__':
    unittest.main() 