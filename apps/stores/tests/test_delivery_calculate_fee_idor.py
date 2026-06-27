"""
Testes de segurança (IDOR) na action calculate_fee do StoreDeliveryZoneViewSet.

A action recebia `store` no corpo e consultava StoreDeliveryZone/Store sem
verificar se o usuário tem acesso à loja — qualquer usuário autenticado podia
calcular (e vazar) a taxa de entrega de lojas concorrentes, incluindo a
default_delivery_fee no fallback.

Cenários:
  1. IDOR: usuário da loja A NÃO pode calcular a taxa da loja B (404, sem vazar fee).
  2. Própria loja: usuário da loja A calcula a taxa da própria loja (200 + fee).
  3. Fallback: sem zona correspondente, a default_delivery_fee só sai p/ loja acessível.
  4. Auth: endpoint exige autenticação.
"""
from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreDeliveryZone

User = get_user_model()

CALC_URL = '/api/v1/stores/delivery-zones/calculate_fee/'


def _make_zone(store, fee, min_km=0, max_km=100):
    return StoreDeliveryZone.objects.create(
        store=store,
        name='Zona',
        zone_type=StoreDeliveryZone.ZoneType.DISTANCE_BAND,
        min_km=Decimal(str(min_km)),
        max_km=Decimal(str(max_km)),
        delivery_fee=Decimal(str(fee)),
        is_active=True,
    )


class DeliveryCalculateFeeIDORTestCase(APITestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user(username='df-owner-a', password='pw')
        self.store_a = Store.objects.create(
            name='Loja DF-A', slug='df-loja-a', owner=self.owner_a,
            default_delivery_fee=Decimal('7.00'),
        )
        self.token_a = Token.objects.create(user=self.owner_a)

        self.owner_b = User.objects.create_user(username='df-owner-b', password='pw')
        self.store_b = Store.objects.create(
            name='Loja DF-B', slug='df-loja-b', owner=self.owner_b,
            default_delivery_fee=Decimal('99.00'),
        )
        _make_zone(self.store_a, fee='15.00')
        _make_zone(self.store_b, fee='42.00')

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token_a.key}')

    def test_idor_rejeita_calculo_de_outra_loja(self):
        """Usuário da loja A não pode calcular a taxa da loja B (sem vazar fee)."""
        resp = self.client.post(CALC_URL, {
            'store': str(self.store_b.id),
            'distance_km': 5,
        }, format='json')
        self.assertEqual(resp.status_code, 404, resp.data)
        self.assertNotIn('42', str(resp.data))

    def test_idor_fallback_nao_vaza_default_fee_de_outra_loja(self):
        """Sem zona correspondente, a default_delivery_fee da loja B não vaza."""
        resp = self.client.post(CALC_URL, {
            'store': str(self.store_b.id),
            'distance_km': 9999,
        }, format='json')
        self.assertEqual(resp.status_code, 404, resp.data)
        self.assertNotIn('99', str(resp.data))

    def test_calcula_taxa_da_propria_loja(self):
        """Usuário da loja A calcula a taxa da própria loja."""
        resp = self.client.post(CALC_URL, {
            'store': str(self.store_a.id),
            'distance_km': 5,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['fee'], '15.00')

    def test_fallback_propria_loja_retorna_default_fee(self):
        """Sem zona correspondente na própria loja, retorna a default_delivery_fee."""
        resp = self.client.post(CALC_URL, {
            'store': str(self.store_a.id),
            'distance_km': 9999,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['fee'], '7.00')

    def test_calculate_fee_exige_autenticacao(self):
        """Endpoint calculate_fee deve exigir autenticação."""
        self.client.credentials()
        resp = self.client.post(CALC_URL, {
            'store': str(self.store_a.id),
            'distance_km': 5,
        }, format='json')
        self.assertEqual(resp.status_code, 401)
