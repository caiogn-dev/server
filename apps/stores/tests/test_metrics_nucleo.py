"""Contrato do núcleo de métricas.

Cobre as invariáveis que os bugs de 05-06/ago violaram:
- janela sempre no fuso da loja (o dia não pode virar às 21h);
- cancelado, não pago e pedido de teste ficam fora da receita;
- filtro e agrupamento usam o MESMO eixo de data;
- contagem operacional é outra coisa e inclui o cancelado.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores import metrics
from apps.stores.models import Store, StoreOrder

User = get_user_model()
SP = ZoneInfo('America/Sao_Paulo')


class JanelasTests(TestCase):
    def test_inicio_do_dia_e_meia_noite_local_nao_utc(self):
        # 22:00 de Brasília = 01:00 UTC do dia seguinte. `now().replace(hour=0)`
        # daria 00:00 UTC = 21:00 local de ONTEM.
        instante = datetime(2026, 8, 6, 22, 0, tzinfo=SP)
        with timezone.override(SP):
            with patch('django.utils.timezone.now', return_value=instante):
                inicio = metrics.inicio_do_dia()
        local = timezone.localtime(inicio, SP)
        self.assertEqual(local.date(), date(2026, 8, 6))
        self.assertEqual(local.hour, 0)

    def test_hoje_as_22h_ainda_e_hoje(self):
        instante = datetime(2026, 8, 6, 22, 0, tzinfo=SP)
        with timezone.override(SP):
            with patch('django.utils.timezone.now', return_value=instante):
                janela = metrics.hoje()
        self.assertEqual(janela.inicio, date(2026, 8, 6))
        self.assertEqual(janela.fim, date(2026, 8, 6))

    def test_ultimos_7_dias_cobre_7_dias_e_nao_8(self):
        janela = metrics.ultimos_dias(7)
        self.assertEqual(janela.dias, 7)
        self.assertEqual(janela.fim, metrics.hoje_local())

    def test_janela_anterior_tem_o_mesmo_tamanho_e_nao_encosta(self):
        atual = metrics.ultimos_dias(7)
        anterior = metrics.janela_anterior(atual)
        self.assertEqual(anterior.dias, atual.dias)
        self.assertEqual(anterior.fim, atual.inicio - timedelta(days=1))

    def test_de_datas_inverte_quando_vem_trocado(self):
        janela = metrics.de_datas(date(2026, 8, 10), date(2026, 8, 1))
        self.assertEqual(janela.inicio, date(2026, 8, 1))
        self.assertEqual(janela.fim, date(2026, 8, 10))

    def test_janela_de_zero_dias_e_erro(self):
        with self.assertRaises(ValueError):
            metrics.ultimos_dias(0)


class ReceitaTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-nucleo', password='x', email='dono-nucleo@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Nucleo', slug='loja-nucleo', owner=self.owner, status='active',
        )
        self.hoje = metrics.hoje_local()

    def _pedido(self, total, *, dia=None, status=None, payment_status=None, metadata=None):
        quando = timezone.make_aware(
            datetime.combine(dia or self.hoje, datetime.min.time().replace(hour=12)),
            timezone.get_current_timezone(),
        )
        pedido = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='5563900000000',
            customer_email='c-nucleo@real.com',
            subtotal=Decimal(total), total=Decimal(total),
            status=status or StoreOrder.OrderStatus.DELIVERED,
            payment_status=payment_status or StoreOrder.PaymentStatus.PAID,
            metadata=metadata or {},
        )
        StoreOrder.objects.filter(pk=pedido.pk).update(created_at=quando, paid_at=quando)
        return pedido

    def test_venda_paga_conta(self):
        self._pedido('100.00')
        self.assertEqual(
            metrics.totais(self.store, metrics.hoje())['receita'], Decimal('100.00'),
        )

    def test_cancelado_mesmo_pago_nao_conta(self):
        self._pedido('100.00')
        self._pedido('999.00', status=StoreOrder.OrderStatus.CANCELLED)
        self.assertEqual(
            metrics.totais(self.store, metrics.hoje())['receita'], Decimal('100.00'),
        )

    def test_nao_pago_nao_conta(self):
        self._pedido('100.00')
        self._pedido(
            '555.00',
            status=StoreOrder.OrderStatus.CONFIRMED,
            payment_status=StoreOrder.PaymentStatus.PENDING,
        )
        self.assertEqual(
            metrics.totais(self.store, metrics.hoje())['receita'], Decimal('100.00'),
        )

    def test_pedido_de_teste_nao_conta(self):
        self._pedido('100.00')
        self._pedido('42.00', metadata={'is_test': True})
        self.assertEqual(
            metrics.totais(self.store, metrics.hoje())['receita'], Decimal('100.00'),
        )

    def test_pedido_sem_a_chave_is_test_continua_contando(self):
        """`exclude(metadata__is_test=True)` cru sumia com o faturamento inteiro:
        o lookup vira NULL e `NOT NULL` é NULL em SQL."""
        self._pedido('100.00', metadata={'origem': 'site'})
        self.assertEqual(
            metrics.totais(self.store, metrics.hoje())['receita'], Decimal('100.00'),
        )

    def test_venda_de_ontem_fica_em_ontem(self):
        self._pedido('100.00')
        self._pedido('70.00', dia=self.hoje - timedelta(days=1))
        self.assertEqual(
            metrics.totais(self.store, metrics.hoje())['receita'], Decimal('100.00'),
        )
        self.assertEqual(
            metrics.totais(self.store, metrics.ontem())['receita'], Decimal('70.00'),
        )

    def test_contagem_operacional_inclui_o_cancelado(self):
        """A cozinha precisa ver o pedido que existiu — receita não."""
        self._pedido('100.00')
        self._pedido('999.00', status=StoreOrder.OrderStatus.CANCELLED)
        op = metrics.contagem_operacional(self.store, metrics.hoje())
        self.assertEqual(op['pedidos'], 2)
        self.assertEqual(metrics.totais(self.store, metrics.hoje())['pedidos'], 1)


class SerieTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-serie', password='x', email='dono-serie@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Serie', slug='loja-serie', owner=self.owner, status='active',
        )
        self.hoje = metrics.hoje_local()

    def _pedido(self, total, dia):
        quando = timezone.make_aware(
            datetime.combine(dia, datetime.min.time().replace(hour=12)),
            timezone.get_current_timezone(),
        )
        p = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='5563900000001',
            customer_email='c-serie@real.com',
            subtotal=Decimal(total), total=Decimal(total),
            status=StoreOrder.OrderStatus.DELIVERED,
            payment_status=StoreOrder.PaymentStatus.PAID,
        )
        StoreOrder.objects.filter(pk=p.pk).update(created_at=quando, paid_at=quando)
        return p

    def test_serie_soma_igual_ao_total(self):
        self._pedido('10.00', self.hoje)
        self._pedido('20.00', self.hoje - timedelta(days=1))
        self._pedido('30.00', self.hoje - timedelta(days=2))
        janela = metrics.ultimos_dias(7)
        serie = metrics.serie_temporal(self.store, janela)
        self.assertEqual(
            sum(p['receita'] for p in serie),
            metrics.totais(self.store, janela)['receita'],
        )

    def test_serie_completa_preenche_dia_sem_venda_com_zero(self):
        self._pedido('10.00', self.hoje)
        serie = metrics.serie_completa(self.store, metrics.ultimos_dias(5))
        self.assertEqual(len(serie), 5, 'dias sem venda sumiram do gráfico')
        self.assertEqual(sum(p['receita'] for p in serie), Decimal('10.00'))

    def test_granularidade_invalida_falha_alto(self):
        with self.assertRaises(ValueError):
            metrics.serie_temporal(self.store, metrics.hoje(), granularidade='decada')

    def test_comparativo_sem_periodo_anterior_nao_divide_por_zero(self):
        self._pedido('10.00', self.hoje)
        cmp = metrics.comparar_periodo(self.store, metrics.hoje())
        self.assertIsNone(
            cmp['variacao_pct'],
            'período anterior zerado tem que devolver None, não infinito',
        )
