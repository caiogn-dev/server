"""Faturamento dos pedidos da 99Food (plano 06/11, item 1.4).

Regra do dono:
- faturamento bruto = preço de cardápio (ranking, ticket, comparações);
- desconto pago pela 99 fica à parte e NÃO reduz receita;
- desconto da loja reduz receita;
- comissão e taxas = venda − recebido;
- recebido = o que caiu no extrato de repasse.

Gabarito: extrato da Cê de 06/11 — 6 pedidos, venda 258,76, recebido 158,42.
O pedido #5 (11:19) custou R$ 8,00 ao cliente: venda 39,99, a loja recebeu 17,62.
"""
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.stores import metrics
from apps.stores.models import Store, StoreOrder
from apps.stores.services import pedidos_da_99 as p99
from apps.stores.services import repasse_99
from apps.webhooks.models import WebhookEvent

User = get_user_model()
TZ = ZoneInfo('America/Sao_Paulo')

# (numero, hora, venda em centavos, cliente pagou em centavos, recebido)
GABARITO = [
    (6, (11, 18), 4499, 1500, '29.05'),
    (5, (11, 19), 3999, 800, '17.62'),
    (4, (11, 13), 6189, 4189, '43.91'),
    (3, (11, 12), 3699, 1699, '21.01'),
    (2, (11, 3), 3699, 1699, '21.01'),
    (1, (10, 45), 3791, 2791, '25.82'),
]

EXTRATO = """pedido;data;venda;recebido
#6;06/11/2026 11:18;44,99;29,05
#5;06/11/2026 11:19;39,99;17,62
#4;06/11/2026 11:13;61,89;43,91
#3;06/11/2026 11:12;36,99;21,01
#2;06/11/2026 11:03;36,99;21,01
#1;06/11/2026 10:45;37,91;25,82
"""


def _aviso(order_id, numero, venda, pagou, **preco_extra):
    return {
        'order_id': order_id,
        'order_info': {
            'order_id': order_id, 'order_index': numero,
            'pay_type': 1, 'pay_method': 1, 'delivery_type': 1, 'fulfillment_mode': 0,
            'price': {
                'order_price': venda, 'items_discount': venda - pagou, 'delivery_price': 0,
                'delivery_discount': 0, 'real_pay_price': pagou, **preco_extra,
            },
            'receive_address': {'name': 'Cliente'},
            'order_items': [{'name': 'Salada', 'amount': 1, 'total_price': venda, 'sub_item_list': []}],
        },
    }


