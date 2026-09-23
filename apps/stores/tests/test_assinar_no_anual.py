"""Contratar o ANUAL — o caminho que existia no backend e não tinha porta.

Medido em 22/09: `StoreSubscription.billing_cycle` existe, a fatura PIX sabe
cobrar `kind=annual` e `ANNUAL_MONTHS_CHARGED` está lá desde sempre. Mas o
endpoint `POST /stores/{slug}/subscribe/` nunca leu o ciclo: saía preapproval
MENSAL do Mercado Pago em qualquer caso.

Por isso o seletor Mensal/Anual foi REMOVIDO da tela em 21/09 — ele prometia
"2 meses grátis" e entregava assinatura mensal. Tirar da tela foi o certo
naquele dia; a correção é aqui embaixo.

O anual não é preapproval: é fatura PIX única. Misturar os dois caminhos
cobraria o ano E deixaria um cartão recorrente autorizado.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreSubscription

User = get_user_model()


class AssinarNoAnualTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-anual', password='x', email='dono-anual@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Anual', slug='loja-anual', owner=self.dono, status='active',
        )
        self.client.force_authenticate(user=self.dono)

    def _assinar(self, **corpo):
        return self.client.post(
            f'/api/v1/stores/{self.store.slug}/subscribe/', corpo, format='json',
        )

    def test_anual_grava_o_ciclo_e_NAO_cria_preapproval(self):
        with patch('apps.stores.services.pix_billing_service.generate_invoice') as fatura, \
             patch('apps.stores.services.subscription_service._sdk') as sdk:
            fatura.return_value = None
            r = self._assinar(plan='pro', billing_cycle='annual')

        self.assertIn(r.status_code, (200, 201), r.data)
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.billing_cycle, StoreSubscription.BillingCycle.ANNUAL)
        self.assertEqual(sub.plan, 'pro')
        self.assertFalse(sdk.called, 'anual não pode abrir preapproval de cartão')
        self.assertEqual(sub.mp_preapproval_id, '')

    def test_anual_pede_a_fatura_pix(self):
        with patch('apps.stores.services.pix_billing_service.generate_invoice') as fatura, \
             patch('apps.stores.services.subscription_service._sdk'):
            fatura.return_value = None
            self._assinar(plan='pro', billing_cycle='annual')

        self.assertTrue(fatura.called, 'anual tem que gerar a fatura PIX do ano')

    def test_sem_ciclo_continua_mensal(self):
        """Compatibilidade: quem já chamava sem o campo não pode virar anual."""
        with patch('apps.stores.services.subscription_service.create_subscription') as criar:
            criar.return_value = {'init_point': 'https://mp/x', 'preapproval_id': 'pre_1'}
            r = self._assinar(plan='pro')

        self.assertIn(r.status_code, (200, 201), r.data)
        self.assertTrue(criar.called)
        self.assertEqual(criar.call_args.kwargs.get('billing_cycle', 'monthly'), 'monthly')

    def test_ciclo_invalido_e_recusado(self):
        r = self._assinar(plan='pro', billing_cycle='trimestral')
        self.assertEqual(r.status_code, 400)
        self.assertNotIn('preapproval', str(r.data).lower())
