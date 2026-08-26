"""A cozinha não consegue preparar o que a comanda não diz.

Pedido real IVO2608180318 (Fabiana chater, 18/ago, Ivoneth Banqueteria).
O que saía no papel:

    [ ] 2x MINI HAMBURGUER
    [ ] 1x TRIO ENTRADAS 20 PESSOAS

"2x Mini Hambúrguer" são 2 unidades ou 2 embalagens? O catálogo sabe — a
descrição do produto diz "Vendido em embalagem com 50 unidades", ou seja
**100 unidades**. E o "trio entradas" tem a composição escrita linha a linha
(terrine de gorgonzola, terrine de frango, kibe cru recheado). Nada disso
chegava à cozinha, que precisava abrir o painel no celular para cada item.

Esta é a diferença entre a comanda de ENTREGA (o que sai) e a comanda de
PREPARO (o que se monta). Os dados já existiam; faltava imprimi-los.
"""
from decimal import Decimal

from django.test import TestCase

from apps.stores.models import StoreOrder, StoreOrderItem, StoreProduct
from apps.stores.tests.factories import make_store
from apps.stores.services.print_service import (
    build_order_print_payload,
    linhas_de_preparo,
    rendimento_por_embalagem,
)


class RendimentoTests(TestCase):
    """Quanto rende UMA unidade vendida, lido da descrição do catálogo."""

    def test_le_embalagem_com_n_unidades(self):
        self.assertEqual(
            rendimento_por_embalagem('Mini hambúrguer. Vendido em embalagem com 50 unidades.'),
            (50, 'unidades'),
        )

    def test_le_contagem_no_inicio(self):
        self.assertEqual(
            rendimento_por_embalagem('100 unidades de brigadeiro caseiro.'),
            (100, 'unidades'),
        )
        self.assertEqual(
            rendimento_por_embalagem('25 unidades de salgados assados!'),
            (25, 'unidades'),
        )

    def test_le_quantas_pessoas_serve(self):
        self.assertEqual(
            rendimento_por_embalagem('Serve 6 pessoas'), (6, 'pessoas')
        )

    def test_sem_numero_nao_inventa(self):
        self.assertIsNone(rendimento_por_embalagem(''))
        self.assertIsNone(rendimento_por_embalagem('O combo perfeito para quem ama salmão!'))

    def test_preco_nao_e_rendimento(self):
        """`R$ 43.60` e `500g` não são contagem de itens."""
        self.assertIsNone(rendimento_por_embalagem('*Economize: R$ 43.60*'))
        self.assertIsNone(rendimento_por_embalagem('Massa de beijinho congelada (500g)'))


class LinhasDePreparoTests(TestCase):
    def test_multiplica_o_rendimento_pela_quantidade(self):
        linhas = linhas_de_preparo('Mini hambúrguer. Vendido em embalagem com 50 unidades.', 2)
        self.assertIn('>> 100 UNIDADES (2 x 50)', linhas)

    def test_quantidade_um_nao_mostra_a_conta(self):
        linhas = linhas_de_preparo('25 unidades de salgados assados!', 1)
        self.assertIn('>> 25 UNIDADES', linhas)
        self.assertNotIn('>> 25 UNIDADES (1 x 25)', linhas)

    def test_composicao_vira_uma_linha_por_item(self):
        linhas = linhas_de_preparo('1 terrine gorgonzola \r\n1 terrine de frango \r\n1 kibe cru rcheado', 1)
        self.assertIn('- 1 terrine gorgonzola', linhas)
        self.assertIn('- 1 terrine de frango', linhas)
        self.assertIn('- 1 kibe cru rcheado', linhas)

    def test_asterisco_do_whatsapp_nao_vai_para_o_papel(self):
        """`*delicioso*` é negrito do WhatsApp; no papel vira ruído."""
        linhas = linhas_de_preparo('100 unidades de brigadeiro.\nExtremamente *delicioso*.', 1)
        self.assertFalse(any('*' in l for l in linhas), linhas)

    def test_texto_de_venda_sem_dado_util_nao_polui_a_comanda(self):
        """Descrição de marketing não ajuda a cozinha e ocupa papel."""
        self.assertEqual(
            linhas_de_preparo('O combo perfeito para quem ama salmão!', 1), []
        )

    def test_sem_descricao_nao_quebra(self):
        self.assertEqual(linhas_de_preparo('', 3), [])
        self.assertEqual(linhas_de_preparo(None, 1), [])


class PayloadDaComandaTests(TestCase):
    """O preparo precisa chegar ao print-agent, não só existir no banco."""

    def setUp(self):
        self.store = make_store(name='Ivoneth', slug='ivoneth-teste')
        self.produto = StoreProduct.objects.create(
            store=self.store,
            name='Mini Hambúrguer',
            price=Decimal('215.00'),
            description='Mini hambúrguer. Vendido em embalagem com 50 unidades.',
        )
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Fabiana chater',
            customer_phone='5563999999999',
            subtotal=Decimal('430.00'),
            total=Decimal('430.00'),
        )

    def test_item_carrega_as_linhas_de_preparo(self):
        StoreOrderItem.objects.create(
            order=self.order,
            product=self.produto,
            product_name='Mini Hambúrguer',
            quantity=2,
            unit_price=Decimal('215.00'),
            subtotal=Decimal('430.00'),
        )
        item = build_order_print_payload(self.order)['items'][0]
        self.assertIn('>> 100 UNIDADES (2 x 50)', item['prep'])

    def test_produto_apagado_do_catalogo_nao_quebra_a_comanda(self):
        """`product` é SET_NULL: pedido antigo sobrevive ao produto excluído."""
        StoreOrderItem.objects.create(
            order=self.order,
            product=None,
            product_name='Produto Removido',
            quantity=1,
            unit_price=Decimal('10.00'),
            subtotal=Decimal('10.00'),
        )
        item = build_order_print_payload(self.order)['items'][0]
        self.assertEqual(item['prep'], [])
