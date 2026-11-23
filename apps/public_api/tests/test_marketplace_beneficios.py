"""GET /api/v1/public/marketplace/beneficios/ — cupons, cashback e fidelidade
de TODAS as lojas do app, num pedido só (o perfil do app é do marketplace,
não de uma loja)."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import StoreCoupon, StoreOrder
from apps.public_api.tests.test_marketplace import add_product, make_store

URL = '/api/v1/public/marketplace/beneficios/'


def cupom(store, code, **kw):
    agora = timezone.now()
    d = dict(store=store, code=code, discount_type='percentage',
             discount_value=Decimal('10'), is_active=True, is_featured=True,
             valid_from=agora - timedelta(days=1), valid_until=agora + timedelta(days=9))
    d.update(kw)
    return StoreCoupon.objects.create(**d)


class BeneficiosTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username='dono', email='d@x.com', password='x')
        self.ce = make_store(self.owner, 'ce', plan='pro',
                             metadata={'loyalty_enabled': True, 'loyalty_salads_required': 8,
                                       'loyalty_item_label_plural': 'saladas'})
        add_product(self.ce)
        self.iv = make_store(self.owner, 'iv', plan='pro', metadata={'loyalty_enabled': False})
        add_product(self.iv)

    def _lojas(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertIn('no-store', r['Cache-Control'])
        return {l['slug']: l for l in r.json()['lojas']}

    def test_publico_lista_cupom_destacado_e_regra_da_fidelidade(self):
        cupom(self.ce, 'BEMVINDO10', first_order_only=True)
        cupom(self.ce, 'SECRETO', is_featured=False)
        cupom(self.ce, 'VENCIDO', valid_until=timezone.now() - timedelta(hours=1))
        lojas = self._lojas()
        ce = lojas['ce']
        self.assertEqual([c['code'] for c in ce['cupons']], ['BEMVINDO10'])
        self.assertTrue(ce['cupons'][0]['first_order_only'])
        self.assertEqual(ce['fidelidade']['threshold'], 8)
        self.assertEqual(ce['fidelidade']['item_label_plural'], 'saladas')
        self.assertEqual(ce['fidelidade']['progresso'], 0)
        self.assertEqual(ce['nome'], 'Ce')
        self.assertTrue(ce['logo_url'])
        self.assertIsNone(lojas['iv']['fidelidade'])
        self.assertEqual(lojas['iv']['cupons'], [])

    def test_cupom_de_primeira_compra_some_para_quem_ja_comprou(self):
        cupom(self.ce, 'BEMVINDO10', first_order_only=True)
        cupom(self.ce, 'SEMPRE10')
        cliente = User.objects.create_user(username='cliente_5563999990001', password='x')
        StoreOrder.objects.create(
            store=self.ce, customer=cliente, customer_name='C', customer_phone='5563999990001',
            status='delivered', payment_status='paid', subtotal=Decimal('30'), total=Decimal('30'))
        self.client.force_authenticate(cliente)
        self.assertEqual([c['code'] for c in self._lojas()['ce']['cupons']], ['SEMPRE10'])

    def test_logado_ve_o_proprio_progresso(self):
        from apps.stores.models import StoreLoyaltyAccount
        cliente = User.objects.create_user(username='cliente_5563999990002', password='x')
        StoreLoyaltyAccount.objects.create(store=self.ce, user=cliente, qualified_count=10)
        self.client.force_authenticate(cliente)
        fid = self._lojas()['ce']['fidelidade']
        self.assertEqual(fid['progresso'], 2)
        self.assertEqual(fid['premios'], 1)
