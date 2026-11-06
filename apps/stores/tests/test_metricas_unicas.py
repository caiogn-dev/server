"""Mesma métrica, mesmo número — em todas as telas (Fase 2, 06/11/2026).

Cada classe monta UM cenário sintético que fazia as telas divergirem e
confere que todos os endpoints que mostram aquele número agora concordam
(e concordam com a definição de `apps/stores/metrics/indicadores.py`).
"""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.stores import metrics
from apps.stores.metrics import indicadores
from apps.stores.models import (
    Store, StoreCustomer, StoreOrder, StoreOrderItem, StoreProduct,
)

User = get_user_model()
SP = ZoneInfo('America/Sao_Paulo')


class Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-mu', password='x', email='dono-mu@real.com')
        self.store = Store.objects.create(
            name='Loja MU', slug='loja-mu', owner=self.owner, status='active', billing_exempt=True,
        )
        self.agora = timezone.localtime()
        self.hoje = self.agora.date()

    def pedido(self, total='50.00', *, frete='0', quando=None, tel='5563999000001', email='',
               status='delivered', pago=True, teste=False, **extra):
        p = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone=tel, customer_email=email,
            subtotal=Decimal(total), total=Decimal(total), delivery_fee=Decimal(frete),
            status=status, payment_status='paid' if pago else 'pending',
            metadata={'is_test': True} if teste else {}, **extra,
        )
        quando = quando or self.agora.replace(hour=12, minute=0, second=0, microsecond=0)
        StoreOrder.objects.filter(pk=p.pk).update(created_at=quando, paid_at=quando)
        p.refresh_from_db()
        return p

    def chamar(self, view, path_params=None, **params):
        rf = APIRequestFactory(SERVER_NAME='localhost')
        req = rf.get('/x', {'store': self.store.slug, **params})
        force_authenticate(req, user=self.owner)
        resp = view(req, **(path_params or {}))
        assert resp.status_code == 200, getattr(resp, 'data', resp)
        return resp.data


# ── Receita total ─────────────────────────────────────────────────────────

class ReceitaTotalTests(Base):
    """Clientes somava `total_spent` gravado no cadastro; Pagamentos/loja, o núcleo."""

    def test_clientes_pagamentos_e_loja_dao_a_mesma_receita(self):
        cad = StoreCustomer.objects.create(
            store=self.store, phone='5563999000001',
            user=User.objects.create_user(username='cli-rt', password='x'),
        )
        self.pedido('100.00', frete='10.00')             # conta 90
        self.pedido('40.00')                             # conta 40
        self.pedido('70.00', status='cancelled')         # não conta
        self.pedido('30.00', teste=True)                 # não conta
        self.pedido('25.00', pago=False)                 # não conta
        # Cadastro com total_spent velho/inflado (fusão de cadastros somou dois lados).
        StoreCustomer.objects.filter(pk=cad.pk).update(total_spent=Decimal('999.00'))

        from apps.stores.api.views.order_views import StoreCustomerViewSet, StoreOrderViewSet
        from apps.stores.api.views.store_views import StoreViewSet

        clientes = Decimal(self.chamar(StoreCustomerViewSet.as_view({'get': 'stats'}))['total_revenue'])
        pagamentos = Decimal(str(self.chamar(StoreOrderViewSet.as_view({'get': 'stats'}))['revenue']['total']))
        loja = Decimal(str(self.chamar(
            StoreViewSet.as_view({'get': 'stats'}), path_params={'pk': str(self.store.pk)},
        )['revenue']['total']))
        definicao = indicadores.receita_pedidos(StoreOrder.objects.filter(store=self.store))

        assert definicao == Decimal('130.00')
        assert clientes == pagamentos == loja == definicao


# ── Clientes novos ────────────────────────────────────────────────────────

