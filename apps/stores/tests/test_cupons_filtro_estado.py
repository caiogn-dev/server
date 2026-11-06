"""Lista de cupons: filtros de status (ativo/inativo/expirado) e tipo no servidor."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCoupon

User = get_user_model()
URL = '/api/v1/stores/coupons/'


class FiltroDeCuponsTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='fc-owner', password='pw')
        self.store = Store.objects.create(name='Loja FC', slug='fc-loja', owner=self.owner)
        now = timezone.now()
        mk = lambda code, **kw: StoreCoupon.objects.create(
            store=self.store, code=code,
            discount_type=kw.pop('discount_type', 'percentage'),
            discount_value=Decimal('10'),
            valid_from=now - timedelta(days=10),
            valid_until=kw.pop('valid_until', now + timedelta(days=10)), **kw)
        mk('VIVO')
        mk('PAUSADO', is_active=False)
        mk('VELHO', valid_until=now - timedelta(days=1))
        mk('FIXO', discount_type='fixed')
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def codes(self, **params):
        r = self.client.get(URL, {'store': str(self.store.id), **params})
        self.assertEqual(r.status_code, 200)
        data = r.data['results'] if isinstance(r.data, dict) and 'results' in r.data else r.data
        return {c['code'] for c in data}

    def test_sem_filtro_lista_todos(self):
        self.assertEqual(self.codes(), {'VIVO', 'PAUSADO', 'VELHO', 'FIXO'})

    def test_inativos(self):
        self.assertEqual(self.codes(is_active='false'), {'PAUSADO'})

    def test_expirados(self):
        self.assertEqual(self.codes(expired='true'), {'VELHO'})

    def test_ativos_nao_inclui_expirado(self):
        self.assertEqual(self.codes(is_active='true', expired='false'), {'VIVO', 'VELHO', 'FIXO'} - {'VELHO'})

    def test_tipo(self):
        self.assertEqual(self.codes(discount_type='fixed'), {'FIXO'})
