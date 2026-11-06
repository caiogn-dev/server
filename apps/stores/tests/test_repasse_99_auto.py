"""Repasse da 99: conciliação diária pela API financeira + importação pelo painel.

API financeira da 99 (developer-food.99app.com › Food › Financial API, lida em 06/11/2026):
- POST https://openapi.99food.com/v3/auth/authtoken/signIn {retailer, secret} → accessToken (6 h)
- POST https://openapi.99food.com/v3/finance/finance/getShopBillDetail
  Authorization: Bearer <accessToken>; {acceptor_code=app_shop_id, page_no, page_size≤200,
  start_date/end_date YYYYMMDD (máx. 31 dias, até 3 meses atrás)} → lançamentos por pedido;
  `settlementAmount` (centavos) é o que a loja recebe por lançamento.

Gabarito: extrato da Cê de 06/11 — 6 pedidos, venda 258,76, recebido 158,42.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest import mock

from celery.schedules import crontab
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder
from apps.stores.services import pedidos_da_99 as p99
from apps.stores.services import repasse_99, repasse_99_api
from apps.stores.tests.test_financeiro_99 import EXTRATO, GABARITO, Base

User = get_user_model()

# Exatamente como o dono copiou do 99store em 06/11.
TEXTO_COLADO = """#6
06 de nov. 11:18
R$44,99
R$29,05
Concluído
#5
06 de nov. 11:19
R$39,99
R$17,62
Concluído
#4
06 de nov. 11:13
R$61,89
R$43,91
Concluído
#3
06 de nov. 11:12
R$36,99
R$21,01
Concluído
#2
06 de nov. 11:03
R$36,99
R$21,01
Concluído
#1
06 de nov. 10:45
R$37,91
R$25,82
Concluído
"""

CREDENCIAIS = dict(NINETY_NINE_APP_ID='app-teste', NINETY_NINE_APP_SECRET='segredo-teste')


def _resposta(corpo, status=200):
    r = mock.Mock(status_code=status)
    r.json.return_value = corpo
    return r


def _token():
    return _resposta({'accessToken': 'tok-fin', 'expiresIn': 21600})


def _pagina(lancamentos, pagina=1, paginas=1):
    return _resposta({'errno': 0, 'errmsg': 'ok', 'data': {
        'data': lancamentos, 'total_num': len(lancamentos), 'total_page': paginas,
        'page_size': 200, 'page_no': pagina,
    }})


def _lancamento(order_id, numero, venda, recebido, tipo=1, quando='2026-11-06 11:00:00'):
    return {
        'orderId': str(order_id), 'orderIndex': str(numero), 'orderType': tipo,
        'businessDateTime': quando, 'mealOriginalAmount': venda,
        'settlementAmount': recebido, 'expectSettleDate': '2026-11-11',
    }


def _lancamentos_do_gabarito():
    return [
        _lancamento(9000000000000000 + numero, numero, venda, int(Decimal(recebido) * 100))
        for numero, _hora, venda, _pagou, recebido in GABARITO
    ]


# ── Texto colado do 99store ───────────────────────────────────────────────

class TextoColadoTests(Base):
    def test_le_os_blocos_do_99store(self, *_):
        linhas = repasse_99.ler_texto_colado(TEXTO_COLADO, ano=2026)
        self.assertEqual([l.pedido for l in linhas], ['6', '5', '4', '3', '2', '1'])
        self.assertEqual(linhas[0].data, date(2026, 11, 6))
        self.assertEqual(linhas[0].venda, Decimal('44.99'))
        self.assertEqual(linhas[0].recebido, Decimal('29.05'))
        self.assertEqual(sum(l.recebido for l in linhas), Decimal('158.42'))
        self.assertEqual(sum(l.venda for l in linhas), Decimal('258.76'))

    def test_ler_qualquer_reconhece_colado_e_csv(self, *_):
        self.assertEqual(len(repasse_99.ler_qualquer(TEXTO_COLADO, hoje=date(2026, 11, 7))), 6)
        self.assertEqual(len(repasse_99.ler_qualquer(EXTRATO)), 6)

    def test_colado_de_dezembro_lido_em_janeiro_e_do_ano_anterior(self, *_):
        linhas = repasse_99.ler_qualquer('#1\n30 de dez. 20:00\nR$10,00\nR$7,00\nConcluído\n',
                                         hoje=date(2027, 1, 2))
        self.assertEqual(linhas[0].data, date(2026, 12, 30))

    def test_colado_concilia_o_gabarito(self, *_):
        self._gabarito()
        linhas = repasse_99.ler_qualquer(TEXTO_COLADO, hoje=date(2026, 11, 7))
        resultado = repasse_99.conciliar(self.store, linhas)
        self.assertEqual(len(resultado['conciliados']), 6)
        resumo = repasse_99.resumo_do_periodo(self.store, date(2026, 11, 6), date(2026, 11, 6))
        self.assertEqual(resumo['recebido'], Decimal('158.42'))


# ── Cliente da API financeira ─────────────────────────────────────────────

@override_settings(**CREDENCIAIS)
class ApiFinanceiraTests(Base):
    def setUp(self):
        super().setUp()
        cache.clear()

    @mock.patch.object(repasse_99_api.requests, 'post')
    def test_token_sai_do_signin_e_fica_guardado(self, post, *_):
        post.return_value = _token()
        self.assertEqual(repasse_99_api.token_financeiro(), 'tok-fin')
        self.assertEqual(repasse_99_api.token_financeiro(), 'tok-fin')
        self.assertEqual(post.call_count, 1)
        url = post.call_args.args[0]
        self.assertEqual(url, 'https://openapi.99food.com/v3/auth/authtoken/signIn')
        self.assertEqual(post.call_args.kwargs['json'], {'retailer': 'app-teste', 'secret': 'segredo-teste'})

    @mock.patch.object(repasse_99_api.requests, 'post')
    def test_lancamentos_pagina_e_manda_loja_e_datas(self, post, *_):
        post.side_effect = [
            _token(),
            _pagina([_lancamento(1, 1, 100, 70)], pagina=1, paginas=2),
            _pagina([_lancamento(2, 2, 100, 60)], pagina=2, paginas=2),
        ]
        itens = repasse_99_api.lancamentos(self.store, date(2026, 10, 31), date(2026, 11, 6))
        self.assertEqual([i['orderId'] for i in itens], ['1', '2'])
        chamada = post.call_args_list[1]
        self.assertEqual(chamada.args[0], 'https://openapi.99food.com/v3/finance/finance/getShopBillDetail')
        self.assertEqual(chamada.kwargs['headers']['Authorization'], 'Bearer tok-fin')
        self.assertEqual(chamada.kwargs['json'], {
            'acceptor_code': 'ce-saladas', 'page_no': 1, 'page_size': 200,
            'start_date': '20261031', 'end_date': '20261106',
        })
        self.assertEqual(post.call_args_list[2].kwargs['json']['page_no'], 2)

    @mock.patch.object(repasse_99_api.requests, 'post')
    def test_errno_da_99_vira_erro(self, post, *_):
        post.side_effect = [_token(), _resposta({'errno': 110005, 'errmsg': 'max 31 days'})]
        with self.assertRaises(p99.ErroDa99):
            repasse_99_api.lancamentos(self.store, date(2026, 10, 1), date(2026, 11, 6))

    @mock.patch.object(repasse_99_api.requests, 'post')
    def test_token_recusado_renova_uma_vez(self, post, *_):
        post.side_effect = [
            _token(), _resposta({'errno': 401, 'errmsg': 'unauthorized'}, status=401),
            _token(), _pagina([]),
        ]
        self.assertEqual(repasse_99_api.lancamentos(self.store, date(2026, 11, 6), date(2026, 11, 6)), [])
        self.assertEqual(post.call_count, 4)

    def test_lancamentos_viram_linhas_por_pedido(self, *_):
        linhas = repasse_99_api.linhas_dos_lancamentos([
            _lancamento(111, 1, 3791, 2582),
            _lancamento(111, 1, 0, -700, tipo=4),          # estorno pós-venda do mesmo pedido
            _lancamento(222, 2, 3699, 2101),
            {'orderId': '999', 'orderType': 5, 'settlementAmount': -5000},  # anúncio: não é pedido
            _lancamento(333, 3, 0, -300, tipo=4),          # ajuste de pedido de fora da janela
        ])
        por_pedido = {l.pedido: l for l in linhas}
        self.assertEqual(set(por_pedido), {'111', '222'})
        self.assertEqual(por_pedido['111'].recebido, Decimal('18.82'))
        self.assertEqual(por_pedido['111'].venda, Decimal('37.91'))
        self.assertEqual(por_pedido['111'].data, date(2026, 11, 6))


@override_settings(**CREDENCIAIS)
class ConciliacaoDiariaTests(Base):
    def setUp(self):
        super().setUp()
        cache.clear()

    @mock.patch.object(repasse_99_api.requests, 'post')
    def test_dia_anterior_concilia_o_gabarito_e_e_idempotente(self, post, *_):
        self._gabarito()
        post.side_effect = lambda url, **kw: _token() if 'signIn' in url else _pagina(_lancamentos_do_gabarito())

        resultado = repasse_99_api.conciliar_pela_api(self.store, date(2026, 11, 6))
        self.assertEqual(len(resultado['conciliados']), 6)
        pedido = StoreOrder.objects.get(store=self.store, metadata__99food__numero=6)
        fin = pedido.metadata['99food']['financeiro']
        self.assertEqual(fin['recebido'], '29.05')
        self.assertEqual(fin['fonte_recebido'], 'api')
        resumo = repasse_99.resumo_do_periodo(self.store, date(2026, 11, 6), date(2026, 11, 6))
        self.assertEqual(resumo['recebido'], Decimal('158.42'))
        self.assertEqual(resumo['venda'], Decimal('258.76'))

        antes = pedido.updated_at
        repasse_99_api.conciliar_pela_api(self.store, date(2026, 11, 6))
        pedido.refresh_from_db()
        self.assertEqual(pedido.updated_at, antes)

    @mock.patch.object(repasse_99_api.requests, 'post')
    def test_janela_e_de_7_dias_ate_ontem(self, post, *_):
        post.side_effect = lambda url, **kw: _token() if 'signIn' in url else _pagina([])
        repasse_99_api.conciliar_pela_api(self.store, date(2026, 11, 6))
        corpo = post.call_args_list[-1].kwargs['json']
        self.assertEqual((corpo['start_date'], corpo['end_date']), ('20261031', '20261106'))


@override_settings(**CREDENCIAIS)
class TarefaDiariaTests(Base):
    def test_roda_so_para_loja_com_pedido_da_99_e_uma_falha_nao_trava_as_outras(self, *_):
        from apps.stores import tasks
        self._gabarito()
        dono = User.objects.create_user(username='dono-outra-99', password='x')
        outra = Store.objects.create(name='Outra', slug='outra-99', owner=dono, status='active')
        with mock.patch.object(p99, 'confirmar_depois'), mock.patch.object(p99, 'imprimir_depois'):
            p99.receber_pedido_novo(outra, {'order_id': 777, 'order_info': {
                'order_id': 777, 'order_index': 1, 'delivery_type': 1,
                'price': {'order_price': 1000, 'real_pay_price': 1000},
                'receive_address': {'name': 'X'}, 'order_items': []}})
        StoreOrder.objects.filter(store=outra).update(created_at=StoreOrder.objects.filter(
            store=self.store).first().created_at)
        Store.objects.create(name='Sem 99', slug='sem-99', owner=dono, status='active')

        vistas = []

        def falso(loja, dia):
            vistas.append(loja.slug)
            if loja.slug == 'outra-99':
                raise p99.ErroDa99('fora do ar')
            return {'conciliados': [], 'sem_pedido': [], 'divergentes': []}

        with mock.patch.object(repasse_99_api, 'conciliar_pela_api', side_effect=falso):
            resumo = tasks.conciliar_repasse_da_99(dia='2026-11-06')
        self.assertEqual(sorted(vistas), ['ce-saladas', 'outra-99'])
        self.assertEqual(resumo['ce-saladas'], 0)
        self.assertIn('erro', resumo['outra-99'])

    def test_sem_credenciais_nao_faz_nada(self, *_):
        from apps.stores import tasks
        self._gabarito()
        with override_settings(NINETY_NINE_APP_ID='', NINETY_NINE_APP_SECRET=''), \
                mock.patch.object(repasse_99_api, 'conciliar_pela_api') as conciliar:
            self.assertEqual(tasks.conciliar_repasse_da_99(dia='2026-11-06'), {})
        conciliar.assert_not_called()


def test_beat_agenda_conciliacao_as_6h():
    from config.celery import app
    entrada = app.conf.beat_schedule['conciliar-repasse-da-99']
    assert entrada['task'] == 'apps.stores.tasks.conciliar_repasse_da_99'
    assert entrada['schedule'] == crontab(hour=6, minute=0)


# ── Importação pelo painel ────────────────────────────────────────────────

URL = '/api/v1/stores/reports/99food/extrato/'


@mock.patch.object(p99, 'confirmar_depois')
@mock.patch.object(p99, 'imprimir_depois')
class ImportarExtratoApiTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-imp-99', password='x')
        self.store = Store.objects.create(name='Cê', slug='ce-saladas', owner=self.dono, status='active')
        for numero, hora, venda, pagou, _ in GABARITO:
            Base._receber(self, 9000000000000000 + numero, numero, venda, pagou, hora=hora)
        self.client.force_authenticate(self.dono)

    def test_previa_nao_grava(self, *_):
        resp = self.client.post(f'{URL}?store=ce-saladas', {'texto': TEXTO_COLADO, 'data': '2026-11-06'},
                                format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['conciliados'], 6)
        self.assertEqual(resp.data['sem_pedido'], 0)
        self.assertEqual(resp.data['divergentes'], 0)
        self.assertEqual(resp.data['venda'], '258.76')
        self.assertEqual(resp.data['recebido'], '158.42')
        self.assertFalse(resp.data['gravado'])
        self.assertEqual(len(resp.data['linhas']), 6)
        self.assertEqual(resp.data['linhas'][0]['situacao'], 'conciliado')
        self.assertFalse(StoreOrder.objects.filter(metadata__99food__financeiro__fonte_recebido='extrato').exists())

    def test_gravar_concilia(self, *_):
        resp = self.client.post(f'{URL}?store=ce-saladas', {'texto': EXTRATO, 'gravar': True}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.data['gravado'])
        resumo = repasse_99.resumo_do_periodo(self.store, date(2026, 11, 6), date(2026, 11, 6))
        self.assertEqual(resumo['recebido'], Decimal('158.42'))

    def test_arquivo_csv(self, *_):
        arquivo = SimpleUploadedFile('extrato.csv', EXTRATO.encode('utf-8'), content_type='text/csv')
        resp = self.client.post(f'{URL}?store=ce-saladas', {'arquivo': arquivo}, format='multipart')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['conciliados'], 6)

    def test_arquivo_xlsx(self, *_):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['Pedido', 'Data', 'Venda', 'Recebido'])
        for numero, hora, venda, _pagou, recebido in GABARITO:
            ws.append([f'#{numero}', f'06/11/2026 {hora[0]:02d}:{hora[1]:02d}', venda / 100, float(recebido)])
        buf = BytesIO()
        wb.save(buf)
        arquivo = SimpleUploadedFile('extrato.xlsx', buf.getvalue(),
                                     content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post(f'{URL}?store=ce-saladas', {'arquivo': arquivo}, format='multipart')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['recebido'], '158.42')

    def test_sem_pedido_e_divergente_aparecem(self, *_):
        texto = 'pedido;data;venda;recebido\n#1;06/11/2026;40,00;25,82\n#9;06/11/2026;10,00;5,00\n'
        resp = self.client.post(f'{URL}?store=ce-saladas', {'texto': texto}, format='json')
        self.assertEqual((resp.data['conciliados'], resp.data['sem_pedido'], resp.data['divergentes']), (1, 1, 1))
        situacoes = {l['pedido']: l['situacao'] for l in resp.data['linhas']}
        self.assertEqual(situacoes, {'1': 'divergente', '9': 'sem_pedido'})

    def test_texto_ilegivel_e_400(self, *_):
        resp = self.client.post(f'{URL}?store=ce-saladas', {'texto': 'oi tudo bem'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_loja_de_outro_dono_e_404(self, *_):
        intruso = User.objects.create_user(username='intruso-99', password='x')
        self.client.force_authenticate(intruso)
        resp = self.client.post(f'{URL}?store=ce-saladas', {'texto': EXTRATO, 'gravar': True}, format='json')
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(StoreOrder.objects.filter(metadata__99food__financeiro__fonte_recebido='extrato').exists())

    def test_sem_login_e_401(self, *_):
        self.client.force_authenticate(None)
        resp = self.client.post(f'{URL}?store=ce-saladas', {'texto': EXTRATO}, format='json')
        self.assertEqual(resp.status_code, 401)
