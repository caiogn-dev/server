"""Autenticação do iFood: app CENTRALIZADO, uma credencial para todas as lojas.

Mudou em 19/11/2026. O modelo distribuído (lojista gera userCode, cola código
no painel) foi trocado pelo centralizado porque:

- webhook de eventos só existe para app centralizado no portal do iFood;
- o próprio portal descreve o centralizado como "instalação centralizada para
  todos os parceiros" — é o caso de um SaaS na nuvem;
- a loja não precisa mais trocar código: informa o ID dela no iFood e aprova o
  app no Portal do Parceiro.

O token é `client_credentials`, dura ~6 h e vale para TODAS as lojas que
autorizaram o app. Fica em cache; quem chama recebe um token bom e, se o iFood
responder 401, esquece o token e pede outro uma vez.

Há dois apps: "pedidos" (Order/Events — credencial só sai após homologação) e
"entregas" (Shipping — chamar entregador para pedido nosso).
"""
from unittest import mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.stores.models import Store
from apps.stores.services import ifood_oauth

User = get_user_model()

CREDENCIAIS = {
    'IFOOD_CLIENT_ID': 'app-pedidos', 'IFOOD_CLIENT_SECRET': 'segredo-p',
    'IFOOD_ENTREGAS_CLIENT_ID': 'app-entregas', 'IFOOD_ENTREGAS_CLIENT_SECRET': 'segredo-e',
}
MERCHANT = '00f0d5a7-6142-4120-b34d-1b1d36cdecec'


@override_settings(**CREDENCIAIS)
class TokenDoAppTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_pede_client_credentials_com_a_credencial_do_app(self):
        with patch.object(ifood_oauth, '_post', return_value={'accessToken': 'tok-e', 'expiresIn': 21600}) as post:
            self.assertEqual(ifood_oauth.token('entregas'), 'tok-e')
        dados = post.call_args.args[1]
        self.assertEqual(dados['grantType'], 'client_credentials')
        self.assertEqual(dados['clientId'], 'app-entregas')
        self.assertEqual(dados['clientSecret'], 'segredo-e')

    def test_token_fica_em_cache(self):
        with patch.object(ifood_oauth, '_post', return_value={'accessToken': 'tok', 'expiresIn': 21600}) as post:
            ifood_oauth.token('pedidos')
            ifood_oauth.token('pedidos')
        self.assertEqual(post.call_count, 1)

    def test_cada_app_tem_o_seu_token(self):
        respostas = [{'accessToken': 'tok-p', 'expiresIn': 21600}, {'accessToken': 'tok-e', 'expiresIn': 21600}]
        with patch.object(ifood_oauth, '_post', side_effect=respostas):
            self.assertEqual(ifood_oauth.token('pedidos'), 'tok-p')
            self.assertEqual(ifood_oauth.token('entregas'), 'tok-e')

    def test_esquecer_obriga_a_pedir_de_novo(self):
        with patch.object(ifood_oauth, '_post', return_value={'accessToken': 'tok', 'expiresIn': 21600}) as post:
            ifood_oauth.token('entregas')
            ifood_oauth.esquecer_token('entregas')
            ifood_oauth.token('entregas')
        self.assertEqual(post.call_count, 2)

    @override_settings(IFOOD_ENTREGAS_CLIENT_ID='', IFOOD_ENTREGAS_CLIENT_SECRET='')
    def test_app_sem_credencial_nao_esta_configurado(self):
        self.assertFalse(ifood_oauth.esta_configurado('entregas'))
        self.assertTrue(ifood_oauth.esta_configurado('pedidos'))
        with self.assertRaises(ifood_oauth.IfoodNaoConfigurado):
            ifood_oauth.token('entregas')

    def test_recusa_do_ifood_vira_erro_legivel(self):
        with patch.object(ifood_oauth, '_post', side_effect=ifood_oauth.IfoodRecusou('403: No permissions')):
            with self.assertRaises(ifood_oauth.IfoodRecusou):
                ifood_oauth.token('entregas')