@mock.patch.object(p99, 'confirmar_depois')
@mock.patch.object(p99, 'imprimir_depois')
class Base(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-fat-99', password='x')
        self.store = Store.objects.create(name='Cê', slug='ce-saladas', owner=dono, status='active')

    def _receber(self, order_id, numero, venda, pagou, hora=(11, 0), **preco_extra):
        with mock.patch.object(p99, 'confirmar_depois'), mock.patch.object(p99, 'imprimir_depois'):
            pedido, _ = p99.receber_pedido_novo(self.store, _aviso(order_id, numero, venda, pagou, **preco_extra))
        quando = datetime(2026, 11, 6, *hora, tzinfo=TZ)
        StoreOrder.objects.filter(pk=pedido.pk).update(created_at=quando)
        pedido.refresh_from_db()
        return pedido

    def _gabarito(self):
        return [
            self._receber(9000000000000000 + numero, numero, venda, pagou, hora=hora)
            for numero, hora, venda, pagou, _ in GABARITO
        ]

    def _receita(self):
        return metrics.totais(self.store, metrics.de_datas(date(2026, 11, 6), date(2026, 11, 6)))


class PedidoNovoGravaFinanceiroTests(Base):
    def test_pedido_subsidiado_pela_99_fatura_preco_de_cardapio(self, *_):
        pedido = self._receber(5764607801871631353, 5, 3999, 800, hora=(11, 19))

        fin = pedido.metadata['99food']['financeiro']
        self.assertEqual(fin['venda_cardapio'], '39.99')
        self.assertEqual(fin['desconto_total'], '31.99')
        # O aviso não diz quem pagou o desconto: fica vazio, não chutado.
        self.assertIsNone(fin['desconto_plataforma'])
        self.assertIsNone(fin['desconto_loja'])
        self.assertIsNone(fin['comissao_taxas'])
        self.assertIsNone(fin['recebido'])
        self.assertEqual(fin['preco'], {
            'order_price': 3999, 'items_discount': 3199, 'delivery_price': 0,
            'delivery_discount': 0, 'real_pay_price': 800,
        })
        # Caixa e cobrança: o cliente pagou 8,00 — o total não infla.
        self.assertEqual(pedido.total, Decimal('8.00'))
        # Sem dono declarado, o desconto vai como da 99 (o extrato de 06/11
        # confirma: a loja recebeu 17,62 de um pedido que o cliente pagou 8,00).
        self.assertEqual(pedido.platform_discount, Decimal('31.99'))
        self.assertEqual(self._receita()['receita'], Decimal('39.99'))

    def test_desconto_da_loja_reduz_receita_e_o_da_99_nao(self, *_):
        pedido = self._receber(1, 1, 5000, 3000, shop_subsidy_price=500, platform_subsidy_price=1500)

        fin = pedido.metadata['99food']['financeiro']
        self.assertEqual(fin['desconto_loja'], '5.00')
        self.assertEqual(fin['desconto_plataforma'], '15.00')
        self.assertEqual(pedido.platform_discount, Decimal('15.00'))
        self.assertEqual(self._receita()['receita'], Decimal('45.00'))

    def test_so_um_lado_informado_deduz_o_outro(self, *_):
        pedido = self._receber(2, 2, 5000, 3000, shop_subsidy_price=500)

        fin = pedido.metadata['99food']['financeiro']
        self.assertEqual(fin['desconto_loja'], '5.00')
        self.assertEqual(fin['desconto_plataforma'], '15.00')

    def test_recebido_no_aviso_vira_comissao(self, *_):
        pedido = self._receber(3, 3, 3999, 800, shop_income=1762)

        fin = pedido.metadata['99food']['financeiro']
        self.assertEqual(fin['recebido'], '17.62')
        self.assertEqual(fin['comissao_taxas'], '22.37')

    def test_totais_separam_desconto_da_99(self, *_):
        self._receber(4, 4, 5000, 3000, shop_subsidy_price=500, platform_subsidy_price=1500)

        totais = self._receita()
        self.assertEqual(totais['desconto'], Decimal('5.00'))
        self.assertEqual(totais['desconto_plataforma'], Decimal('15.00'))

    def test_pedido_do_site_nao_muda(self, *_):
        StoreOrder.objects.create(
            store=self.store, customer_name='A', customer_phone='1', subtotal=Decimal('50'),
            discount=Decimal('5'), total=Decimal('45'), payment_status='paid', status='confirmed',
        )
        self.assertEqual(metrics.totais(self.store, metrics.hoje())['receita'], Decimal('45.00'))


class ExtratoDeRepasseTests(Base):
    def test_gabarito_06_11_concilia_pedido_a_pedido(self, *_):
        pedidos = self._gabarito()

        resultado = repasse_99.conciliar(self.store, repasse_99.ler_extrato(EXTRATO))

        self.assertEqual(len(resultado['conciliados']), 6)
        self.assertEqual(resultado['sem_pedido'], [])
        self.assertEqual(resultado['divergentes'], [])
        por_numero = {p.metadata['99food']['numero']: p for p in pedidos}
        for numero, _, venda, _, recebido in GABARITO:
            pedido = por_numero[numero]
            pedido.refresh_from_db()
            fin = pedido.metadata['99food']['financeiro']
            self.assertEqual(fin['recebido'], recebido)
            esperado = (Decimal(venda) / 100 - Decimal(recebido)).quantize(Decimal('0.01'))
            self.assertEqual(fin['comissao_taxas'], str(esperado))
            self.assertEqual(fin['fonte_recebido'], 'extrato')

        resumo = repasse_99.resumo_do_periodo(self.store, date(2026, 11, 6), date(2026, 11, 6))
        self.assertEqual(resumo['pedidos'], 6)
        self.assertEqual(resumo['venda'], Decimal('258.76'))
        self.assertEqual(resumo['recebido'], Decimal('158.42'))
        self.assertEqual(resumo['comissao_taxas'], Decimal('100.34'))
        self.assertEqual(resumo['conciliados'], 6)
        # E o faturamento do dia é o de cardápio, igual ao 99store.
        self.assertEqual(self._receita()['receita'], Decimal('258.76'))

    def test_reimportar_nao_muda_nada(self, *_):
        self._gabarito()
        repasse_99.conciliar(self.store, repasse_99.ler_extrato(EXTRATO))
        antes = list(StoreOrder.objects.order_by('pk').values_list('metadata', flat=True))

        resultado = repasse_99.conciliar(self.store, repasse_99.ler_extrato(EXTRATO))

        self.assertEqual(len(resultado['conciliados']), 6)
        self.assertEqual(list(StoreOrder.objects.order_by('pk').values_list('metadata', flat=True)), antes)

    def test_simulacao_nao_grava(self, *_):
        self._gabarito()

        resultado = repasse_99.conciliar(self.store, repasse_99.ler_extrato(EXTRATO), gravar=False)

        self.assertEqual(len(resultado['conciliados']), 6)
        for pedido in StoreOrder.objects.all():
            self.assertIsNone(pedido.metadata['99food']['financeiro']['recebido'])

    def test_linha_sem_pedido_e_venda_divergente_sao_apontadas(self, *_):
        self._receber(11, 1, 3791, 2791, hora=(10, 45))
        extrato = 'pedido;data;venda;recebido\n#1;06/11/2026;40,00;25,82\n#9;06/11/2026;10,00;5,00\n'

        resultado = repasse_99.conciliar(self.store, repasse_99.ler_extrato(extrato))

        self.assertEqual([l.pedido for l in resultado['sem_pedido']], ['9'])
        self.assertEqual(len(resultado['divergentes']), 1)
        # Divergente ainda grava o recebido (é o dinheiro real), mas avisa.
        pedido = StoreOrder.objects.get()
        self.assertEqual(pedido.metadata['99food']['financeiro']['recebido'], '25.82')

    def test_aceita_order_id_longo_e_virgula_como_separador(self, *_):
        self._receber(5764607801871631353, 5, 3999, 800)
        extrato = 'Pedido,Valor da venda,Valor recebido\n5764607801871631353,"R$ 39,99","R$ 17,62"\n'

        resultado = repasse_99.conciliar(self.store, repasse_99.ler_extrato(extrato))

        self.assertEqual(len(resultado['conciliados']), 1)

    def test_numero_sem_data_usa_a_data_informada(self, *_):
        self._receber(12, 1, 3791, 2791, hora=(10, 45))
        extrato = 'pedido;venda;recebido\n1;37,91;25,82\n'

        linhas = repasse_99.ler_extrato(extrato, data_padrao=date(2026, 11, 6))
        resultado = repasse_99.conciliar(self.store, linhas)

        self.assertEqual(len(resultado['conciliados']), 1)

    def test_comando_importa_o_arquivo(self, *_):
        self._gabarito()
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(EXTRATO)
        saida = StringIO()

        call_command('importar_extrato_99', f.name, '--loja', 'ce-saladas', '--dry-run', stdout=saida)
        self.assertIn('6 conciliados', saida.getvalue())
        self.assertIsNone(StoreOrder.objects.first().metadata['99food']['financeiro']['recebido'])

        call_command('importar_extrato_99', f.name, '--loja', 'ce-saladas', stdout=StringIO())
        resumo = repasse_99.resumo_do_periodo(self.store, date(2026, 11, 6), date(2026, 11, 6))
        self.assertEqual(resumo['recebido'], Decimal('158.42'))


class BackfillTests(Base):
    def _pedido_antigo(self, order_id, numero, venda, pagou):
        """Pedido gravado pelo código antigo: sem financeiro, sem platform_discount."""
        pedido = self._receber(order_id, numero, venda, pagou)
        meta = dict(pedido.metadata)
        meta['99food'] = {k: v for k, v in meta['99food'].items() if k != 'financeiro'}
        StoreOrder.objects.filter(pk=pedido.pk).update(metadata=meta, platform_discount=Decimal('0'))
        WebhookEvent.objects.create(
            provider='99food', event_type='orderNew',
            payload={'type': 'orderNew', 'app_shop_id': 'ce-saladas',
                     'data': _aviso(order_id, numero, venda, pagou)},
        )
        return pedido

    def test_dry_run_nao_grava_e_o_resto_e_idempotente(self, *_):
        pedido = self._pedido_antigo(77, 5, 3999, 800)

        call_command('financeiro_dos_pedidos_da_99', '--dry-run', stdout=StringIO())
        pedido.refresh_from_db()
        self.assertNotIn('financeiro', pedido.metadata['99food'])
        self.assertEqual(pedido.platform_discount, Decimal('0'))

        call_command('financeiro_dos_pedidos_da_99', stdout=StringIO())
        pedido.refresh_from_db()
        self.assertEqual(pedido.metadata['99food']['financeiro']['venda_cardapio'], '39.99')
        self.assertEqual(pedido.platform_discount, Decimal('31.99'))

        saida = StringIO()
        call_command('financeiro_dos_pedidos_da_99', stdout=saida)
        self.assertIn('0 atualizados', saida.getvalue())

    def test_backfill_nao_apaga_recebido_do_extrato(self, *_):
        pedido = self._pedido_antigo(5764607801871600078, 5, 3999, 800)
        call_command('financeiro_dos_pedidos_da_99', stdout=StringIO())
        repasse_99.conciliar(self.store, repasse_99.ler_extrato(
            'pedido;venda;recebido\n5764607801871600078;39,99;17,62\n'))

        call_command('financeiro_dos_pedidos_da_99', stdout=StringIO())

        pedido.refresh_from_db()
        self.assertEqual(pedido.metadata['99food']['financeiro']['recebido'], '17.62')


class RelatorioPorCanalTests(APITestCase):
    def test_canal_99_mostra_venda_e_recebido(self):
        dono = User.objects.create_user(username='dono-canal-99', password='x')
        loja = Store.objects.create(name='Cê', slug='ce-canal', owner=dono, status='active', billing_exempt=True)
        with mock.patch.object(p99, 'confirmar_depois'), mock.patch.object(p99, 'imprimir_depois'):
            p99.receber_pedido_novo(loja, _aviso(5764607801871600031, 5, 3999, 800))
        pedido = StoreOrder.objects.get(store=loja)
        repasse_99.conciliar(loja, repasse_99.ler_extrato('pedido;venda;recebido\n5764607801871600031;39,99;17,62\n'))
        self.client.force_authenticate(dono)

        resp = self.client.get('/api/v1/stores/reports/channels/', {'store': loja.slug, 'period': '7d'})

        self.assertEqual(resp.status_code, 200, resp.content)
        linha = {r['channel']: r for r in resp.data['by_source']}['99food']
        self.assertAlmostEqual(float(linha['revenue']), 39.99)
        self.assertAlmostEqual(float(linha['recebido']), 17.62)
        self.assertAlmostEqual(float(linha['desconto_plataforma']), 31.99)
        self.assertAlmostEqual(float(linha['comissao_taxas']), 22.37)
        self.assertEqual(pedido.total, Decimal('8.00'))
