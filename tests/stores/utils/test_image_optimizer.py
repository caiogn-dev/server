import os
import tempfile
from pathlib import Path
from PIL import Image
from django.test import TestCase
from apps.stores.utils.image_optimizer import ImageOptimizer


class ImageOptimizerTestCase(TestCase):
    def setUp(self):
        self.optimizer = ImageOptimizer()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Clean up temp files
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_optimize_converts_to_webp(self):
        """Test that optimize() converts image to WebP format."""
        # Create a test PNG image (100x100)
        test_image_path = Path(self.temp_dir) / "test.png"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(test_image_path, 'PNG')

        # Optimize
        result_path = self.optimizer.optimize(str(test_image_path))

        # Assert
        self.assertTrue(Path(result_path).exists())
        self.assertTrue(result_path.endswith('.webp'))

        # Verify it's actually WebP by opening it
        optimized = Image.open(result_path)
        self.assertEqual(optimized.format, 'WEBP')

    def test_optimize_respects_max_dimensions(self):
        """Test that optimize() respects max_width and max_height."""
        # Create a large test image (1000x1000)
        test_image_path = Path(self.temp_dir) / "large.png"
        img = Image.new('RGB', (1000, 1000), color='blue')
        img.save(test_image_path, 'PNG')

        # Optimize with max 600x600
        result_path = self.optimizer.optimize(str(test_image_path), max_width=600, max_height=600)

        # Verify dimensions
        optimized = Image.open(result_path)
        self.assertLessEqual(optimized.width, 600)
        self.assertLessEqual(optimized.height, 600)

    def test_optimize_maintains_aspect_ratio(self):
        """Test that optimize() maintains aspect ratio during resize."""
        # Create a wide image (800x200)
        test_image_path = Path(self.temp_dir) / "wide.png"
        img = Image.new('RGB', (800, 200), color='green')
        img.save(test_image_path, 'PNG')

        # Optimize
        result_path = self.optimizer.optimize(str(test_image_path), max_width=600, max_height=600)

        # Check aspect ratio is maintained (800:200 = 4:1)
        optimized = Image.open(result_path)
        original_ratio = 800 / 200
        optimized_ratio = optimized.width / optimized.height
        self.assertAlmostEqual(original_ratio, optimized_ratio, places=1)

    def test_optimize_returns_none_for_nonexistent_file(self):
        """Test that optimize() returns None for non-existent file."""
        result = self.optimizer.optimize("/nonexistent/path/image.png")
        self.assertIsNone(result)