@override_settings(**CREDENCIAIS)
class LojaNoIfoodTest(TestCase):
    def setUp(self):
        cache.clear()
        dono = User.objects.create_user(username='dona-ifood', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-ifood', owner=dono,
            store_type='food', status='active',
        )

    def test_id_que_nao_e_uuid_e_recusado(self):
        with self.assertRaises(ValueError):
            ifood_oauth.vincular(self.store, '4327433')

    def test_vincular_guarda_o_id_e_confere_o_acesso(self):
        with patch.object(ifood_oauth, 'api', return_value={'id': MERCHANT, 'name': 'Cê Saladas Palmas'}) as api:
            integracao = ifood_oauth.vincular(self.store, f'  {MERCHANT.upper()} ')
        self.assertEqual(integracao.merchant_id, MERCHANT)
        self.assertTrue(integracao.conectado)
        self.assertEqual(integracao.merchant_name, 'Cê Saladas Palmas')
        self.assertIn(f'/merchant/v1.0/merchants/{MERCHANT}', api.call_args.args[2])

    def test_loja_que_ainda_nao_autorizou_fica_aguardando(self):
        with patch.object(ifood_oauth, 'api', side_effect=ifood_oauth.IfoodRecusou('403: No permissions granted')):
            integracao = ifood_oauth.vincular(self.store, MERCHANT)
        self.assertEqual(integracao.merchant_id, MERCHANT)
        self.assertFalse(integracao.conectado)
        self.assertIn('Portal do Parceiro', integracao.ultimo_erro)

    def test_token_valido_exige_loja_vinculada(self):
        self.assertIsNone(ifood_oauth.token_valido(self.store))
        integracao = ifood_oauth.integracao_da_loja(self.store)
        integracao.merchant_id = MERCHANT
        integracao.save()
        with patch.object(ifood_oauth, '_post', return_value={'accessToken': 'tok-p', 'expiresIn': 21600}):
            self.assertEqual(ifood_oauth.token_valido(self.store), 'tok-p')

    def test_desconectar_esquece_a_loja_e_desliga_as_entregas(self):
        integracao = ifood_oauth.integracao_da_loja(self.store)
        integracao.merchant_id = MERCHANT
        integracao.conectado = True
        integracao.frete_pelo_ifood = True
        integracao.chamar_entregador = 'confirmado'
        integracao.save()
        ifood_oauth.desconectar(self.store)
        integracao.refresh_from_db()
        self.assertEqual(integracao.merchant_id, '')
        self.assertFalse(integracao.conectado)
        self.assertFalse(integracao.frete_pelo_ifood)
        self.assertEqual(integracao.chamar_entregador, 'manual')


@override_settings(**CREDENCIAIS)
class ApiTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_401_esquece_o_token_e_tenta_uma_vez(self):
        class R:
            def __init__(self, code, body=b'{"ok": 1}'):
                self.status_code, self.content, self.text = code, body, body.decode()

            def json(self):
                return {'ok': 1}

        tokens = iter(['velho', 'novo'])
        with patch.object(ifood_oauth, 'token', side_effect=lambda app, **k: next(tokens)), \
             patch('requests.request', side_effect=[R(401, b'expired'), R(200)]) as req:
            self.assertEqual(ifood_oauth.api('entregas', 'GET', '/x'), {'ok': 1})
        self.assertEqual(req.call_count, 2)
        self.assertEqual(req.call_args.kwargs['headers']['Authorization'], 'Bearer novo')


    def test_202_com_corpo_devolve_o_json(self):
        """Shipping: POST /orders responde 202 COM {id, trackingUrl} (medido ao vivo 20/11)."""
        r = mock.Mock(status_code=202, content=b'{"id": "e1", "trackingUrl": "https://t"}')
        r.json.return_value = {'id': 'e1', 'trackingUrl': 'https://t'}
        with patch.object(ifood_oauth, 'token', return_value='t'), patch('requests.request', return_value=r):
            self.assertEqual(ifood_oauth.api('entregas', 'POST', '/x', corpo={}), {'id': 'e1', 'trackingUrl': 'https://t'})

    def test_202_sem_corpo_devolve_none(self):
        r = mock.Mock(status_code=202, content=b'')
        with patch.object(ifood_oauth, 'token', return_value='t'), patch('requests.request', return_value=r):
            self.assertIsNone(ifood_oauth.api('pedidos', 'POST', '/x'))


@override_settings(IFOOD_CLIENT_ID='app-p', IFOOD_CLIENT_SECRET='s')
class RetryTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _resp(self, status, corpo=b'{}', cab=None):
        r = mock.Mock(status_code=status, content=corpo, text=corpo.decode(), headers=cab or {})
        r.json.return_value = {}
        return r

    def test_5xx_tenta_de_novo_com_backoff(self):
        from apps.stores.services import ifood_oauth
        with mock.patch.object(ifood_oauth, 'token', return_value='t'), \
             mock.patch('requests.request', side_effect=[self._resp(503), self._resp(200)]) as req, \
             mock.patch('time.sleep') as dorme:
            self.assertEqual(ifood_oauth.api('pedidos', 'GET', '/x'), {})
        self.assertEqual(req.call_count, 2)
        dorme.assert_called_once_with(0.5)

    def test_429_respeita_retry_after(self):
        from apps.stores.services import ifood_oauth
        with mock.patch.object(ifood_oauth, 'token', return_value='t'), \
             mock.patch('requests.request', side_effect=[self._resp(429, cab={'Retry-After': '2'}), self._resp(200)]), \
             mock.patch('time.sleep') as dorme:
            ifood_oauth.api('pedidos', 'GET', '/x')
        dorme.assert_called_once_with(2.0)

    def test_desiste_depois_de_3(self):
        from apps.stores.services import ifood_oauth
        with mock.patch.object(ifood_oauth, 'token', return_value='t'), \
             mock.patch('requests.request', return_value=self._resp(500)) as req, mock.patch('time.sleep'):
            with self.assertRaises(ifood_oauth.IfoodRecusou):
                ifood_oauth.api('pedidos', 'GET', '/x')
        self.assertEqual(req.call_count, 3)


