"""Venda de balcão não é venda pelo site.

A coluna `source` existe para o dono saber de onde vem o dinheiro antes de
decidir onde investir. Só que o serializer de criação nunca a preenchia: o
`save()` do model cai no default `'web'` quando ninguém diz nada, então TODA
venda do PDV Balcão era creditada ao site.

Medido em produção (15/ago): os pedidos de balcão da Agrião, com
`metadata.suppress_notifications`, todos com `source='web'`.

O model já sabia traduzir — `_SOURCE_MAP_PREFIXES` mapeia 'dashboard' e 'pdv'
para 'pdv'. Faltava alguém escrever a origem. Quem sabe o canal é o cliente da
API, não o backend: o mesmo endpoint serve o PDV, o drawer de pedido manual e
integrações futuras.
"""
import pytest

from apps.stores.api.serializers import StoreOrderCreateSerializer
from apps.stores.models import StoreOrder, StoreProduct
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Agrião')


@pytest.fixture
def produto(loja):
    # `track_stock=False`: este teste é sobre o canal da venda, não sobre
    # estoque — sem isso a criação morre em "estoque insuficiente" e o teste
    # falha por um motivo que não é o dele.
    return StoreProduct.objects.create(
        store=loja, name='Marmita', price='23.00',
        status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
    )


def criar(loja, produto, **extra):
    dados = {
        'store': loja.slug,
        'customer_name': 'Cliente Balcão',
        'customer_phone': '00000000000',
        'delivery_method': 'pickup',
        'items': [{'product_id': str(produto.id), 'quantity': 1}],
        **extra,
    }
    s = StoreOrderCreateSerializer(data=dados)
    assert s.is_valid(), s.errors
    return s.save()


@pytest.mark.django_db
class TestOCanalDaVenda:
    def test_pdv_grava_pdv(self, loja, produto):
        pedido = criar(loja, produto, source='pdv')
        assert pedido.source == 'pdv'

    def test_pedido_manual_do_painel_tambem_conta_como_pdv(self, loja, produto):
        """`dashboard` e `pdv` são o mesmo canal para o relatório: venda feita
        por dentro da loja, não pelo cliente no site."""
        pedido = criar(loja, produto, source='dashboard')
        assert pedido.source == 'pdv'

    def test_sem_declarar_o_canal_continua_web(self, loja, produto):
        """Compatibilidade: cliente antigo que não manda `source` não quebra."""
        pedido = criar(loja, produto)
        assert pedido.source == 'web'

    def test_canal_desconhecido_nao_inventa_coluna(self, loja, produto):
        """String livre vira 'web' pelo mapa do model, em vez de sujar o BI."""
        pedido = criar(loja, produto, source='qualquer-coisa')
        assert pedido.source == 'web'

    def test_o_canal_sobrevive_no_metadata(self, loja, produto):
        """O valor cru fica registrado: 'dashboard' e 'pdv' viram a mesma
        coluna, e sem o cru não dá para distinguir depois."""
        pedido = criar(loja, produto, source='pdv')
        assert pedido.metadata.get('source') == 'pdv'

    def test_o_canal_nao_apaga_o_resto_do_metadata(self, loja, produto):
        pedido = criar(loja, produto, source='pdv', suppress_notifications=True)
        assert pedido.metadata.get('suppress_notifications') is True
        assert pedido.metadata.get('source') == 'pdv'


@pytest.mark.django_db
class TestOQueNaoPodeMudar:
    def test_o_pedido_continua_completo(self, loja, produto):
        pedido = criar(loja, produto, source='pdv')
        assert pedido.items.count() == 1
        assert pedido.total == StoreOrder.objects.get(pk=pedido.pk).total