class ClientesNovosTests(Base):
    """Visão geral contava cadastro criado; Relatórios › Clientes, quem comprou 1x no período."""

    def test_visao_geral_relatorio_de_clientes_e_saladas_concordam(self):
        dentro = self.agora - timedelta(days=5)
        # A: cliente antigo (1ª compra há 60 dias) que comprou 1x no período → NÃO é novo.
        self.pedido(tel='5563900000001', quando=self.agora - timedelta(days=60))
        self.pedido(tel='5563900000001', quando=dentro)
        # B: 1ª compra no período, comprou 2x → é novo.
        self.pedido(tel='5563900000002', quando=dentro)
        self.pedido(tel='5563900000002', quando=dentro + timedelta(days=1))
        # C: cadastro novo sem compra → NÃO é novo.
        StoreCustomer.objects.create(
            store=self.store, phone='5563900000003',
            user=User.objects.create_user(username='cli-cn', password='x'),
        )
        # D: 1ª compra no período → é novo.
        self.pedido(tel='5563900000004', quando=dentro)
        # E: só pedido cancelado no período → NÃO é novo.
        self.pedido(tel='5563900000005', quando=dentro, status='cancelled')

        inicio, fim = self.hoje - timedelta(days=29), self.hoje
        periodo = {'start_date': inicio.isoformat(), 'end_date': fim.isoformat()}

        from apps.stores.api.analytics_views import OverviewReportView
        from apps.stores.api.export_views import CustomersReportView, SaladasReportView

        visao_geral = self.chamar(OverviewReportView.as_view(), **periodo)['current']['new_customers']
        relatorio = self.chamar(CustomersReportView.as_view(), **periodo)['summary']['new_customers']
        saladas = self.chamar(SaladasReportView.as_view(), period='30d')['customers']['new']
        definicao = indicadores.clientes_novos(self.store, inicio, fim)

        assert definicao == 2
        assert visao_geral == relatorio == saladas == definicao


# ── Esperando resposta ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEsperandoResposta:
    """Início 13 × Conversas 10 × Esperando atendente 23/10 — agora um número só."""

    def test_inicio_e_fila_humana_contam_igual(self):
        from apps.conversations.api.views import ConversationViewSet
        from apps.conversations.models import Conversation
        from apps.conversations.services.atendimento_humano import assumir_atendimento
        from apps.core.dashboard_views import DashboardOverviewView
        from apps.whatsapp.models import WhatsAppAccount

        dono = User.objects.create_user(username='dono-esp', password='x')
        conta = WhatsAppAccount.objects.create(
            name='C', phone_number_id='pn-esp', waba_id='wa-esp', phone_number='+5563900077',
            display_phone_number='+5563900077', access_token_encrypted='x',
            webhook_verify_token='x', owner=dono,
        )
        agora = timezone.now()

        def conversa(tel, humana, escreveu, respondemos=None):
            c = Conversation.objects.create(account=conta, phone_number=tel, contact_name=tel)
            if humana:
                assumir_atendimento(c, origem='eco_do_app_business')
            Conversation.objects.filter(pk=c.pk).update(
                last_customer_message_at=escreveu, last_agent_message_at=respondemos,
            )
            return c

        conversa('5563911110001', True, agora - timedelta(minutes=30))           # conta
        conversa('5563911110002', True, agora - timedelta(hours=30))             # conta (entre 24 e 48 h)
        conversa('5563911110003', True, agora - timedelta(days=3))               # fora da janela
        conversa('5563911110004', False, agora - timedelta(minutes=5))           # bot sem responder: conta
        conversa('5563911110005', True, agora - timedelta(minutes=50),
                 respondemos=agora - timedelta(minutes=10))                      # respondida

        rf = APIRequestFactory(SERVER_NAME='localhost')
        req = rf.get('/x')
        force_authenticate(req, user=dono)
        inicio = DashboardOverviewView.as_view()(req).data['conversations']['waiting_reply']

        req = rf.get('/x')
        force_authenticate(req, user=dono)
        fila = ConversationViewSet.as_view({'get': 'fila_humana'})(req).data

        definicao = indicadores.esperando_resposta(Conversation.objects.filter(account=conta)).count()
        assert definicao == 3
        assert inicio == fila['resumo']['esperando'] == len(fila['esperando']) == definicao


# ── Itens para repor ──────────────────────────────────────────────────────

