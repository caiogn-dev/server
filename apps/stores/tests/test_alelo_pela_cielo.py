"""Alelo no mesmo espaço do vale: duas conexões, uma tela.

A loja pode ter Pagar.me (VR/Pluxee/Ticket) e Cielo (Alelo) ao mesmo tempo.
Quem escolhe o gateway é a BANDEIRA que o cliente marcou.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.api.views.storefront_views import build_store_payment_config
from apps.stores.models import Store, StoreOrder, StorePayment, StorePaymentGateway
from apps.stores.services import cielo_ecommerce
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.voucher import registry
from apps.stores.services.voucher.base import ResultadoDaCobranca

User = get_user_model()

COBRAR_PAGARME = 'apps.stores.services.voucher.pagarme.PagarmeVoucherProvider.cobrar'
COBRAR_CIELO = 'apps.stores.services.voucher.cielo.CieloVoucherProvider.cobrar'


def aprovado(eid):
    return ResultadoDaCobranca(True, 'approved', eid, '', {'id': eid})


class AleloPelaCieloTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-alelo', password='x', email='owner-alelo@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Alelo', slug='loja-alelo', owner=self.owner, status='active',
        )
        self.pagarme = StorePaymentGateway.objects.create(
            store=self.store, name='Pagar.me', gateway_type='pagarme',
            api_key='sk_test_x', public_key='pk_test_y', is_enabled=True,
            is_sandbox=True, configuration={'voucher_brands': ['vr', 'ticket']},
        )
        self.cielo = StorePaymentGateway.objects.create(
            store=self.store, name='Cielo', gateway_type='cielo',
            api_key='MERCHANTKEY', public_key='merchant-id', api_secret='sop-secret',
            is_enabled=True, is_sandbox=True,
            configuration={'voucher_brands': ['alelo'], 'sop_client_id': 'sop-client'},
        )

    def _order(self, total='25.00'):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Cliente',
            customer_phone='5599999999999', customer_email='cli@real.com',
            subtotal=Decimal(total), total=Decimal(total),
        )

    def _dados(self, brand):
        return {'card_token': 'tok', 'brand': brand,
                'holder_name': 'ANA SILVA', 'holder_document': '39053344705'}

    # ── roteamento ───────────────────────────────────────────────────────────

    def test_a_bandeira_escolhe_o_gateway(self):
        assert registry.gateway_de_voucher(self.store, 'alelo') == self.cielo
        assert registry.gateway_de_voucher(self.store, 'vr') == self.pagarme
        assert registry.gateway_de_voucher(self.store, 'xpto') is None

    def test_a_loja_aceita_a_uniao_das_bandeiras_dos_dois(self):
        assert set(registry.bandeiras_da_loja(self.store)) == {'vr', 'ticket', 'alelo'}

    def test_alelo_e_cobrada_na_cielo_e_o_pagamento_fica_no_gateway_certo(self):
        order = self._order()
        with patch(COBRAR_CIELO, return_value=aprovado('pay-1')) as cielo, \
             patch(COBRAR_PAGARME) as pagarme:
            r = CheckoutService._cobrar_voucher(order, self._dados('alelo'))
        assert r['success'] is True
        cielo.assert_called_once()
        pagarme.assert_not_called()
        pagamento = StorePayment.objects.get(order=order)
        assert pagamento.gateway_id == self.cielo.id
        assert pagamento.external_id == 'pay-1'
        order.refresh_from_db()
        assert order.payment_status == StoreOrder.PaymentStatus.PAID

    def test_vr_continua_indo_para_o_pagarme(self):
        order = self._order()
        with patch(COBRAR_PAGARME, return_value=aprovado('or_1')) as pagarme, \
             patch(COBRAR_CIELO) as cielo:
            CheckoutService._cobrar_voucher(order, self._dados('vr'))
        pagarme.assert_called_once()
        cielo.assert_not_called()

    def test_bandeira_que_a_loja_nao_marcou_nao_cria_pagamento(self):
        order = self._order()
        r = CheckoutService._cobrar_voucher(order, self._dados('sodexo'))
        assert r['success'] is False
        assert 'bandeira' in r['error']
        assert not StorePayment.objects.filter(order=order).exists()

    def test_alelo_marcada_no_pagarme_nao_vaza_para_la(self):
        """Config suja não pode mandar Alelo para quem não sabe cobrar."""
        self.pagarme.configuration = {'voucher_brands': ['vr', 'alelo']}
        self.pagarme.save()
        self.cielo.is_enabled = False
        self.cielo.save()
        assert registry.gateway_de_voucher(self.store, 'alelo') is None

    # ── config pública ───────────────────────────────────────────────────────

    def test_config_publica_separa_as_bandeiras_por_trilho(self):
        config = build_store_payment_config(self.store)
        assert 'voucher' in config['enabled_methods']
        assert [b['value'] for b in config['pagarme']['brands']] == ['vr', 'ticket']
        assert [b['value'] for b in config['cielo']['brands']] == ['alelo']
        assert config['cielo']['brands'][0]['gateway'] == 'cielo'
        assert config['cielo']['is_sandbox'] is True

    def test_config_publica_nao_vaza_chave_da_cielo(self):
        texto = str(build_store_payment_config(self.store))
        for segredo in ('MERCHANTKEY', 'sop-secret', 'sop-client', 'merchant-id'):
            assert segredo not in texto

    def test_sem_credencial_do_sop_a_alelo_nao_e_anunciada(self):
        self.cielo.api_secret = ''
        self.cielo.save()
        config = build_store_payment_config(self.store)
        assert config['cielo']['brands'] == []
        # ...mas o vale continua valendo pelas bandeiras do Pagar.me.
        assert 'voucher' in config['enabled_methods']

    def test_so_cielo_tambem_liga_o_vale(self):
        self.pagarme.delete()
        config = build_store_payment_config(self.store)
        assert 'voucher' in config['enabled_methods']
        assert config['pagarme']['brands'] == []

    # ── token do formulário seguro ───────────────────────────────────────────

    def test_endpoint_do_sop_devolve_token_e_ambiente_sem_cache(self):
        with patch.object(cielo_ecommerce, 'token_do_sop', return_value='sop-token') as token:
            r = self.client.post(f'/api/v1/stores/{self.store.slug}/voucher/cielo/sop-token/')
        assert r.status_code == 200, r.content
        assert r.json() == {
            'access_token': 'sop-token', 'environment': 'sandbox',
            'script_url': cielo_ecommerce.SOP_SCRIPT_URL,
            'provider': 'braspag',
        }
        assert r['Cache-Control'] == 'no-store'
        assert token.call_args.args[0].id == self.cielo.id

    def test_endpoint_do_sop_em_loja_sem_cielo_e_404(self):
        self.cielo.delete()
        r = self.client.post(f'/api/v1/stores/{self.store.slug}/voucher/cielo/sop-token/')
        assert r.status_code == 404

    def test_sop_fora_do_ar_e_503_com_saida_para_o_cliente(self):
        with patch.object(cielo_ecommerce, 'token_do_sop',
                          side_effect=cielo_ecommerce.SopIndisponivel('x')):
            r = self.client.post(f'/api/v1/stores/{self.store.slug}/voucher/cielo/sop-token/')
        assert r.status_code == 503
        assert 'PIX' in r.json()['detail']
