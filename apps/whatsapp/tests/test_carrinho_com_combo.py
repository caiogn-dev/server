"""O resumo do carrinho precisa mostrar o combo — e somar o preço dele.

Sem isto, o combo entrava nos itens pendentes e sumia da tela: o cliente
conferia um subtotal MENOR do que ia pagar. Num combo de R$ 239,98 a diferença
não passa despercebida na hora do PIX, mas aí a confiança já foi.

O resumo tem uma implementação só (`_texto_do_carrinho`), usada pelo fluxo de
produto e pela montagem de combo. Duas versões divergiriam — e resumo
divergente é o cliente conferindo um total que não é o cobrado.
"""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.stores.models import StoreCombo, StoreProduct
from apps.stores.models.combo_group import (
    ComboProductGroup, ComboProductGroupProductOption,
)
from apps.stores.tests.factories import make_store
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def sabores(loja):
    return [
        StoreProduct.objects.create(
            store=loja, name=nome, slug=nome.lower().replace(' ', '-'),
            price=Decimal('47.99'), is_active=True, status='active',
        )
        for nome in ('Especial Filé de Frango', 'Magnifico Camarão')
    ]


@pytest.fixture
def combo(loja, sabores):
    c = StoreCombo.objects.create(
        store=loja, name='COMBO 5 SALADAS', slug='combo-5',
        price=Decimal('239.98'), is_active=True,
    )
    g = ComboProductGroup.objects.create(
        combo=c, title='Escolha suas 5 saladas',
        min_selections=5, max_selections=5, is_required=True,
    )
    for p in sabores:
        ComboProductGroupProductOption.objects.create(group=g, product=p)
    return c, g


def _handler(loja):
    h = InteractiveReplyHandler.__new__(InteractiveReplyHandler)
    h.store = loja
    h.account = MagicMock()
    h.conversation = MagicMock()
    h.company_profile = MagicMock()
    return h


@pytest.mark.django_db
class TestOComboApareceNoResumo:
    def test_o_nome_e_o_preco_entram(self, loja, combo, sabores):
        c, g = combo
        item = {'combo_id': str(c.id), 'quantity': 1,
                'group_selections': {str(g.id): [str(sabores[0].id)] * 5}}

        texto = _handler(loja)._texto_do_carrinho([item])

        assert 'COMBO 5 SALADAS' in texto
        assert '239.98' in texto

    def test_os_sabores_escolhidos_voltam_pro_cliente(self, loja, combo, sabores):
        """Não ver a escolha de volta é quando ele desconfia que o bot não anotou."""
        c, g = combo
        item = {'combo_id': str(c.id), 'quantity': 1, 'group_selections': {
            str(g.id): [str(sabores[0].id)] * 2 + [str(sabores[1].id)] * 3,
        }}

        texto = _handler(loja)._texto_do_carrinho([item])

        assert '2x Especial Filé de Frango' in texto
        assert '3x Magnifico Camarão' in texto

    def test_o_subtotal_INCLUI_o_combo(self, loja, combo, sabores):
        """O bug: combo no carrinho e fora da conta = total menor que o cobrado."""
        c, g = combo
        item = {'combo_id': str(c.id), 'quantity': 1, 'group_selections': {}}

        texto = _handler(loja)._texto_do_carrinho([item])

        assert 'R$ 239.98' in texto.split('Subtotal')[1]

    def test_combo_e_produto_no_mesmo_carrinho_somam(self, loja, combo, sabores):
        c, g = combo
        itens = [
            {'combo_id': str(c.id), 'quantity': 1, 'group_selections': {}},
            {'product_id': str(sabores[0].id), 'quantity': 2},
        ]

        texto = _handler(loja)._texto_do_carrinho(itens)

        # 239.98 + 2 × 47.99 = 335.96
        assert '335.96' in texto


@pytest.mark.django_db
class TestOQueNaoPodeRegredir:
    def test_carrinho_so_de_produto_continua_igual(self, loja, sabores):
        texto = _handler(loja)._texto_do_carrinho(
            [{'product_id': str(sabores[0].id), 'quantity': 2}],
        )

        assert '2x Especial Filé de Frango' in texto
        assert '95.98' in texto

    def test_combo_apagado_nao_derruba_o_resumo(self, loja, sabores):
        """Item pendente sobrevive ao catálogo mudar — não pode explodir."""
        import uuid
        texto = _handler(loja)._texto_do_carrinho(
            [{'combo_id': str(uuid.uuid4()), 'quantity': 1},
             {'product_id': str(sabores[0].id), 'quantity': 1}],
        )

        assert 'Especial Filé de Frango' in texto

    def test_carrinho_vazio_nao_estoura(self, loja):
        assert 'Subtotal' in _handler(loja)._texto_do_carrinho([])
