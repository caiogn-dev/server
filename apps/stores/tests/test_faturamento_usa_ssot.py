"""Toda tela que fala de dinheiro tem que passar pelo SSOT de receita.

Existe `apps/stores/metrics/` com a regra canônica (pago E não
cancelado E não é teste), mas metade das telas montava a própria query com
`payment_status='paid'` e nada mais. Resultado: contavam venda cancelada e
pedido de teste do dono como faturamento.

Dois riscos que sobrevivem mesmo depois de o cancelamento passar a liquidar o
pagamento:

1. **Pedido de teste** — nunca teve nada que o excluísse nessas telas.
2. **Linha legada** — pedido pago+cancelado gravado direto no banco (import,
   `.update()`, correção manual) volta a inflar se a tela confiar só no
   `payment_status`.

Por isso o filtro tem que estar na tela, não só no fluxo de cancelamento.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_ssot_telas', password='x')
    return Store.objects.create(owner=dono, name='Loja SSOT', slug='loja-ssot-telas')


@pytest.fixture
def pedidos(loja):
    """Uma venda real de R$ 50 + duas armadilhas que não são faturamento."""
    def novo(total, status='delivered', pagamento='paid', metadata=None):
        return StoreOrder.objects.create(
            store=loja, total=Decimal(total), subtotal=Decimal(total),
            status=status, payment_status=pagamento, metadata=metadata or {},
        )

    real = novo('50.00')
    novo('100.00', status='cancelled')          # legado: cancelado ainda 'paid'
    novo('300.00', metadata={'is_test': True})  # pedido de teste do dono
    return real


RECEITA_REAL = Decimal('50.00')


@pytest.mark.django_db
class TestTelasDeFaturamento:

    def test_bi_avancado_soma_so_a_venda_real(self, loja, pedidos):
        """Base das 6 abas de BI do painel."""
        from apps.stores.api.analytics_views import BaseAnalyticsView

        qs = BaseAnalyticsView().paid_orders(loja, '2000-01-01', '2100-01-01')

        assert list(qs) == [pedidos]

    def test_resumo_do_dashboard_soma_so_a_venda_real(self, loja, pedidos):
        """Agora pelo payload público, não por um método interno.

        O agregador deixou de montar queryset próprio e passou a chamar
        `metrics.totais()`. Testar a saída é mais forte que testar o encanamento:
        vale mesmo que o interior mude de novo.
        """
        from decimal import Decimal

        from apps.core.services.dashboard_stats import DashboardStatsAggregator

        payload = DashboardStatsAggregator(loja).build_payload()

        assert Decimal(str(payload['today']['revenue'])) == RECEITA_REAL
        # A contagem é operacional: os 3 pedidos aparecem, o dinheiro não.
        assert payload['today']['orders'] == 3

    def test_estatisticas_da_lista_de_pedidos_somam_so_a_venda_real(self, loja, pedidos):
        from apps.stores.metrics import pedidos_de_receita

        # A lista mostra TODOS os pedidos (a cozinha precisa ver o cancelado),
        # mas o card de faturamento no topo só pode somar a venda real.
        todos = StoreOrder.objects.filter(store=loja)
        assert todos.count() == 3
        assert pedidos_de_receita(queryset=todos).count() == 1

    def test_export_de_periodo_soma_so_a_venda_real(self, loja, pedidos):
        from django.db.models import Sum

        from apps.stores.api.export_views import BaseExportView

        qs = BaseExportView().revenue_queryset(loja)

        assert qs.aggregate(t=Sum('total'))['t'] == RECEITA_REAL

    def test_caixa_nao_espera_dinheiro_de_pedido_de_teste(self, loja):
        from apps.stores.models import StoreCashSession

        sessao = StoreCashSession.objects.create(
            store=loja, opening_amount=Decimal('0.00'), status='open',
        )
        StoreOrder.objects.create(
            store=loja, total=Decimal('50.00'), subtotal=Decimal('50.00'),
            status='delivered', payment_status='paid', payment_method='cash',
        )
        StoreOrder.objects.create(
            store=loja, total=Decimal('300.00'), subtotal=Decimal('300.00'),
            status='delivered', payment_status='paid', payment_method='cash',
            metadata={'is_test': True},
        )

        assert sessao.expected_cash() == RECEITA_REAL


@pytest.mark.django_db
class TestPainelDjangoLegado:
    """O /panel/ somava `Sum('total')` sem filtro nenhum — contava até não pago."""

    def test_dashboard_do_panel_soma_so_a_venda_real(self, client, loja, pedidos):
        StoreOrder.objects.create(  # nem pago está
            store=loja, total=Decimal('999.00'), subtotal=Decimal('999.00'),
            status='pending', payment_status='pending',
        )
        loja.owner.set_password('segredo')
        loja.owner.save()
        client.force_login(loja.owner)
        sessao = client.session
        sessao['panel_store_id'] = str(loja.id)
        sessao.save()

        resposta = client.get('/panel/')

        assert resposta.status_code == 200
        assert resposta.context['revenue_today'] == RECEITA_REAL
        assert resposta.context['orders_today'] == 4, 'a contagem mostra tudo'
