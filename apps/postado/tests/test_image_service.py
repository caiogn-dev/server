import io
import base64
from unittest.mock import patch, MagicMock
from django.test import TestCase
from PIL import Image
from apps.postado.services.image_service import ImageService
from apps.postado.models import PostadoClient, PostadoPack, PostadoPost


def _make_png_b64(size=(100, 100), color=(255, 0, 0)) -> str:
    img = Image.new('RGB', size, color=color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


class TestImageService(TestCase):
    def _make_post(self, niche='restaurant'):
        c = PostadoClient.objects.create(
            business_name="Test Biz",
            niche=niche,
            tone='casual',
            brand_colors=["#FF5733"],
            email=f"img_{niche}@test.com",
            whatsapp=f"619000000{hash(niche) % 10}",
        )
        pack = PostadoPack.objects.create(client=c, month="2026-06")
        return PostadoPost.objects.create(pack=pack, post_number=1, post_type='promo')

    @patch('apps.postado.services.image_service.openai.images.generate')
    def test_generate_base_image_returns_pil_1080(self, mock_gen):
        mock_gen.return_value = MagicMock(data=[MagicMock(b64_json=_make_png_b64())])
        svc = ImageService()
        post = self._make_post()
        result = svc.generate_base_image(post, caption="Promoção especial!")
        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (1080, 1080))

    @patch('apps.postado.services.image_service.openai.images.generate')
    def test_generate_base_image_fallback_on_error(self, mock_gen):
        mock_gen.side_effect = Exception("API down")
        svc = ImageService()
        post = self._make_post()
        result = svc.generate_base_image(post, caption="Test")
        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (1080, 1080))

    def test_composite_feed_returns_1080x1080(self):
        svc = ImageService()
        base = Image.new('RGB', (1080, 1080), color=(100, 150, 200))
        result = svc.composite_feed(base, "Meu Negócio", "Legenda teste", "Peça já")
        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (1080, 1080))

    def test_to_stories_returns_1080x1920(self):
        svc = ImageService()
        feed = Image.new('RGB', (1080, 1080), color=(50, 50, 50))
        result = svc.to_stories(feed)
        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (1080, 1920))

    def test_save_to_bytes_returns_png(self):
        svc = ImageService()
        img = Image.new('RGB', (100, 100), color=(0, 255, 0))
        data = svc.save_to_bytes(img)
        self.assertIsInstance(data, bytes)
        self.assertTrue(data[:4] == b'\x89PNG')

    def test_placeholder_image_uses_brand_color(self):
        svc = ImageService()
        img = svc._placeholder_image('#FF0000', (200, 200))
        self.assertEqual(img.size, (200, 200))
        pixel = img.getpixel((100, 100))
        self.assertEqual(pixel[0], 255)  # Red channel
        self.assertEqual(pixel[1], 0)    # Green channel
        self.assertEqual(pixel[2], 0)    # Blue channel
