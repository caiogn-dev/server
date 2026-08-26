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


class ApiDoPedidoTests(TestCase):
    """Os dois caminhos de impressão precisam dizer a MESMA coisa.

    O print-agent lê `build_order_print_payload`; o botão "Imprimir" do painel
    monta o papel no navegador a partir do serializer do pedido. Sem `prep`
    nos dois, a comanda automática diria "100 unidades" e a manual diria só
    "2x Mini Hambúrguer" — e a cozinha aprenderia a não confiar em nenhuma.
    """

    def setUp(self):
        self.store = make_store(name='Ivoneth API', slug='ivoneth-api-teste')
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
        self.item = StoreOrderItem.objects.create(
            order=self.order,
            product=self.produto,
            product_name='Mini Hambúrguer',
            quantity=2,
            unit_price=Decimal('215.00'),
            subtotal=Decimal('430.00'),
        )

    def test_serializer_expoe_o_mesmo_preparo_do_print_agent(self):
        from apps.stores.api.serializers import StoreOrderItemSerializer

        do_painel = StoreOrderItemSerializer(self.item).data['prep']
        do_agente = build_order_print_payload(self.order)['items'][0]['prep']
        self.assertEqual(do_painel, do_agente)
        self.assertIn('>> 100 UNIDADES (2 x 50)', do_painel)

    def test_prep_nao_dispara_uma_query_por_item(self):
        """`product` precisa vir no prefetch — senão a lista de pedidos
        multiplica queries pelo número de itens de cada pedido."""
        from apps.stores.api.serializers import StoreOrderItemSerializer

        for i in range(5):
            StoreOrderItem.objects.create(
                order=self.order, product=self.produto,
                product_name=f'Item {i}', quantity=1,
                unit_price=Decimal('1.00'), subtotal=Decimal('1.00'),
            )
        itens = list(self.order.items.select_related('product').all())
        with self.assertNumQueries(0):
            [StoreOrderItemSerializer(i).data['prep'] for i in itens]


class NaoImprimirMarketingTests(TestCase):
    """Descrição é escrita para VENDER. A comanda só quer o que se monta.

    Rodando a primeira versão da regra contra o catálogo real das duas lojas,
    10/42 produtos da Cê Saladas e 35/58 da Ivoneth ganhavam preparo — mas
    junto vinha promoção. O que ia sair no papel da cozinha:

        - Com 15% de desconto!
        - Economize: R$ 43.60
        - Peça agora e não fique de fora dessa promoção!

    Papel térmico é caro e atenção de cozinha em sábado de evento é mais
    ainda. Linha que não ajuda a montar não entra.
    """

    def test_preco_e_desconto_nunca_entram(self):
        linhas = linhas_de_preparo(
            '*8 unidades da queridinha*\r\n\r\nCom 15% de desconto!\r\n\r\n*Economize: R$ 43.60*', 1
        )
        self.assertIn('>> 8 UNIDADES', linhas)
        self.assertFalse(any('R$' in l or '%' in l for l in linhas), linhas)

    def test_chamariz_de_venda_nao_entra(self):
        linhas = linhas_de_preparo(
            'Combo promocional de *5 saladas*!\n\nNa compra de 4 filé de frango, '
            'você ganha *1 de graça!*\n\nPeça agora e não fique de fora dessa promoção!', 1
        )
        self.assertFalse(any('Peça agora' in l for l in linhas), linhas)
        self.assertFalse(any('promoção' in l.lower() for l in linhas), linhas)

    def test_gramatura_da_salada_entra_inteira(self):
        """A ficha da Cê Saladas é exatamente o que a montagem precisa."""
        linhas = linhas_de_preparo(
            'Tropical do Cê\n- Frango 120 g\n- abacaxi 70 g\n- manga 50 g\n'
            '- pepino 20 g\n- cebola roxa 15 g\n- gergelim 2 g', 1
        )
        self.assertIn('- Frango 120 g', linhas)
        self.assertIn('- gergelim 2 g', linhas)

    def test_marcador_nao_e_duplicado(self):
        """A descrição já vem com '-'; somar outro produz '- - Frango 120 g'."""
        linhas = linhas_de_preparo('Salada\n- Frango 120 g\n- alface 90 g', 1)
        self.assertFalse(any(l.startswith('- -') for l in linhas), linhas)

    def test_composicao_repetida_no_rendimento_nao_sai_duas_vezes(self):
        """'100 unidades de brigadeiro' já virou '>> 100 UNIDADES'."""
        linhas = linhas_de_preparo(
            '100 unidades de brigadeiro caseiro.\nExtremamente *delicioso* e pronto para o consumo.', 1
        )
        self.assertEqual(['>> 100 UNIDADES'], linhas)

    def test_sabores_do_bolo_entram(self):
        """Lista curta de sabores é o que a confeiteira precisa ler."""
        linhas = linhas_de_preparo(
            'Bolo recheado recheio\nchocolate\nchocolate e ninho\nninho\nbombom', 1
        )
        self.assertIn('- chocolate e ninho', linhas)
        self.assertIn('- bombom', linhas)


