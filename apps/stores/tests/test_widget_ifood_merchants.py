"""Widget oficial do iFood: só vão as lojas que o app de verdade tem autorizadas.

Medido 26/11: o dono tem a Cê e a loja de TESTE da homologação; as duas iam
para o widget e o iFood respondia "Usuário não tem acesso em alguns dos
restaurantes inclusos no widget" — derrubando o widget inteiro.
"""
import base64
import json
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.models.ifood import StoreIfoodIntegration
from apps.stores.services import ifood_oauth

User = get_user_model()
URL = '/api/v1/stores/integracoes/ifood/merchants/'
CE = '4ea4f892-62f1-4037-a95f-1a903a55be70'
TESTE = '00f0d5a7-6142-4120-b34d-1b1d36cdecec'


def _jwt(merchant_scope):
    corpo = base64.urlsafe_b64encode(json.dumps({'merchant_scope': merchant_scope}).encode()).decode().rstrip('=')
    return f'x.{corpo}.y'


class MerchantsDoWidgetTests(APITestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-widget', password='x')
        for slug, merchant in (('ce-w', CE), ('teste-w', TESTE)):
            loja = Store.objects.create(name=slug, slug=slug, owner=dono, status='active')
            StoreIfoodIntegration.objects.create(store=loja, merchant_id=merchant, conectado=True)
        self.client.force_authenticate(dono)

    def test_loja_que_o_app_nao_tem_autorizada_fica_fora(self):
        with mock.patch.object(ifood_oauth, 'token', return_value=_jwt([f'{CE}:order', f'{CE}:merchant'])):
            resposta = self.client.get(URL)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data['merchant_ids'], [CE])

    def test_sem_conseguir_ler_o_token_manda_a_lista_da_conta(self):
        with mock.patch.object(ifood_oauth, 'token', side_effect=ifood_oauth.IfoodNaoConfigurado('x')):
            resposta = self.client.get(URL)
        self.assertEqual(sorted(resposta.data['merchant_ids']), sorted([CE, TESTE]))
