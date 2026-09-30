"""Credencial da Cielo com caractere a mais derrubava a Alelo com HTTP 500.

Em 30/09 o Merchant ID foi salvo como 'd55454c7-...-92013d8.' — com o ponto
final da frase de onde foi copiado. A Cielo aceitava o OAuth e quebrava com
500 no AccessToken, sem dizer por quê. O painel tem que recusar na hora.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.api.payment_serializers import StorePaymentGatewaySerializer
from apps.stores.models import Store, StorePaymentGateway
from apps.stores.services import cielo_ecommerce

User = get_user_model()
MID = 'd55454c7-f324-4fcd-a618-4f61c92013d8'
CID = '1da50a26-af11-45e2-a8f8-7e41410b65e9'


class CredenciaisDaCieloTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-cred', password='x', email='o-cred@real.com')
        self.store = Store.objects.create(name='Loja Cred', slug='loja-cred', owner=self.owner, status='active')

    def _dados(self, **extra):
        base = {
            'store': self.store.id, 'name': 'Cielo (Alelo)', 'gateway_type': 'cielo',
            'public_key': MID, 'api_key': 'K' * 40, 'api_secret': 'segredo',
            'configuration': {'voucher_brands': ['alelo'], 'sop_client_id': CID},
        }
        base.update(extra)
        return base

    def test_merchant_id_com_ponto_final_e_recusado(self):
        s = StorePaymentGatewaySerializer(data=self._dados(public_key=MID + '.'))
        assert not s.is_valid()
        assert 'public_key' in s.errors

    def test_client_id_do_sop_invalido_e_recusado(self):
        s = StorePaymentGatewaySerializer(data=self._dados(
            configuration={'voucher_brands': ['alelo'], 'sop_client_id': 'abc'}))
        assert not s.is_valid()
        assert 'configuration' in s.errors

    def test_espaco_em_volta_e_limpo_e_nao_recusado(self):
        s = StorePaymentGatewaySerializer(data=self._dados(
            public_key=f'  {MID}\n',
            configuration={'voucher_brands': ['alelo'], 'sop_client_id': f' {CID} '}))
        assert s.is_valid(), s.errors
        gw = s.save()
        assert gw.public_key == MID
        assert gw.configuration['sop_client_id'] == CID

    def test_merchant_key_fora_de_40_caracteres_e_recusada(self):
        s = StorePaymentGatewaySerializer(data=self._dados(api_key='curta'))
        assert not s.is_valid()
        assert 'api_key' in s.errors

    def test_edicao_sem_redigitar_a_merchant_key_continua_valendo(self):
        gw = StorePaymentGateway.objects.create(
            store=self.store, name='Cielo', gateway_type='cielo', public_key=MID,
            api_key='K' * 40, api_secret='s', configuration={'sop_client_id': CID})
        s = StorePaymentGatewaySerializer(gw, data={'api_key': '', 'is_enabled': False}, partial=True)
        assert s.is_valid(), s.errors

    def test_edicao_parcial_com_merchant_id_ruim_tambem_e_recusada(self):
        gw = StorePaymentGateway.objects.create(
            store=self.store, name='Cielo', gateway_type='cielo', public_key=MID,
            api_key='K' * 40, api_secret='s', configuration={'sop_client_id': CID})
        s = StorePaymentGatewaySerializer(gw, data={'public_key': MID + '.'}, partial=True)
        assert not s.is_valid()

    def test_pagarme_nao_e_afetado(self):
        s = StorePaymentGatewaySerializer(data={
            'store': self.store.id, 'name': 'Pagar.me', 'gateway_type': 'pagarme',
            'public_key': 'pk_test_qualquer', 'api_key': 'sk_test_x',
        })
        assert s.is_valid(), s.errors


def test_erro_do_sop_leva_o_corpo_da_resposta_para_o_log(settings):
    """O 500 de 30/09 só dizia 'respondeu 500'. Com o corpo, o motivo aparece."""
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    from django.core.cache import cache
    cache.clear()
    from types import SimpleNamespace

    oauth = mock.Mock(status_code=201)
    oauth.json.return_value = {'access_token': 'b', 'expires_in': 599}
    quebrado = mock.Mock(status_code=500, text='{"Message":"MerchantId invalido"}')
    quebrado.json.return_value = {'Message': 'MerchantId invalido'}
    gw = SimpleNamespace(id=1, public_key=MID, api_secret='s', is_sandbox=False,
                         configuration={'sop_client_id': CID})
    with mock.patch.object(cielo_ecommerce.requests, 'post', side_effect=[oauth, quebrado]):
        try:
            cielo_ecommerce.token_do_sop(gw)
        except cielo_ecommerce.SopIndisponivel as erro:
            assert '500' in str(erro)
            assert 'MerchantId invalido' in str(erro)
        else:
            raise AssertionError('deveria ter levantado')
