"""O checklist de onboarding tem que cobrar o meio de recebimento.

Incidente 16/set: o primeiro cliente pago montou logo, banner, cor e tagline,
e parou. O checklist dizia 3/6 e não mencionava pagamento em nenhum passo — e
pagamento é a única coisa que, faltando, faz o pedido morrer no checkout com
"pagamento bloqueado de propósito". A loja dele registrou 4 carrinhos e 3
bloqueios desses em 12 horas.

Uma loja podia bater 6/6 no checklist e não conseguir receber um centavo. O
passo que faltava não é cosmético: é o único que decide se entra dinheiro.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store
from apps.stores.services.onboarding_checklist import build_checklist

User = get_user_model()


class OnboardingPassoPagamentoTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono_onb', email='dono@onb.com', password='x'
        )
        self.loja = Store.objects.create(
            name='Loja Onb', slug='loja-onb', owner=self.dono, status='active'
        )

    def _passo(self, store, key):
        passos = {s['key']: s for s in build_checklist(store)['steps']}
        return passos.get(key)

    def test_existe_passo_de_pagamento(self):
        self.assertIsNotNone(
            self._passo(self.loja, 'payment'),
            'checklist sem passo de pagamento: a loja fecha 100% e não recebe',
        )

    def test_passo_de_pagamento_nasce_pendente(self):
        self.assertFalse(self._passo(self.loja, 'payment')['done'])

    def test_gateway_proprio_cumpre_o_passo(self):
        from apps.stores.models import StorePaymentGateway

        StorePaymentGateway.objects.create(
            store=self.loja, name='MP', gateway_type='mercadopago',
            is_enabled=True, access_token='TOKEN-FALSO',
        )
        self.assertTrue(self._passo(self.loja, 'payment')['done'])

    def test_gateway_da_plataforma_cumpre_o_passo(self):
        """Loja do próprio dono recebe na conta da plataforma — também conta."""
        self.loja.usa_gateway_da_plataforma = True
        self.loja.save(update_fields=['usa_gateway_da_plataforma'])
        self.assertTrue(self._passo(self.loja, 'payment')['done'])

    def test_gateway_inativo_nao_cumpre_o_passo(self):
        from apps.stores.models import StorePaymentGateway

        StorePaymentGateway.objects.create(
            store=self.loja, name='MP', gateway_type='mercadopago',
            is_enabled=False, access_token='TOKEN-FALSO',
        )
        self.assertFalse(
            self._passo(self.loja, 'payment')['done'],
            'gateway desligado não recebe pagamento — não pode contar como pronto',
        )