class ItensParaReporTests(Base):
    """Visão geral contava `estoque <= 10` sem olhar controle nem mínimo: 29 × 6."""

    def produto(self, nome, *, qtd, minimo=5, controla=True, status='active'):
        return StoreProduct.objects.create(
            store=self.store, name=nome, slug=nome.lower(), price=Decimal('10'), status=status,
            track_stock=controla, stock_quantity=qtd, low_stock_threshold=minimo,
        )

    def test_visao_geral_inicio_e_loja_contam_igual(self):
        self.produto('Zerado', qtd=0)                     # sem estoque → repor
        self.produto('No fim', qtd=3)                     # acabando → repor
        self.produto('Folgado', qtd=8)                    # ≤10 mas acima do mínimo → não
        self.produto('Ilimitado', qtd=0, controla=False)  # não controla estoque → não
        self.produto('Pausado', qtd=0, status='inactive') # fora do ar → não

        from apps.core.dashboard_views import DashboardStatsView
        from apps.stores.api.export_views import StoreDashboardStatsView
        from apps.stores.api.views.store_views import StoreViewSet

        visao_geral = self.chamar(StoreDashboardStatsView.as_view())['alerts']['low_stock_products']
        inicio = self.chamar(DashboardStatsView.as_view())['alerts']['low_stock_products']
        loja = self.chamar(
            StoreViewSet.as_view({'get': 'stats'}), path_params={'pk': str(self.store.pk)},
        )['products']['low_stock']
        definicao = indicadores.itens_para_repor(StoreProduct.objects.filter(store=self.store)).count()

        assert definicao == 2
        assert visao_geral == inicio == loja == definicao


# ── Entrega de campanha ───────────────────────────────────────────────────

class EntregaDeCampanhaTests(TestCase):
    def test_taxa_e_entregues_sobre_publico_total(self):
        from apps.campaigns.api.serializers import CampaignSerializer
        from apps.campaigns.models import Campaign
        from apps.campaigns.services.campaign_service import CampaignService
        from apps.whatsapp.models import WhatsAppAccount

        dono = User.objects.create_user(username='dono-camp', password='x')
        conta = WhatsAppAccount.objects.create(
            name='C', phone_number_id='pn-camp', waba_id='wa-camp', phone_number='+5563900088',
            display_phone_number='+5563900088', access_token_encrypted='x',
            webhook_verify_token='x', owner=dono,
        )
        camp = Campaign.objects.create(
            account=conta, name='Promo', total_recipients=561,
            messages_sent=30, messages_delivered=30, messages_read=10,
        )

        esperado = indicadores.taxa_de_entrega(30, 561)
        assert esperado == pytest.approx(5.3)
        assert camp.delivery_rate == esperado
        assert CampaignSerializer(camp).data['delivery_rate'] == esperado
        assert CampaignService().get_campaign_stats(str(camp.id))['delivery_rate'] == esperado

    def test_sem_publico_nao_inventa_percentual(self):
        assert indicadores.taxa_de_entrega(0, 0) is None


# ── Comparação com a média ────────────────────────────────────────────────

class MediaDeReferenciaTests(Base):
    """Vigia e resumo da IA comparavam contra médias diferentes."""

    def test_vigia_e_resumo_usam_a_mesma_media_com_janela(self):
        ontem = self.hoje - timedelta(days=1)

        def as_doze(d):
            return datetime(d.year, d.month, d.day, 12, 0, tzinfo=SP)

        self.pedido('200.00', quando=as_doze(ontem))
        # Quatro mesmos dias-da-semana anteriores: 100, 100, 0 (sem venda), 200.
        self.pedido('100.00', quando=as_doze(ontem - timedelta(days=7)))
        self.pedido('100.00', quando=as_doze(ontem - timedelta(days=14)))
        self.pedido('200.00', quando=as_doze(ontem - timedelta(days=28)))

        ref = indicadores.media_de_referencia(self.store, ontem)
        assert ref['receita'] == Decimal('100.00')
        assert ref['janela'].startswith('últimas 4 ')

        from apps.stores.vigias.regras import resumo_da_manha
        fato = resumo_da_manha(self.store, self.agora)[0]
        assert Decimal(str(fato.dados['base_media'])) == ref['receita']
        assert ref['janela'] in fato.texto
        assert fato.dados['variacao_pct'] == 100

        from apps.stores.services import ai_insights
        with mock.patch.object(ai_insights, '_llm_text', side_effect=Exception('sem llm')):
            resumo = ai_insights.generate_daily_summary(self.store, day=ontem)
        assert Decimal(str(resumo['referencia']['receita'])) == ref['receita']
        assert resumo['referencia']['janela'] == ref['janela']
        assert resumo['referencia']['variacao_pct'] == 100


