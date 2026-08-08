"""Perfil de CRM do cliente vem dos PEDIDOS, não do contador denormalizado.

`StoreCustomer.total_spent` / `total_orders` / `last_order_at` são campos
gravados por signal. Em 07/ago/2026, 12 dos 78 clientes da Cê Saladas estavam
errados: a lista somava R$ 2.726,01 e os pedidos somavam R$ 2.613,21. Contador
denormalizado que ninguém reconcilia sempre diverge — pedido editado, pedido
cancelado depois de pago, restauração de backup.

O painel passa a exibir os campos derivados (`dias_sem_comprar`, `perfil`,
`gasto_real`, `pedidos_reais`) calculados sobre o MESMO núcleo que produz o
faturamento (`apps.stores.metrics`). Uma definição de "receita", em todo lugar.

`perfil` classifica sem pedir configuração:
  novo       0 ou 1 pedido
  ocasional  2 a 4 pedidos
  vip        5+ pedidos
Régua explícita em vez de "VIP" mágico — quem lê a tela precisa saber o corte.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCustomer, StoreOrder

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-crm', email='dono-crm@x.com', password='x')
    return Store.objects.create(name='Loja CRM', slug='loja-crm', owner=dono)


def _pedido(loja, user, total, quando, status=None, payment_status=None):
    pedido = StoreOrder.objects.create(
        store=loja,
        # A FK do pedido chama-se `customer` e aponta para auth.User —
        # `StoreCustomer` é o perfil da loja, não o dono do pedido.
        customer=user,
        total=Decimal(str(total)),
        subtotal=Decimal(str(total)),
        status=status or StoreOrder.OrderStatus.DELIVERED,
        payment_status=payment_status or StoreOrder.PaymentStatus.PAID,
    )
    # created_at é auto_now_add: só dá para posicionar no tempo com update().
    StoreOrder.objects.filter(pk=pedido.pk).update(created_at=quando, paid_at=quando)
    return pedido


@pytest.fixture
def cliente(loja):
    user = User.objects.create_user(username='cli-crm', email='cli@x.com', password='x')
    return StoreCustomer.objects.create(store=loja, user=user, phone='63999990000')


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(user=loja.owner)
    return c


def _linha(api, loja, cliente):
    # A lista do painel é o router raiz filtrado por `?store=`, NÃO a rota
    # aninhada — `/stores/{slug}/customers/` cai no include do storefront.
    r = api.get('/api/v1/stores/customers/', {'store': loja.slug})
    assert r.status_code == 200, r.content
    dados = r.json()
    linhas = dados['results'] if isinstance(dados, dict) else dados
    return next(l for l in linhas if str(l['id']) == str(cliente.id))


@pytest.mark.django_db
class TestPerfilCrm:
    def test_gasto_real_ignora_o_contador_defasado(self, api, loja, cliente):
        # O cenário exato da Cê Saladas: o contador diz mais do que os pedidos.
        StoreCustomer.objects.filter(pk=cliente.pk).update(
            total_spent=Decimal('999.00'), total_orders=99,
        )
        agora = timezone.now()
        _pedido(loja, cliente.user, '100.00', agora - timedelta(days=3))
        _pedido(loja, cliente.user, '50.00', agora - timedelta(days=1))

        linha = _linha(api, loja, cliente)
        assert Decimal(str(linha['gasto_real'])) == Decimal('150.00')
        assert linha['pedidos_reais'] == 2

    def test_pedido_cancelado_nao_conta(self, api, loja, cliente):
        agora = timezone.now()
        _pedido(loja, cliente.user, '100.00', agora - timedelta(days=2))
        _pedido(
            loja, cliente.user, '500.00', agora - timedelta(days=1),
            status=StoreOrder.OrderStatus.CANCELLED,
        )

        linha = _linha(api, loja, cliente)
        assert Decimal(str(linha['gasto_real'])) == Decimal('100.00')
        assert linha['pedidos_reais'] == 1

    def test_dias_sem_comprar_conta_do_ultimo_pedido_valido(self, api, loja, cliente):
        _pedido(loja, cliente.user, '30.00', timezone.now() - timedelta(days=40))
        linha = _linha(api, loja, cliente)
        assert linha['dias_sem_comprar'] == 40

    def test_cliente_sem_pedido_nao_finge_ter_comprado_hoje(self, api, loja, cliente):
        # 0 dias seria lido como "comprou hoje" — mentira perigosa numa lista
        # ordenada por reengajamento. Sem pedido, não existe a conta.
        linha = _linha(api, loja, cliente)
        assert linha['dias_sem_comprar'] is None
        assert linha['perfil'] == 'novo'

    @pytest.mark.parametrize('qtd,esperado', [(1, 'novo'), (2, 'ocasional'), (4, 'ocasional'), (5, 'vip')])
    def test_perfil_pelo_numero_de_pedidos(self, api, loja, cliente, qtd, esperado):
        agora = timezone.now()
        for i in range(qtd):
            _pedido(loja, cliente.user, '20.00', agora - timedelta(days=i + 1))
        assert _linha(api, loja, cliente)['perfil'] == esperado

    def test_uma_query_para_a_lista_inteira(self, api, loja, django_assert_max_num_queries):
        # A tentação é calcular por linha e detonar N+1 numa base de 2.400
        # clientes. Os agregados entram por annotate.
        agora = timezone.now()
        for i in range(12):
            u = User.objects.create_user(username=f'c{i}', email=f'c{i}@x.com', password='x')
            StoreCustomer.objects.create(store=loja, user=u, phone=f'6399999{i:04d}')
            _pedido(loja, u, '25.00', agora - timedelta(days=i + 1))

        with django_assert_max_num_queries(12):
            r = api.get('/api/v1/stores/customers/', {'store': loja.slug})
            assert r.status_code == 200


@pytest.mark.django_db
class TestSegmentosDeCrm:
    """A lista de clientes precisa responder A QUEM MANDAR MENSAGEM HOJE.

    "2.386 clientes cadastrados" não é acionável. "106 em risco — 30 a 45 dias
    sem comprar" é: dá para disparar uma campanha nesses hoje à tarde.

    A RÉGUA VAI JUNTO DO NÚMERO. "Em risco" sem o corte é opinião nossa
    disfarçada de dado — quem lê não tem como julgar se concorda, nem como
    explicar o número para outra pessoa.
    """

    def _stats(self, api, loja):
        r = api.get('/api/v1/stores/customers/stats/', {'store': loja.slug})
        assert r.status_code == 200, r.content
        return r.json()['segmentos']

    def test_classifica_pela_ultima_compra(self, api, loja):
        agora = timezone.now()
        casos = [
            ('ativo', 5),        # comprou esta semana
            ('em_risco', 35),    # 30–45 dias
            ('inativo', 90),     # 45+
        ]
        for i, (_, dias) in enumerate(casos):
            u = User.objects.create_user(username=f'seg{i}', email=f'seg{i}@x.com', password='x')
            StoreCustomer.objects.create(store=loja, user=u, phone=f'639000000{i}')
            _pedido(loja, u, '50.00', agora - timedelta(days=dias))

        s = self._stats(api, loja)
        assert s['ativos'] == 1
        assert s['em_risco'] == 1
        assert s['inativos'] == 1

    def test_cada_segmento_declara_a_propria_regua(self, api, loja):
        # Sem o corte escrito, "em risco" é opinião nossa disfarçada de dado.
        s = self._stats(api, loja)
        assert '30' in s['reguas']['em_risco'] and '45' in s['reguas']['em_risco']
        assert '45' in s['reguas']['inativos']

    def test_quem_nunca_comprou_nao_e_inativo(self, api, loja):
        # Cadastro sem compra é LEAD, não cliente perdido. Somar os dois
        # inflaria "inativos" e mandaria campanha de reativação para quem nunca
        # ativou.
        u = User.objects.create_user(username='lead', email='lead@x.com', password='x')
        StoreCustomer.objects.create(store=loja, user=u, phone='63900001111')

        s = self._stats(api, loja)
        assert s['inativos'] == 0
        assert s['sem_compra'] == 1

    def test_pedido_cancelado_nao_conta_como_ultima_compra(self, api, loja):
        u = User.objects.create_user(username='canc', email='canc@x.com', password='x')
        StoreCustomer.objects.create(store=loja, user=u, phone='63900002222')
        _pedido(loja, u, '50.00', timezone.now() - timedelta(days=2),
                status=StoreOrder.OrderStatus.CANCELLED)

        s = self._stats(api, loja)
        assert s['ativos'] == 0
        assert s['sem_compra'] == 1