class ModoHomologacaoTest(TestCase):
    """Homologação de Merchant/Shipping: o iFood exige o APP DE TESTE nas gravações.

    Com IFOOD_HOMOLOGACAO_CLIENT_ID/SECRET no ambiente, os dois apps usam a
    credencial de teste. Sem elas, nada muda. Tirar do .env depois de aprovado.
    """

    @override_settings(**CREDENCIAIS, IFOOD_HOMOLOGACAO_CLIENT_ID='app-teste',
                       IFOOD_HOMOLOGACAO_CLIENT_SECRET='segredo-t')
    def test_com_credencial_de_teste_os_dois_apps_usam_ela(self):
        self.assertEqual(ifood_oauth.credenciais('pedidos'), ('app-teste', 'segredo-t'))
        self.assertEqual(ifood_oauth.credenciais('entregas'), ('app-teste', 'segredo-t'))
        self.assertTrue(ifood_oauth.esta_configurado('pedidos'))

    @override_settings(**CREDENCIAIS, IFOOD_HOMOLOGACAO_CLIENT_ID='',
                       IFOOD_HOMOLOGACAO_CLIENT_SECRET='')
    def test_sem_credencial_de_teste_cada_app_usa_a_sua(self):
        self.assertEqual(ifood_oauth.credenciais('pedidos'), ('app-pedidos', 'segredo-p'))
        self.assertEqual(ifood_oauth.credenciais('entregas'), ('app-entregas', 'segredo-e'))

    @override_settings(**CREDENCIAIS, IFOOD_HOMOLOGACAO_CLIENT_ID='app-teste',
                       IFOOD_HOMOLOGACAO_CLIENT_SECRET='')
    def test_credencial_de_teste_pela_metade_nao_liga_o_modo(self):
        self.assertEqual(ifood_oauth.credenciais('pedidos'), ('app-pedidos', 'segredo-p'))


@override_settings(**CREDENCIAIS, IFOOD_HOMOLOGACAO_CLIENT_ID='app-teste',
                   IFOOD_HOMOLOGACAO_CLIENT_SECRET='segredo-t')
class HomologacaoSoLojaDeTesteTest(TestCase):
    """Com o app de teste ligado, só a loja de teste fala com o iFood.

    Medido 23/11: o status da Cê Saladas era consultado com a credencial de
    teste e voltava 403 — sujava o log que o iFood usa para validar os vídeos.
    """

    OUTRA = '4ea4f892-62f1-4037-a95f-1a903a55be70'

    def setUp(self):
        cache.clear()

    @staticmethod
    def _resp(status, dados=None):
        r = mock.Mock(status_code=status, headers={}, text='')
        r.content = b'x' if dados is not None else b''
        r.json.return_value = dados
        return r

    def _api(self, respostas):
        return (patch.object(ifood_oauth, 'token', return_value='tok'),
                mock.patch('requests.request', side_effect=respostas))

    def test_merchant_fora_do_app_de_teste_nem_chega_ao_ifood(self):
        lista = self._resp(200, [{'id': MERCHANT, 'name': 'Teste'}])
        tok, req = self._api([lista])
        with tok, req as chamada:
            with self.assertRaises(ifood_oauth.IfoodRecusou) as erro:
                ifood_oauth.api('pedidos', 'GET', f'/merchant/v1.0/merchants/{self.OUTRA}/status')
        self.assertEqual(erro.exception.status, 403)
        urls = [c.args[1] for c in chamada.call_args_list]
        self.assertEqual(urls, [f'{ifood_oauth.BASE}/merchant/v1.0/merchants'])

    def test_loja_de_teste_passa(self):
        lista = self._resp(200, [{'id': MERCHANT}])
        status = self._resp(200, [{'state': 'OK'}])
        tok, req = self._api([lista, status])
        with tok, req:
            dados = ifood_oauth.api('pedidos', 'GET', f'/merchant/v1.0/merchants/{MERCHANT}/status')
        self.assertEqual(dados, [{'state': 'OK'}])

    def test_lista_de_lojas_do_app_fica_em_cache(self):
        lista = self._resp(200, [{'id': MERCHANT}])
        tok, req = self._api([lista, self._resp(204), self._resp(204)])
        with tok, req as chamada:
            ifood_oauth.api('pedidos', 'GET', f'/merchant/v1.0/merchants/{MERCHANT}/status')
            ifood_oauth.api('pedidos', 'GET', f'/merchant/v1.0/merchants/{MERCHANT}/interruptions')
        self.assertEqual(chamada.call_count, 3)

    @override_settings(IFOOD_HOMOLOGACAO_CLIENT_ID='', IFOOD_HOMOLOGACAO_CLIENT_SECRET='')
    def test_fora_da_homologacao_nao_filtra(self):
        tok, req = self._api([self._resp(200, {'id': self.OUTRA})])
        with tok, req as chamada:
            ifood_oauth.api('pedidos', 'GET', f'/merchant/v1.0/merchants/{self.OUTRA}')
        self.assertEqual(chamada.call_count, 1)
