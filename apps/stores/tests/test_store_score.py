"""Score da Loja — gamificação do LOJISTA.

Pontua o que realmente move venda (catálogo completo, reputação, operação,
recursos ligados) e devolve conquistas acionáveis. Cada critério tem `done`,
`points` e `cta` — o painel mostra anel de progresso + próximos passos.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreProduct

User = get_user_model()

URL = '/api/v1/stores/reports/store-score/'


class StoreScoreTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-score', email='sc@x.com', password='x')
        self.store = Store.objects.create(
            name='Loja Score', slug='loja-score', owner=self.owner,
            status='active', billing_exempt=True,
        )
        self.client.force_authenticate(self.owner)

    def _get(self):
        return self.client.get(URL, {'store': self.store.slug})

    def test_loja_crua_score_baixo_com_ctas(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertLess(resp.data['score'], 30)
        self.assertEqual(resp.data['level'], 'bronze')
        pending = [c for c in resp.data['checklist'] if not c['done']]
        self.assertTrue(all('cta' in c and c['points'] > 0 for c in pending))
        keys = {c['key'] for c in resp.data['checklist']}
        self.assertIn('produtos_com_custo', keys)
        self.assertIn('google_review_url', keys)
        self.assertIn('logo', keys)

    def test_criterios_pontuam_quando_cumpridos(self):
        cat = StoreCategory.objects.create(store=self.store, name='C', slug='c-sc')
        for i in range(3):
            StoreProduct.objects.create(
                store=self.store, category=cat, name=f'P{i}', slug=f'p{i}-sc',
                price=Decimal('20'), cost_price=Decimal('8'),
                description='Uma descrição caprichada do prato com detalhes.',
                main_image_url='https://cdn.x/p.jpg',
            )
        self.store.logo_url = 'https://cdn.x/logo.png'
        self.store.description = 'A melhor loja da cidade'
        self.store.operating_hours = {'monday': {'open': '08:00', 'close': '18:00'}}
        self.store.metadata['google_review_url'] = 'https://g.page/r/X/review'
        self.store.save()

        before = self._get().data['score']
        self.assertGreater(before, 40)
        done_keys = {c['key'] for c in self._get().data['checklist'] if c['done']}
        for k in ('logo', 'descricao_loja', 'horarios', 'google_review_url',
                  'produtos_com_foto', 'produtos_com_descricao', 'produtos_com_custo'):
            self.assertIn(k, done_keys, k)

    def test_score_nao_estoura_100(self):
        resp = self._get()
        total = sum(c['points'] for c in resp.data['checklist'])
        self.assertEqual(total, 100)