class RendimentoNaVarianteTests(TestCase):
    """A Tábua de Frios guarda o rendimento no NOME DA VARIANTE.

    Produto "Tábua de Frios", variante "Tábua - 20 Pessoas". A descrição só
    tem a composição. Sem ler a variante, justamente o item mais caro do
    pedido da Fabiana (R$ 139,99) saía sem dizer para quantas pessoas é.
    """

    def test_le_o_rendimento_do_nome_da_variante(self):
        linhas = linhas_de_preparo(
            'Provolone, parmesão, gorgonzola, mussarela e snacks.', 1,
            variante='Tábua - 20 Pessoas',
        )
        self.assertIn('>> 20 PESSOAS', linhas)

    def test_variante_sem_numero_nao_inventa(self):
        linhas = linhas_de_preparo('Quiche variado.', 1, variante='Lorraine')
        self.assertFalse(any(l.startswith('>>') for l in linhas), linhas)

    def test_descricao_vence_a_variante(self):
        """A descrição é mais específica; a variante é o palpite de reserva."""
        linhas = linhas_de_preparo('Embalagem com 50 unidades.', 2, variante='Kit - 20 Pessoas')
        self.assertIn('>> 100 UNIDADES (2 x 50)', linhas)
        self.assertFalse(any('PESSOAS' in l for l in linhas), linhas)


class NomeDoProdutoNaoSeRepeteTests(TestCase):
    """A ficha da Cê Saladas começa repetindo o nome do produto.

    "Tropical do Cê\n- Frango 120 g\n..." — o nome já está em corpo duplo na
    linha do item, logo acima. Repetir gasta papel e faz a lista de montagem
    começar com uma linha que não é ingrediente.
    """

    def test_primeira_linha_igual_ao_nome_do_produto_e_descartada(self):
        linhas = linhas_de_preparo(
            'Tropical do Cê\n- Frango 120 g\n- manga 50 g', 1, produto='Tropical do Cê'
        )
        self.assertNotIn('- Tropical do Cê', linhas)
        self.assertIn('- Frango 120 g', linhas)

    def test_ingrediente_com_o_nome_do_produto_dentro_sobrevive(self):
        """Descartar por 'contém' apagaria ingrediente legítimo."""
        linhas = linhas_de_preparo(
            'Bolo\n- Massa de bolo 300 g\n- cobertura 80 g', 1, produto='Bolo'
        )
        self.assertIn('- Massa de bolo 300 g', linhas)


