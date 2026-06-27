"""
Testes de segurança (IDOR) e correção de atributos na action validate do StoreCouponViewSet.

Cenários:
  1. IDOR: usuário autenticado da loja A NÃO pode validar cupom da loja B.
  2. Própria loja: usuário da loja A PODE validar cupom ativo da loja A.
  3. Auth: endpoint exige autenticação (401 sem token).
  4. Atributos: validate não levanta AttributeError em cupom válido com uso limitado.
"""
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreCoupon

User = get_user_model()

VALIDATE_URL = '/api/v1/stores/coupons/validate/'


def _make_coupon(store, code, **kwargs):
    now = timezone.now()
    defaults = dict(
        discount_type='percentage',
        discount_value=Decimal('10.00'),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
    )
    defaults.update(kwargs)
    return StoreCoupon.objects.create(store=store, code=code, **defaults)


class CouponValidateIDORTestCase(APITestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user(username='cv-owner-a', password='pw')
        self.store_a = Store.objects.create(name='Loja CV-A', slug='cv-loja-a', owner=self.owner_a)
        self.token_a = Token.objects.create(user=self.owner_a)

        self.owner_b = User.objects.create_user(username='cv-owner-b', password='pw')
        self.store_b = Store.objects.create(name='Loja CV-B', slug='cv-loja-b', owner=self.owner_b)

        self.coupon_b = _make_coupon(self.store_b, 'SECRETB10')
        self.coupon_a = _make_coupon(self.store_a, 'PROMO10')

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token_a.key}')

    def test_idor_rejeita_cupom_de_outra_loja(self):
        """IDOR P1: usuário da loja A não pode ver/validar cupom da loja B."""
        resp = self.client.get(VALIDATE_URL, {
            'code': 'SECRETB10',
            'store': str(self.store_b.id),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['valid'])
        self.assertIn('não encontrado', resp.data['error'].lower())

    def test_valida_cupom_da_propria_loja(self):
        """Usuário da loja A pode validar cupom ativo da própria loja."""
        resp = self.client.get(VALIDATE_URL, {
            'code': 'PROMO10',
            'store': str(self.store_a.id),
            'subtotal': '100.00',
        })
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data['valid'])
        self.assertIn('discount', resp.data)

    def test_validate_exige_autenticacao(self):
        """Endpoint validate deve retornar 401 para requisição sem token."""
        self.client.credentials()
        resp = self.client.get(VALIDATE_URL, {
            'code': 'PROMO10',
            'store': str(self.store_a.id),
        })
        self.assertEqual(resp.status_code, 401)

    def test_validate_sem_code_retorna_400(self):
        """Parâmetros obrigatórios: code e store."""
        resp = self.client.get(VALIDATE_URL, {'store': str(self.store_a.id)})
        self.assertEqual(resp.status_code, 400)

    def test_validate_cupom_com_usage_limit_nao_levanta_attributeerror(self):
        """Atributo usage_limit (não max_uses) não deve causar AttributeError."""
        coupon = _make_coupon(self.store_a, 'LIMITED5', usage_limit=5)
        resp = self.client.get(VALIDATE_URL, {
            'code': 'LIMITED5',
            'store': str(self.store_a.id),
            'subtotal': '50.00',
        })
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data['valid'])
