from unittest.mock import patch, MagicMock


def _resposta(texto):
    """A resposta no formato do cliente OpenAI-compatível.

    Estes testes nasceram contra a Anthropic (`messages.create`, `content[].text`).
    O serviço migrou para NVIDIA NIM — que fala o protocolo da OpenAI,
    `chat.completions.create` com `choices[].message.content` — e os mocks
    ficaram apontando para um nome que o módulo não tem mais. Resultado: três
    testes estourando em `AttributeError` na suíte completa, sem nunca chegar
    a exercitar o serviço.
    """
    return MagicMock(choices=[MagicMock(message=MagicMock(content=texto))])
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

    @patch('apps.postado.services.copy_service.OpenAI')
    def test_generate_copy_fills_caption(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _resposta(
            '{"caption":"Promoção incrível!","cta":"Peça agora","hashtags":"#burger #promoção"}'
        )
        svc = CopyService()
        result = svc.generate(self.post)
        self.assertIn('caption', result)
        self.assertIn('cta', result)
        self.assertIn('hashtags', result)
        self.assertEqual(result['caption'], 'Promoção incrível!')

    @patch('apps.postado.services.copy_service.OpenAI')
    def test_generate_fallback_on_api_error(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")
        svc = CopyService()
        result = svc.generate(self.post)
        self.assertIn('caption', result)
        self.assertIn('cta', result)
        self.assertIn('hashtags', result)

    @patch('apps.postado.services.copy_service.OpenAI')
    def test_generate_strips_markdown_code_block(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _resposta(
            '```json\n{"caption":"Test","cta":"Teste","hashtags":"#test"}\n```'
        )
        svc = CopyService()
        result = svc.generate(self.post)
        self.assertEqual(result['caption'], 'Test')
