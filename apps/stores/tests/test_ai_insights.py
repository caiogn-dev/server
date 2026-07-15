"""IA do painel: resumo diário e análise de conversas — escopo por dono, LLM mockado."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder, StoreOrderItem

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username='dono-ai', email='ai@loja.com', password='x')
        self.intruder = User.objects.create_user(username='intruso-ai', email='in@x.com', password='x')
        self.store = Store.objects.create(name='Loja IA', slug='loja-ia', owner=self.owner)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.owner).key}')

    def _order(self, when, total=50, status='delivered', items=None):
        o = StoreOrder.objects.create(
            store=self.store, customer_phone='5563000000000',
            status=status, subtotal=total, total=total,
        )
        StoreOrder.objects.filter(pk=o.pk).update(created_at=when)
        for name, qty in (items or [('Lasanha', 1)]):
            StoreOrderItem.objects.create(
                order=o, product_name=name, unit_price=25, quantity=qty, subtotal=25 * qty,
            )
        return o


class DailySummaryTest(_Base):
    def test_stats_and_llm_summary(self):
        yesterday = timezone.now() - timedelta(days=1)
        self._order(yesterday, total=100, items=[('Lasanha', 2)])
        self._order(yesterday, total=50, items=[('Rondelli', 1)])
        self._order(yesterday, total=30, status='cancelled')
        with patch('apps.stores.services.ai_insights._llm_text', return_value='Resumo gerado pela IA.'):
            resp = self.client.get('/api/v1/stores/ai/daily-summary/', {'store': 'loja-ia'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['stats']['orders'], 2)
        self.assertEqual(data['stats']['revenue'], 150.0)
        self.assertEqual(data['stats']['cancelled'], 1)
        self.assertEqual(data['stats']['top_products'][0]['name'], 'Lasanha')
        self.assertEqual(data['summary'], 'Resumo gerado pela IA.')
        self.assertEqual(data['source'], 'llm')

    def test_llm_down_falls_back_to_template(self):
        self._order(timezone.now() - timedelta(days=1), total=80)
        with patch('apps.stores.services.ai_insights._llm_text', side_effect=RuntimeError('down')):
            resp = self.client.get('/api/v1/stores/ai/daily-summary/', {'store': 'loja-ia'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['source'], 'template')
        self.assertIn('pedidos', data['summary'])

    def test_other_users_store_is_404(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.intruder).key}')
        resp = client.get('/api/v1/stores/ai/daily-summary/', {'store': 'loja-ia'})
        self.assertEqual(resp.status_code, 404)

    def test_llm_result_is_cached(self):
        self._order(timezone.now() - timedelta(days=1))
        with patch('apps.stores.services.ai_insights._llm_text', return_value='ok') as llm:
            self.client.get('/api/v1/stores/ai/daily-summary/', {'store': 'loja-ia'})
            resp2 = self.client.get('/api/v1/stores/ai/daily-summary/', {'store': 'loja-ia'})
        self.assertEqual(llm.call_count, 1)
        self.assertTrue(resp2.json()['cached'])


class ProviderResolutionTest(TestCase):
    def test_pseudo_agent_does_not_inherit_anthropic_base_url_default(self):
        """Bug 15/jul: Agent.base_url tem default anthropic — o pseudo-agente
        OpenAI postava em api.anthropic.com/chat/completions (404) e o resumo
        caía sempre no template."""
        from django.test import override_settings
        from apps.stores.services import ai_insights

        captured = {}

        def fake_create_llm(agent):
            captured['base_url'] = agent.base_url
            captured['provider'] = agent.provider
            return object()

        with override_settings(
            NVIDIA_API_KEY='', ANTHROPIC_API_KEY='', KIMI_API_KEY='', OPENAI_API_KEY='sk-test',
        ):
            with patch('apps.agents.runtime.factory.create_llm', fake_create_llm):
                ai_insights.get_insights_llm()
        self.assertEqual(captured['base_url'], '')

    def test_nvidia_nim_is_first_choice_with_live_default_model(self):
        """NVIDIA NIM é o provider da casa; o default do modelo não pode ser o
        405b aposentado do .env — usa NVIDIA_INSIGHTS_MODEL/llama-3.3."""
        from django.test import override_settings
        from apps.agents.models import Agent
        from apps.stores.services import ai_insights

        captured = {}

        def fake_create_llm(agent):
            captured['provider'] = agent.provider
            captured['model'] = agent.model_name
            return object()

        with override_settings(
            NVIDIA_API_KEY='nvapi-test', NVIDIA_INSIGHTS_MODEL='',
            ANTHROPIC_API_KEY='', KIMI_API_KEY='', OPENAI_API_KEY='sk-test',
        ):
            with patch('apps.agents.runtime.factory.create_llm', fake_create_llm):
                ai_insights.get_insights_llm()
        self.assertEqual(captured['provider'], Agent.AgentProvider.NVIDIA)
        self.assertEqual(captured['model'], 'meta/llama-3.1-70b-instruct')


class ConversationInsightsTest(_Base):
    def _wire_whatsapp(self):
        from apps.conversations.models import Conversation
        from apps.whatsapp.models import Message, WhatsAppAccount
        account = WhatsAppAccount.objects.create(name='AI', phone_number_id='PHAI', waba_id='WAI')
        self.store.whatsapp_account = account
        self.store.save(update_fields=['whatsapp_account'])
        conv = Conversation.objects.create(account=account, phone_number='5563911112222')
        for i, text in enumerate(['vocês têm opção vegana?', 'demorou demais ontem', 'qual o horário?']):
            Message.objects.create(
                account=account, conversation=conv, direction='inbound',
                message_type='text', content={'text': text},
                whatsapp_message_id=f'wamid.test-ai-{i}',
            )
        return account

    def test_insights_parsed_from_llm_json(self):
        self._wire_whatsapp()
        fake = ('{"faqs": ["horário de funcionamento"], "complaints": ["demora"], '
                '"opportunities": ["opção vegana"], "sentiment": "neutro", "summary": "Resumo."}')
        with patch('apps.stores.services.ai_insights._llm_text', return_value=fake):
            resp = self.client.get('/api/v1/stores/ai/conversation-insights/', {'store': 'loja-ia'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['message_count'], 3)
        self.assertEqual(data['insights']['sentiment'], 'neutro')
        self.assertEqual(data['source'], 'llm')

    def test_no_messages_returns_gracefully(self):
        resp = self.client.get('/api/v1/stores/ai/conversation-insights/', {'store': 'loja-ia'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['source'], 'none')

    def test_llm_error_returns_graceful_payload(self):
        self._wire_whatsapp()
        with patch('apps.stores.services.ai_insights._llm_text', side_effect=RuntimeError('boom')):
            resp = self.client.get('/api/v1/stores/ai/conversation-insights/', {'store': 'loja-ia'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['source'], 'error')
