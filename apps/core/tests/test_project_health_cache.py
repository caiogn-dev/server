"""project-health: o payload é caro (~24 queries + inspect Celery). Deve cachear
o payload inteiro por escopo (~30s), não só o health_check do broker.

Antes: cache só do inspect() do Celery → 24 queries de contagem rodavam TODA chamada
(home congelava esperando esse request). Este teste prova que a 2ª chamada (cache
quente) faz muito menos queries que a 1ª.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APITestCase

from apps.stores.models import Store

User = get_user_model()


class ProjectHealthCacheTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username='ph-owner', email='ph@t.com', password='x')
        self.store = Store.objects.create(name='Loja PH', slug='loja-ph', owner=self.owner, status='active')
        self.client.force_authenticate(self.owner)

    def _count(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f'/api/v1/core/dashboard/project-health/?store={self.store.slug}')
        self.assertEqual(resp.status_code, 200, resp.content)
        return len(ctx.captured_queries), resp.data

    def test_payload_is_cached_per_scope(self):
        q_cold, data_cold = self._count()   # cache frio: computa tudo
        q_warm, data_warm = self._count()   # cache quente: deve cair MUITO

        # mesma resposta (cache fiel)
        self.assertEqual(data_cold['commerce'], data_warm['commerce'])
        # a 2ª chamada faz bem menos queries (payload cacheado)
        self.assertLess(
            q_warm, q_cold,
            f'cache não pegou: frio={q_cold} queries, quente={q_warm} queries'
        )
        # alvo: cache quente faz só a resolução de escopo (poucas queries), não as ~24
        self.assertLessEqual(
            q_warm, 8,
            f'cache quente ainda caro: {q_warm} queries (deveria ser só resolução de escopo)'
        )
