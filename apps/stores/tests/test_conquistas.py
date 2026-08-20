"""Conquistas de faturamento — marcos DERIVADOS, nunca armazenados.

A decisão que define este módulo: uma conquista não é um registro, é um FATO
sobre o histórico. "R$ 10 mil faturados" aconteceu no dia em que a receita
acumulada cruzou 10 mil — e isso se calcula.

Guardar numa tabela parece mais simples e é pior. Pedido cancelado depois de
pago, reembolso, restauração de backup: qualquer um deles muda o acumulado, e
a conquista gravada passa a mentir. É o mesmo defeito que encontramos hoje em
`StoreCustomer.total_spent`, onde 12 de 78 clientes tinham valor errado por
contador denormalizado que ninguém reconcilia.

Derivando, a conquista some sozinha se o faturamento que a sustentava sumiu.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import Store, StoreOrder
from apps.stores.services import conquistas as svc

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-cq', email='cq@x.com', password='x')
    return Store.objects.create(name='Loja CQ', slug='loja-cq', owner=dono, status='active')


def pedido(loja, total, dias_atras=0):
    quando = timezone.now() - timedelta(days=dias_atras)
    p = StoreOrder.objects.create(
        store=loja,
        total=Decimal(str(total)),
        subtotal=Decimal(str(total)),
        status=StoreOrder.OrderStatus.DELIVERED,
        payment_status=StoreOrder.PaymentStatus.PAID,
    )
    StoreOrder.objects.filter(pk=p.pk).update(created_at=quando, paid_at=quando)
    return p


@pytest.mark.django_db
class TestConquistas:
    def test_loja_sem_venda_nao_tem_conquista(self, loja):
        assert svc.conquistas_alcancadas(loja) == []

    def test_a_primeira_venda_e_uma_conquista(self, loja):
        # É o marco que mais importa e o único que não é sobre dinheiro: é
        # sobre a loja ter saído do papel.
        pedido(loja, 236, dias_atras=10)
        alcancadas = svc.conquistas_alcancadas(loja)
        assert alcancadas[0]['chave'] == 'primeira_venda'
        assert alcancadas[0]['faturamento_no_marco'] == Decimal('236.00')

    def test_marco_registra_o_dia_em_que_o_acumulado_cruzou(self, loja):
        # 600 + 600 = 1200: o marco de mil aconteceu no SEGUNDO pedido, não no
        # dia em que alguém olhou o painel.
        pedido(loja, 600, dias_atras=5)
        p2 = pedido(loja, 600, dias_atras=3)
        # `.update()` não mexe no objeto em memória: sem recarregar, `p2`
        # ainda tem o created_at de agora e o teste compara com a data errada.
        p2.refresh_from_db()

        mil = next(c for c in svc.conquistas_alcancadas(loja) if c['chave'] == 'faturamento_1000')
        assert mil['alcancado_em'] == p2.created_at.astimezone().date()
        assert mil['faturamento_no_marco'] == Decimal('1200.00')

    def test_conquistas_vem_da_mais_recente_para_a_mais_antiga(self, loja):
        # A lista é uma linha do tempo que se lê de cima para baixo: o que
        # acabou de acontecer primeiro. Ordem crescente enterraria a conquista
        # nova sob dez antigas.
        pedido(loja, 6000, dias_atras=10)
        chaves = [c['chave'] for c in svc.conquistas_alcancadas(loja)]
        assert chaves[0] == 'faturamento_5000'
        assert chaves[-1] == 'primeira_venda'

    def test_pedido_cancelado_nao_gera_conquista(self, loja):
        # É a razão de derivar em vez de gravar: cancelar depois de pago
        # desfaz a conquista sozinho.
        p = pedido(loja, 5000, dias_atras=2)
        StoreOrder.objects.filter(pk=p.pk).update(status=StoreOrder.OrderStatus.CANCELLED)
        assert svc.conquistas_alcancadas(loja) == []

    def test_marco_nao_atingido_nao_aparece(self, loja):
        pedido(loja, 900, dias_atras=1)
        chaves = [c['chave'] for c in svc.conquistas_alcancadas(loja)]
        assert 'faturamento_1000' not in chaves
        assert chaves == ['primeira_venda']


@pytest.mark.django_db
class TestProximaConquista:
    def test_aponta_o_proximo_marco_e_quanto_falta(self, loja):
        pedido(loja, 1200, dias_atras=3)
        p = svc.proxima_conquista(loja)
        assert p['valor'] == Decimal('5000')
        assert p['falta'] == Decimal('3800.00')
        assert 0 < p['progresso_pct'] < 100

    def test_loja_sem_venda_mira_a_primeira(self, loja):
        # "Sua primeira venda" é objetivo melhor que "R$ 1.000" para quem ainda
        # não vendeu nada: o segundo parece inalcançável e desliga.
        p = svc.proxima_conquista(loja)
        assert p['chave'] == 'primeira_venda'

    def test_estima_o_prazo_pelo_ritmo_recente(self, loja):
        # 30 dias vendendo 100/dia → 3.000 acumulados, ritmo de 100/dia.
        # Próximo marco é 5.000, faltam 2.000: ~20 dias.
        for d in range(30):
            pedido(loja, 100, dias_atras=d)
        p = svc.proxima_conquista(loja)
        assert p['dias_estimados'] is not None
        assert 18 <= p['dias_estimados'] <= 22, p['dias_estimados']

    def test_sem_ritmo_nao_inventa_prazo(self, loja):
        # Loja parada há meses: dividir por zero daria infinito, e uma data
        # chutada é pior que nenhuma — o dono planeja em cima dela.
        pedido(loja, 1200, dias_atras=200)
        p = svc.proxima_conquista(loja)
        assert p['dias_estimados'] is None
        assert p['prazo_estimado'] is None

    def test_todos_os_marcos_batidos_nao_quebra(self, loja):
        # Acima do último marco da escala a resposta é "não há próximo", não
        # um erro nem um marco inventado.
        pedido(loja, 99_000_000, dias_atras=1)
        assert svc.proxima_conquista(loja) is None


@pytest.mark.django_db
class TestResumoDeMetas:
    def test_crescimento_mensal_compara_com_o_mes_anterior(self, loja):
        # Data explícita, não "40 dias atrás": rodando no dia 8, 40 dias atrás
        # cai DOIS meses para trás, e o mês anterior fica zerado — o teste
        # passaria a medir outra coisa conforme o dia em que roda.
        from apps.stores.metrics import hoje_local
        hoje = hoje_local()
        ultimo_dia_mes_passado = hoje.replace(day=1) - timedelta(days=1)
        pedido(loja, 1000, dias_atras=(hoje - ultimo_dia_mes_passado).days)
        pedido(loja, 1500, dias_atras=0)
        r = svc.resumo_de_metas(loja)
        assert r['mes_atual'] == Decimal('1500.00')
        assert r['crescimento_mensal_pct'] is not None

    def test_sem_mes_anterior_nao_ha_percentual(self, loja):
        # Sair de zero não é "+100%", é uma conta que não existe. Mostrar
        # número ali dá uma precisão que o dado não tem.
        pedido(loja, 1500, dias_atras=0)
        r = svc.resumo_de_metas(loja)
        assert r['crescimento_mensal_pct'] is None

    def test_meta_anual_nasce_do_ano_anterior_com_crescimento(self, loja):
        r = svc.resumo_de_metas(loja)
        assert r['meta_anual']['crescimento_pct'] == 20


@pytest.mark.django_db
class TestEndpointDeConquistas:
    def _api(self, loja):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=loja.owner)
        return c

    def test_devolve_resumo_proxima_e_conquistas_numa_chamada(self, loja):
        # Três requisições produziriam três estados de carga piscando em
        # sequência na mesma tela.
        pedido(loja, 1200, dias_atras=3)
        r = self._api(loja).get(f'/api/v1/stores/{loja.slug}/conquistas/')
        assert r.status_code == 200, r.content
        d = r.json()
        assert set(d) == {'resumo', 'proxima', 'conquistas'}
        assert d['conquistas'][0]['chave'] == 'faturamento_1000'

    def test_loja_de_outro_dono_e_negada(self, loja):
        from rest_framework.test import APIClient
        outro = User.objects.create_user(username='intruso-cq', email='i@x.com', password='x')
        c = APIClient()
        c.force_authenticate(user=outro)
        r = c.get(f'/api/v1/stores/{loja.slug}/conquistas/')
        assert r.status_code == 404
