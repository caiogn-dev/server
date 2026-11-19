"""Módulo Merchant do iFood: a loja vista e operada pelo painel do Cardapidex.

Critérios de homologação do Merchant: mostrar o status da loja no iFood,
criar e remover pausas (interruptions) e ler/alterar o horário de
funcionamento (opening-hours).

    GET    /merchant/v1.0/merchants/{m}/status
    GET    /merchant/v1.0/merchants/{m}/interruptions
    POST   /merchant/v1.0/merchants/{m}/interruptions        {description, start, end}
    DELETE /merchant/v1.0/merchants/{m}/interruptions/{id}
    GET    /merchant/v1.0/merchants/{m}/opening-hours
    PUT    /merchant/v1.0/merchants/{m}/opening-hours        {storeId, shifts:[{dayOfWeek, start, duration}]}
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.stores.models import Store
from apps.stores.models.ifood import StoreIfoodIntegration
from apps.stores.services import loja_no_ifood as loja
from apps.stores.services.ifood_oauth import IfoodRecusou

User = get_user_model()
CREDENCIAIS = {'IFOOD_ENTREGAS_CLIENT_ID': 'app-e', 'IFOOD_ENTREGAS_CLIENT_SECRET': 's'}
M = '00f0d5a7-6142-4120-b34d-1b1d36cdecec'
BASE = f'/merchant/v1.0/merchants/{M}'

STATUS = [{
    'operation': 'delivery', 'salesChannel': 'ifood-app', 'available': False, 'state': 'CLOSED',
    'message': {'title': 'Loja fechada', 'subtitle': 'Fora do horário de funcionamento', 'description': ''},
    'validations': [],
}]
PAUSAS = [{'id': 'p-1', 'description': 'Cozinha cheia',
           'start': '2026-11-19T20:00:00Z', 'end': '2026-11-19T20:30:00Z'}]
HORARIOS = {'id': 'oh', 'shifts': [
    {'id': 's1', 'dayOfWeek': 'MONDAY', 'start': '11:00:00', 'duration': 240},
    {'id': 's2', 'dayOfWeek': 'MONDAY', 'start': '18:00:00', 'duration': 300},
]}


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.dono = User.objects.create_user(username='dono-loja-ifood', password='x')
        self.store = Store.objects.create(billing_exempt=True, name='Cê', slug='ce-loja-ifood',
                                          owner=self.dono, store_type='food', status='active')
        StoreIfoodIntegration.objects.create(store=self.store, merchant_id=M, conectado=True)

    def _api(self, respostas=None):
        self.chamadas = []
        respostas = respostas or {}

        def falso(app, metodo, caminho, corpo=None, **kw):
            self.chamadas.append((metodo, caminho, corpo))
            valor = respostas.get((metodo, caminho))
            if isinstance(valor, Exception):
                raise valor
            return valor
        return mock.patch.object(loja.ifood_oauth, 'api', side_effect=falso)


@override_settings(**CREDENCIAIS)
class LeituraTest(Base):
    def test_resume_status_pausas_e_horarios(self):
        with self._api({('GET', f'{BASE}/status'): STATUS, ('GET', f'{BASE}/interruptions'): PAUSAS,
                        ('GET', f'{BASE}/opening-hours'): HORARIOS}):
            d = loja.resumo(self.store)
        self.assertEqual(d['status'], {'estado': 'CLOSED', 'aberta': False, 'titulo': 'Loja fechada',
                                       'detalhe': 'Fora do horário de funcionamento'})
        self.assertEqual(d['pausas'], [{'id': 'p-1', 'motivo': 'Cozinha cheia',
                                        'inicio': '2026-11-19T20:00:00Z', 'fim': '2026-11-19T20:30:00Z'}])
        self.assertEqual(d['horarios'], [
            {'dia': 'MONDAY', 'inicio': '11:00', 'fim': '15:00'},
            {'dia': 'MONDAY', 'inicio': '18:00', 'fim': '23:00'},
        ])

    def test_loja_aberta(self):
        aberta = [dict(STATUS[0], state='OK', available=True, message={'title': 'Loja aberta'})]
        with self._api({('GET', f'{BASE}/status'): aberta}):
            d = loja.resumo(self.store)
        self.assertTrue(d['status']['aberta'])
        self.assertEqual(d['pausas'], [])
        self.assertEqual(d['horarios'], [])

    def test_lista_lojas_que_aprovaram_o_app(self):
        with self._api({('GET', '/merchant/v1.0/merchants'): [
                {'id': M, 'name': 'Teste', 'corporateName': 'L DE SOUZA'}]}):
            self.assertEqual(loja.lojas_do_app(), [{'id': M, 'nome': 'Teste', 'razao_social': 'L DE SOUZA'}])

    def test_loja_sem_id_recusa(self):
        StoreIfoodIntegration.objects.filter(store=self.store).update(merchant_id='')
        with self.assertRaises(loja.LojaNoIfoodErro):
            loja.resumo(self.store)


@override_settings(**CREDENCIAIS)
class OperacoesTest(Base):
    def test_pausar_cria_interrupcao_com_inicio_e_fim(self):
        with self._api():
            loja.pausar(self.store, 30, 'Cozinha cheia')
        metodo, caminho, corpo = self.chamadas[0]
        self.assertEqual((metodo, caminho), ('POST', f'{BASE}/interruptions'))
        self.assertEqual(corpo['description'], 'Cozinha cheia')
        from datetime import datetime
        inicio = datetime.fromisoformat(corpo['start'])
        fim = datetime.fromisoformat(corpo['end'])
        self.assertEqual((fim - inicio).total_seconds(), 30 * 60)
        self.assertIn('id', corpo)

    def test_pausa_fora_do_limite_recusa(self):
        for minutos in (0, -5, 60 * 24 * 8):
            with self.subTest(minutos=minutos), self.assertRaises(loja.LojaNoIfoodErro):
                loja.pausar(self.store, minutos)

    def test_retomar_apaga_a_interrupcao(self):
        with self._api():
            loja.retomar(self.store, 'p-1')
        self.assertEqual(self.chamadas[0][:2], ('DELETE', f'{BASE}/interruptions/p-1'))

    def test_salvar_horarios_converte_para_inicio_e_duracao(self):
        with self._api():
            loja.salvar_horarios(self.store, [
                {'dia': 'MONDAY', 'inicio': '11:00', 'fim': '15:00'},
                {'dia': 'sunday', 'inicio': '18:30', 'fim': '23:59'},
            ])
        metodo, caminho, corpo = self.chamadas[0]
        self.assertEqual((metodo, caminho), ('PUT', f'{BASE}/opening-hours'))
        self.assertEqual(corpo['storeId'], M)
        self.assertEqual(corpo['shifts'], [
            {'dayOfWeek': 'MONDAY', 'start': '11:00:00', 'duration': 240},
            {'dayOfWeek': 'SUNDAY', 'start': '18:30:00', 'duration': 329},
        ])

    def test_horario_invalido_recusa(self):
        for turno in ({'dia': 'MONDAY', 'inicio': '15:00', 'fim': '11:00'},
                      {'dia': 'FUNDAY', 'inicio': '11:00', 'fim': '12:00'},
                      {'dia': 'MONDAY', 'inicio': '25:00', 'fim': '26:00'}):
            with self.subTest(turno=turno), self.assertRaises(loja.LojaNoIfoodErro):
                loja.salvar_horarios(self.store, [turno])

    def test_recusa_do_ifood_vira_erro_legivel(self):
        with self._api({('POST', f'{BASE}/interruptions'): IfoodRecusou('409', 409, '{"message": "sobreposta"}')}):
            with self.assertRaises(loja.LojaNoIfoodErro) as ctx:
                loja.pausar(self.store, 30)
        self.assertIn('sobreposta', str(ctx.exception))


@override_settings(**CREDENCIAIS)
class ViewsTest(Base):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.dono)
        self.url = '/api/v1/stores/integracoes/ifood/loja/'

    def test_get(self):
        with mock.patch.object(loja, 'resumo', return_value={'status': {}, 'pausas': [], 'horarios': []}):
            r = self.client.get(f'{self.url}?store={self.store.slug}')
        self.assertEqual(r.status_code, 200, r.content)

    def test_pausar_e_devolve_o_resumo(self):
        with mock.patch.object(loja, 'pausar') as pausar, \
             mock.patch.object(loja, 'resumo', return_value={'status': {}, 'pausas': [], 'horarios': []}):
            r = self.client.post(f'{self.url}pausar/?store={self.store.slug}', {'minutos': 30}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        pausar.assert_called_once_with(self.store, 30, '')

    def test_horarios(self):
        with mock.patch.object(loja, 'salvar_horarios') as salvar, \
             mock.patch.object(loja, 'resumo', return_value={'status': {}, 'pausas': [], 'horarios': []}):
            r = self.client.put(f'{self.url}horarios/?store={self.store.slug}',
                                {'horarios': [{'dia': 'MONDAY', 'inicio': '11:00', 'fim': '15:00'}]}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        salvar.assert_called_once()

    def test_erro_vira_400(self):
        with mock.patch.object(loja, 'pausar', side_effect=loja.LojaNoIfoodErro('Pausa inválida.')):
            r = self.client.post(f'{self.url}pausar/?store={self.store.slug}', {'minutos': 0}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['detail'], 'Pausa inválida.')

    def test_outro_dono_nao_ve(self):
        c = APIClient()
        c.force_authenticate(User.objects.create_user(username='intruso-loja-ifood', password='x'))
        r = c.get(f'{self.url}?store={self.store.slug}')
        self.assertEqual(r.status_code, 404)
