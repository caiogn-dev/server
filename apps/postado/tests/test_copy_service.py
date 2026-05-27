from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.postado.services.copy_service import CopyService
from apps.postado.models import PostadoClient, PostadoPack, PostadoPost


class TestCopyService(TestCase):
    def setUp(self):
        self.client_obj = PostadoClient.objects.create(
            business_name="Burguer King Test",
            niche=PostadoClient.Niche.RESTAURANT,
            tone=PostadoClient.Tone.CASUAL,
            email="bk@test.com",
            whatsapp="61900000000",
        )
        self.pack = PostadoPack.objects.create(client=self.client_obj, month="2026-06")
        self.post = PostadoPost.objects.create(
            pack=self.pack,
            post_number=1,
            post_type=PostadoPost.PostType.PROMO,
        )

    @patch('apps.postado.services.copy_service.Anthropic')
    def test_generate_copy_fills_caption(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"caption":"Promoção incrível!","cta":"Peça agora","hashtags":"#burger #promoção"}')]
        )
        svc = CopyService()
        result = svc.generate(self.post)
        self.assertIn('caption', result)
        self.assertIn('cta', result)
        self.assertIn('hashtags', result)
        self.assertEqual(result['caption'], 'Promoção incrível!')

    @patch('apps.postado.services.copy_service.Anthropic')
    def test_generate_fallback_on_api_error(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")
        svc = CopyService()
        result = svc.generate(self.post)
        self.assertIn('caption', result)
        self.assertIn('cta', result)
        self.assertIn('hashtags', result)

    @patch('apps.postado.services.copy_service.Anthropic')
    def test_generate_strips_markdown_code_block(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='```json\n{"caption":"Test","cta":"Teste","hashtags":"#test"}\n```')]
        )
        svc = CopyService()
        result = svc.generate(self.post)
        self.assertEqual(result['caption'], 'Test')
