"""
Preço da salada montada é derivado no SERVIDOR, nunca aceito do cliente.

Contexto: o endpoint de add ao carrinho é AllowAny e aceitava `unit_price` do corpo
da requisição, gravando-o como está. Isso valia tanto para o combo virtual (salada
montada) quanto para o combo REAL — bastava mandar `unit_price` junto do `combo_id`
para o preço do cliente vencer o preço cadastrado.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreCart, StoreCategory, StoreCombo, StoreProduct
from apps.stores.services.cart_service import CartService

User = get_user_model()


@pytest.fixture
def store(db):
    owner = User.objects.create_user(username='dono_salada', password='x')
    return Store.objects.create(owner=owner, name='Cê Saladas', slug='ce-saladas-test')


@pytest.fixture
def categoria(store):
    return StoreCategory.objects.create(store=store, name='Ingredientes', slug='ingredientes')


@pytest.fixture
def ingredientes(store, categoria):
    def novo(nome, slug, preco):
        return StoreProduct.objects.create(
            store=store, category=categoria, name=nome, slug=slug,
            price=Decimal(preco), is_active=True,
        )
    return {
        'alface': novo('Alface', 'alface', '4.00'),
        'frango': novo('Frango', 'frango', '12.50'),
        'tomate': novo('Tomate', 'tomate', '3.00'),
        'mostarda': novo('Mostarda e Mel', 'mostarda-mel', '2.00'),  # molho: sempre grátis
    }


@pytest.fixture
def combo_builder(store):
    """O combo 'monte-sua-salada' é o preço-base da salada montada."""
    return StoreCombo.objects.create(
        store=store, name='Monte sua Salada', slug='monte-sua-salada',
        price=Decimal('10.00'), is_active=True,
    )


@pytest.fixture
def cart(store):
    return StoreCart.objects.create(store=store, session_key='k-teste')


def _custom(ings):
    return {'is_salad_builder': True, 'ingredients': ings}


@pytest.mark.django_db
class TestPrecoSaladaCustomizada:

    def test_preco_vem_do_banco_e_ignora_o_que_o_cliente_mandou(self, store, combo_builder, ingredientes):
        """base 10 + alface 4 + frango 12,50 = 26,50 — mesmo com o cliente pedindo 0,01."""
        custom = _custom([
            {'id': str(ingredientes['alface'].id), 'name': 'Alface', 'price': 999, 'role': 'base'},
            {'id': str(ingredientes['frango'].id), 'name': 'Frango', 'price': 0, 'role': 'proteina'},
        ])
        preco = CartService.price_custom_salad(store, custom)
        assert preco == Decimal('26.50')

    def test_molho_nao_soma(self, store, combo_builder, ingredientes):
        """Molho é grátis — a regra do front (role == 'molho' -> 0) vale no servidor."""
        custom = _custom([
            {'id': str(ingredientes['alface'].id), 'name': 'Alface', 'role': 'base'},
            {'id': str(ingredientes['mostarda'].id), 'name': 'Mostarda e Mel', 'role': 'molho'},
        ])
        assert CartService.price_custom_salad(store, custom) == Decimal('14.00')  # 10 + 4

    def test_ingrediente_de_outra_loja_e_ignorado(self, store, combo_builder, ingredientes, db):
        """Isolamento multi-tenant: id de produto de outra loja não entra na conta."""
        outro_dono = User.objects.create_user(username='outro', password='x')
        outra = Store.objects.create(owner=outro_dono, name='Outra', slug='outra-loja-test')
        cat2 = StoreCategory.objects.create(store=outra, name='C', slug='c')
        caro = StoreProduct.objects.create(
            store=outra, category=cat2, name='Caro', slug='caro', price=Decimal('500.00'), is_active=True
        )
        custom = _custom([
            {'id': str(ingredientes['alface'].id), 'name': 'Alface', 'role': 'base'},
            {'id': str(caro.id), 'name': 'Caro', 'role': 'complemento'},
        ])
        assert CartService.price_custom_salad(store, custom) == Decimal('14.00')

    def test_sem_combo_base_a_loja_cobra_so_os_ingredientes(self, store, ingredientes):
        """Loja sem o combo 'monte-sua-salada' — base 0, não quebra."""
        custom = _custom([{'id': str(ingredientes['frango'].id), 'name': 'Frango', 'role': 'proteina'}])
        assert CartService.price_custom_salad(store, custom) == Decimal('12.50')

    def test_add_combo_virtual_grava_o_preco_do_servidor(self, store, cart, combo_builder, ingredientes):
        """O item do carrinho nasce com o preço derivado, não com o do cliente."""
        custom = _custom([
            {'id': str(ingredientes['alface'].id), 'name': 'Alface', 'role': 'base'},
            {'id': str(ingredientes['frango'].id), 'name': 'Frango', 'role': 'proteina'},
        ])
        item = CartService.add_combo(
            cart, combo=None, quantity=2, customizations=custom,
            combo_name='Monte sua Salada', unit_price=Decimal('0.01'),  # tentativa de fraude
        )
        assert item.unit_price == Decimal('26.50')
        assert item.subtotal == Decimal('53.00')


@pytest.mark.django_db
class TestPrecoComboReal:

    def test_combo_real_ignora_unit_price_do_cliente(self, store, cart, combo_builder):
        """Regressão do buraco em cart_service.py:148 — o cadastro sempre vence."""
        item = CartService.add_combo(
            cart, combo=combo_builder, quantity=1, unit_price=Decimal('0.01'),
        )
        assert item.unit_price == Decimal('10.00')
        assert item.subtotal == Decimal('10.00')