class ComposicaoEmUmaLinhaTests(TestCase):
    """Nem toda ficha está cadastrada em várias linhas.

    A Tábua de Frios — o item mais caro do pedido da Fabiana — tem a
    composição inteira numa linha só, separada por vírgula:

        "Provolone, parmesão, gorgonzola, mussarela, lombo canadense,
         salaminho, presunto, azeitonas, tomate seco e snacks."

    Exigir quebra de linha jogava a conta para o dono ("recadastre o
    produto"). O separador da lista é a vírgula; a comanda que aprenda a ler.
    """

    TABUA = ('Provolone, parmesão, gorgonzola, mussarela, lombo canadense, '
             'salaminho, presunto, azeitonas, tomate seco e snacks.')

    def test_tabua_de_frios_vira_lista(self):
        linhas = linhas_de_preparo(self.TABUA, 1, variante='Tábua - 20 Pessoas')
        self.assertIn('>> 20 PESSOAS', linhas)
        self.assertIn('- Provolone', linhas)
        self.assertIn('- lombo canadense', linhas)

    def test_o_e_final_separa_o_ultimo_item(self):
        """'tomate seco e snacks' são DOIS frios, não um."""
        linhas = linhas_de_preparo(self.TABUA, 1)
        self.assertIn('- tomate seco', linhas)
        self.assertIn('- snacks', linhas)

    def test_o_e_no_meio_de_um_item_nao_separa(self):
        """'terrine de gorgonzola e damasco' é UMA terrine."""
        linhas = linhas_de_preparo(
            'Caixa com 200g de cada: terrine de gorgonzola e damasco, '
            'pasta de frango e cream cheese, queijo cremoso e nozes', 1
        )
        self.assertIn('- terrine de gorgonzola e damasco', linhas)
        self.assertIn('- pasta de frango e cream cheese', linhas)

    def test_prefixo_antes_dos_dois_pontos_vira_cabecalho(self):
        linhas = linhas_de_preparo(
            'Ingredientes: Trigo, água, sal, açúcar, mini-hambúrguer, gergelim, fermento, ovos, óleo', 1
        )
        self.assertIn('- Ingredientes:', linhas)
        self.assertIn('- Trigo', linhas)
        self.assertIn('- óleo', linhas)

    def test_sabores_disponiveis_chegam_a_cozinha(self):
        linhas = linhas_de_preparo(
            'Suco natural de polpa 1 litro. Sabores: acerola, caju, abacaxi ou goiaba.', 1
        )
        self.assertTrue(any('acerola' in l for l in linhas), linhas)
        self.assertTrue(any('goiaba' in l for l in linhas), linhas)

    def test_marketing_em_uma_linha_continua_fora(self):
        """'100 unidades de beijinho, perfeito para sua festa, ...' """
        linhas = linhas_de_preparo(
            '100 unidades de beijinho, perfeito para sua festa, comemoração e dividir com quem você ama!', 1
        )
        self.assertEqual(['>> 100 UNIDADES'], linhas)

    def test_frase_comum_nao_vira_lista(self):
        """Duas vírgulas numa frase não fazem dela uma ficha técnica."""
        linhas = linhas_de_preparo('Bolo recheado, feito na hora.', 1)
        self.assertEqual([], linhas)


class FraseComAdjetivosNaoEListaTests(TestCase):
    """Vírgula separa lista — e também adjetivo. A comanda só quer a lista.

    Os ingredientes avulsos da Cê Saladas são descritos assim:

        "Porção de 35 g. Repolho finamente fatiado, fresco, crocante."

    Quebrar por vírgula produzia três "itens" para a cozinha montar, sendo
    que dois deles são adjetivos:

        - Porção de 35 g. Repolho finamente fatiado
        - fresco
        - crocante

    O sinal que separa os dois casos: uma lista de composição não tem ponto
    final no meio. "Provolone, parmesão, gorgonzola" não tem; a frase acima
    tem, porque emenda duas orações.
    """

    def test_adjetivos_da_ce_saladas_nao_viram_itens(self):
        for descricao in [
            'Porção de 35 g. Repolho finamente fatiado, fresco, crocante.',
            'Porção de 80 g. Floretes de brócolis cozidos no ponto, verdes, macios.',
            'Porção de 50 g. Cubos de manga madura, frescos, naturalmente doces.',
        ]:
            self.assertEqual([], linhas_de_preparo(descricao, 1), descricao)

    def test_lista_de_verdade_continua_passando(self):
        linhas = linhas_de_preparo(
            'Ovos, óleo, leite, queijo ralado, polvilho doce, polvilho azedo e margarina.', 1
        )
        self.assertIn('- queijo ralado', linhas)
        self.assertIn('- margarina', linhas)

    def test_ponto_no_meio_com_cabecalho_ainda_vale(self):
        """"Suco natural de polpa 1 litro. Sabores: acerola, caju..." — o
        `:` diz onde a lista começa, então o ponto antes dele não atrapalha."""
        linhas = linhas_de_preparo(
            'Suco natural de polpa 1 litro. Sabores: acerola, caju, abacaxi ou goiaba.', 1
        )
        self.assertTrue(any('acerola' in l for l in linhas), linhas)