# ── Ranking de produtos ───────────────────────────────────────────────────

class RankingDeProdutosTests(Base):
    """O mesmo prato aparecia em duas linhas porque o agrupamento era pelo nome gravado."""

    def test_um_produto_uma_linha_em_todos_os_rankings(self):
        prato = StoreProduct.objects.create(store=self.store, name='Queridinha', slug='queridinha', price=Decimal('30'))
        outro = StoreProduct.objects.create(store=self.store, name='Especial Filé de Frango', slug='especial', price=Decimal('40'))
        for nome_gravado in ('Queridinha', 'Queridinha (antiga)', 'queridinha '):
            p = self.pedido('30.00')
            StoreOrderItem.objects.create(order=p, product=prato, product_name=nome_gravado,
                                          quantity=1, unit_price=Decimal('30'), subtotal=Decimal('30'))
        p = self.pedido('40.00')
        StoreOrderItem.objects.create(order=p, product=outro, product_name='Especial Filé de Frango',
                                      quantity=1, unit_price=Decimal('40'), subtotal=Decimal('40'))

        periodo = {'start_date': self.hoje.isoformat(), 'end_date': self.hoje.isoformat()}
        from apps.stores.api.analytics_views import AbcReportView
        from apps.stores.api.export_views import ProductsReportView, SaladasReportView
        from apps.stores.services.ai_insights import compute_daily_stats

        abc = self.chamar(AbcReportView.as_view(), **periodo)['products']
        produtos = self.chamar(ProductsReportView.as_view(), **periodo)['top_products']
        saladas = self.chamar(SaladasReportView.as_view(), period='today')['top_products']
        nucleo = metrics.top_produtos(self.store, metrics.hoje())
        ia = compute_daily_stats(self.store, self.hoje)['top_products']

        for linhas, nome, qtd in (
            (abc, 'product_name', 'quantity'),
            (produtos, 'product_name', 'total_quantity'),
            (saladas, 'name', 'quantity'),
            (nucleo, 'nome', 'unidades'),
            (ia, 'name', 'qty'),
        ):
            queridinha = [r for r in linhas if 'queridinha' in r[nome].lower()]
            assert len(queridinha) == 1, linhas
            assert queridinha[0][nome] == 'Queridinha'
            assert queridinha[0][qtd] == 3


# ── Tempos de operação ────────────────────────────────────────────────────

class TemposDeOperacaoTests(Base):
    def test_esquecido_sai_da_media_e_vai_a_parte(self):
        base = self.agora.replace(hour=10, minute=0, second=0, microsecond=0)
        for minutos in (30, 40, 50):
            p = self.pedido(quando=base)
            StoreOrder.objects.filter(pk=p.pk).update(delivered_at=base + timedelta(minutes=minutos))
        # Pedido deixado aberto 42 dias e "entregue" hoje.
        p = self.pedido(quando=base)
        StoreOrder.objects.filter(pk=p.pk).update(
            created_at=base - timedelta(days=42), delivered_at=base + timedelta(minutes=5),
        )

        from apps.stores.api.analytics_views import SlaReportView
        inicio = (self.hoje - timedelta(days=60)).isoformat()
        etapas = {e['stage']: e for e in self.chamar(
            SlaReportView.as_view(), start_date=inicio, end_date=self.hoje.isoformat(),
        )['stages']}
        total = etapas['total']

        assert total['count'] == 3
        assert total['avg_minutes'] == 40.0
        assert total['p90_minutes'] == 48.0
        assert total['esquecidos'] == 1
        assert total['p90_minutes'] >= total['avg_minutes']

    def test_percentil_interpola(self):
        assert indicadores.percentil([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], 0.9) == pytest.approx(91.0)
        assert indicadores.percentil([], 0.9) is None
