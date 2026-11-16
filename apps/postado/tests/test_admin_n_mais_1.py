from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.postado.models import PostadoClient, PostadoPack, PostadoPost


@override_settings(POSTADO_ADMIN_TOKEN='tok')
class AdminNMaisUmTest(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer tok')
        self.n = 0

    def _populate(self, qtd):
        for _ in range(qtd):
            self.n += 1
            c = PostadoClient.objects.create(
                business_name=f'C{self.n}', niche='x', tone='casual',
                email=f'c{self.n}@t.com', whatsapp=f'11{self.n:09d}',
            )
            for m in ('2025-05', '2025-06'):
                p = PostadoPack.objects.create(client=c, month=m, status='review')
                for i in range(2):
                    PostadoPost.objects.create(pack=p, post_number=i + 1)

    def _queries(self, url):
        with CaptureQueriesContext(connection) as ctx:
            r = self.api.get(url)
        self.assertEqual(r.status_code, 200)
        return len(ctx), r.json()

    def test_lista_clientes_queries_constantes(self):
        self._populate(2)
        q2, _ = self._queries('/api/postado/admin/clients/')
        self._populate(6)
        q8, data = self._queries('/api/postado/admin/clients/')
        self.assertEqual(q2, q8)
        self.assertEqual(data[0]['pack_count'], 2)
        self.assertIn(data[0]['latest_pack_status'], ('review',))

    def test_dashboard_fila_revisao_queries_constantes(self):
        self._populate(2)
        q2, _ = self._queries('/api/postado/admin/dashboard/')
        self._populate(6)
        q8, data = self._queries('/api/postado/admin/dashboard/')
        self.assertEqual(q2, q8)
        self.assertEqual(data['review_queue'][0]['total_posts'], 2)

    def test_detalhe_cliente_queries_constantes(self):
        self._populate(1)
        c = PostadoClient.objects.get()
        q1, _ = self._queries(f'/api/postado/admin/clients/{c.id}/')
        for m in ('2025-07', '2025-08', '2025-09'):
            PostadoPack.objects.create(client=c, month=m, status='review')
        q4, data = self._queries(f'/api/postado/admin/clients/{c.id}/')
        self.assertEqual(q1, q4)
        self.assertEqual(data['pack_count'], 5)
