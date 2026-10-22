"""API do layout da comanda (painel → Impressoras → Layout da comanda).

GET/PUT do layout, prévia em linhas e "imprimir teste". Só dono/equipe da
loja; outra loja recebe 403. Heartbeat devolve `atualizacao` (auto-update).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePrintAgent, StorePrintJob
from apps.stores.services import comanda_linhas as cl

User = get_user_model()


class Base(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-cmdapi', email='dono-cmdapi@t.local', password='x')
        self.loja = Store.objects.create(name='Loja Cmd', slug='loja-cmdapi', owner=self.dono, status='active')
        self.client.force_authenticate(self.dono)
        self.url = '/api/v1/stores/loja-cmdapi/comanda/'

    def _pedido(self, numero='CE-2610225590', **kw):
        return StoreOrder.objects.create(
            store=self.loja, order_number=numero, customer_name='Ana', customer_phone='63999990000',
            subtotal=Decimal('30.00'), total=Decimal('30.00'), **kw)


class LayoutTests(Base):
    def test_get_sem_nada_salvo_devolve_o_padrao(self):
        resp = self.client.get(self.url + 'layout/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), cl.layout_padrao())

    def test_put_valida_salva_e_devolve(self):
        layout = cl.layout_padrao()
        layout['colunas'] = 32
        layout['blocos'] = list(reversed(layout['blocos']))
        resp = self.client.put(self.url + 'layout/', layout, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['colunas'], 32)
        self.assertEqual(resp.json()['blocos'][0]['id'], 'codigo_barras')
        self.loja.refresh_from_db()
        self.assertEqual(self.loja.metadata['comanda']['colunas'], 32)
        self.assertEqual(self.client.get(self.url + 'layout/').json()['colunas'], 32)

    def test_put_invalido_e_400(self):
        resp = self.client.put(self.url + 'layout/', {**cl.layout_padrao(), 'vias': 9}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_put_nao_apaga_o_resto_do_metadata(self):
        self.loja.metadata = {'etiquetas_layouts': {'x': 1}}
        self.loja.save(update_fields=['metadata'])
        self.client.put(self.url + 'layout/', cl.layout_padrao(), format='json')
        self.loja.refresh_from_db()
        self.assertEqual(self.loja.metadata['etiquetas_layouts'], {'x': 1})

    def test_outra_loja_e_403(self):
        intruso = User.objects.create_user(username='intruso', email='intruso@t.local', password='x')
        Store.objects.create(name='Outra', slug='outra-cmdapi', owner=intruso, status='active')
        self.client.force_authenticate(intruso)
        self.assertEqual(self.client.get(self.url + 'layout/').status_code, 403)
        self.assertEqual(self.client.put(self.url + 'layout/', cl.layout_padrao(), format='json').status_code, 403)
        self.assertEqual(self.client.post(self.url + 'previa/', {}, format='json').status_code, 403)
        self.assertEqual(self.client.post(self.url + 'imprimir-teste/', {}, format='json').status_code, 403)

    def test_anonimo_nao_entra(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url + 'layout/').status_code, (401, 403))


class PreviaTests(Base):
    def test_sem_pedido_usa_o_exemplo(self):
        resp = self.client.post(self.url + 'previa/', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        dado = resp.json()
        self.assertEqual(dado['colunas'], 48)
        self.assertEqual(dado['pedido'], cl.pedido_de_exemplo()['order']['order_number'])
        self.assertTrue(dado['linhas'])
        self.assertEqual(set(dado['linhas'][0]), {'texto', 'alinhar', 'negrito', 'altura_dupla',
                                                  'largura_dupla', 'invertido', 'tipo'})

    def test_usa_o_ultimo_pedido_da_loja(self):
        self._pedido('CE-1')
        self._pedido('CE-2')
        resp = self.client.post(self.url + 'previa/', {}, format='json')
        self.assertEqual(resp.json()['pedido'], 'CE-2')

    def test_pedido_escolhido_e_layout_nao_salvo(self):
        p = self._pedido('CE-ESCOLHIDO')
        self._pedido('CE-DEPOIS')
        resp = self.client.post(self.url + 'previa/', {'pedido_id': str(p.id), 'layout': {**cl.layout_padrao(), 'colunas': 32}}, format='json')
        self.assertEqual(resp.json()['pedido'], 'CE-ESCOLHIDO')
        self.assertEqual(resp.json()['colunas'], 32)

    def test_pedido_de_outra_loja_nao_vaza(self):
        outro_dono = User.objects.create_user(username='od', email='od@t.local', password='x')
        outra = Store.objects.create(name='Outra', slug='outra2-cmdapi', owner=outro_dono, status='active')
        alheio = StoreOrder.objects.create(store=outra, order_number='OUT-1', subtotal=1, total=1)
        resp = self.client.post(self.url + 'previa/', {'pedido_id': str(alheio.id)}, format='json')
        self.assertEqual(resp.status_code, 404)


class ImprimirTesteTests(Base):
    def test_cria_job_com_o_ultimo_pedido_sem_dedupe(self):
        p = self._pedido()
        r1 = self.client.post(self.url + 'imprimir-teste/', {}, format='json')
        r2 = self.client.post(self.url + 'imprimir-teste/', {}, format='json')
        self.assertEqual(r1.status_code, 201, r1.content)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])
        job = StorePrintJob.objects.get(pk=r1.json()['id'])
        self.assertEqual(job.order_id, p.id)
        self.assertEqual(job.source, StorePrintJob.Source.TEST)
        self.assertTrue(job.payload.get('escpos_b64'))

    def test_layout_enviado_vale_no_teste(self):
        self._pedido()
        resp = self.client.post(self.url + 'imprimir-teste/', {'layout': {**cl.layout_padrao(), 'vias': 2}}, format='json')
        import base64
        dados = base64.b64decode(StorePrintJob.objects.get(pk=resp.json()['id']).payload['escpos_b64'])
        self.assertEqual(dados.count(bytes([0x1B, 0x40])), 2)

    def test_sem_pedido_imprime_o_exemplo(self):
        resp = self.client.post(self.url + 'imprimir-teste/', {}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        job = StorePrintJob.objects.get(pk=resp.json()['id'])
        self.assertIsNone(job.order_id)
        self.assertTrue(job.payload.get('escpos_b64'))


class HeartbeatAtualizacaoTests(APITestCase):
    def _bate(self):
        dono = User.objects.create_user(username='dono-hbu', email='dono-hbu@t.local', password='x')
        loja = Store.objects.create(name='L', slug='loja-hbu', owner=dono, status='active')
        raw, prefix, hashed = StorePrintAgent.generate_api_key()
        StorePrintAgent.objects.create(store=loja, name='Caixa', slug='caixa-hbu', api_key_prefix=prefix, api_key_hash=hashed)
        return self.client.post('/api/v1/stores/print/agent/heartbeat/', {'app_version': '0.5.0'},
                                format='json', HTTP_X_PRINT_AGENT_KEY=raw)

    @override_settings(PRINT_AGENT_UPDATE_VERSION='', PRINT_AGENT_UPDATE_URL='', PRINT_AGENT_UPDATE_SHA256='')
    def test_sem_configuracao_e_null(self):
        resp = self._bate()
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['atualizacao'])

    @override_settings(PRINT_AGENT_UPDATE_VERSION='0.6.0', PRINT_AGENT_UPDATE_URL='https://x/agent.zip',
                       PRINT_AGENT_UPDATE_SHA256='ab' * 32)
    def test_com_configuracao_devolve_versao_url_e_sha(self):
        self.assertEqual(self._bate().json()['atualizacao'],
                         {'versao': '0.6.0', 'url_zip': 'https://x/agent.zip', 'sha256': 'ab' * 32})
