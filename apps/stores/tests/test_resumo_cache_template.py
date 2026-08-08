"""O resumo em template também é cacheado.

Só o resultado de LLM ia para o cache. Com o provedor fora do ar — que é o
estado real hoje — TODA visita à home refazia a chamada, esperava o timeout
inteiro e só então devolvia o template. Inclusive a primeira visita do dia,
que é exatamente quando o dono abre o painel.

O TTL do template é curto de propósito: ele é o plano B, e assim que o
provedor voltar a próxima visita já tenta o LLM de novo em vez de ficar presa
seis horas no texto genérico.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.stores.models import Store
from apps.stores.services import ai_insights

User = get_user_model()
URL = '/api/v1/stores/ai/daily-summary/'


class ResumoCacheTemplateTest(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username='dono-cc', email='cc@x.com', password='x')
        self.loja = Store.objects.create(
            billing_exempt=True, name='Loja CC', slug='loja-cc', owner=self.owner, status='active',
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {Token.objects.get_or_create(user=self.owner)[0].key}'
        )

    def test_template_nao_repete_a_espera_a_cada_visita(self):
        with patch.object(ai_insights, '_llm_text', side_effect=TimeoutError('x')) as llm:
            self.client.get(URL, {'store': 'loja-cc'})
            r2 = self.client.get(URL, {'store': 'loja-cc'})

        self.assertEqual(
            llm.call_count, 1,
            'a segunda visita chamou o LLM de novo — cada uma paga o timeout inteiro',
        )
        self.assertTrue(r2.json()['cached'])
        self.assertEqual(r2.json()['source'], 'template')

    def test_refresh_ignora_o_cache_e_tenta_de_novo(self):
        # O botão de atualizar existe justamente para tentar o LLM outra vez.
        with patch.object(ai_insights, '_llm_text', side_effect=TimeoutError('x')) as llm:
            self.client.get(URL, {'store': 'loja-cc'})
            self.client.get(URL, {'store': 'loja-cc', 'refresh': '1'})
        self.assertEqual(llm.call_count, 2)
