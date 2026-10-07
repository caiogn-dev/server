"""Salada grátis vale para a salada escolhida DENTRO de um combo.

07/10, Cê Saladas (CE-2610073719): cliente com 1 salada grátis disponível,
sacola com o combo Queridinha + Suco + Sobremesa — "tentei usar o item grátis
e nada foi abatido, nenhuma salada". O resgate só via salada AVULSA: o combo
não tem categoria, então nunca qualificava, e a Queridinha lá dentro não
contava.

Regra: a salada que qualifica, avulsa ou escolhida num combo, pode ser a
grátis. Desconto = preço da própria salada, limitado ao valor da linha do
combo (nunca abate suco nem sobremesa).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreCart, StoreCartComboItem, StoreCartItem, StoreCategory, StoreCombo, StoreProduct
from apps.stores.models.combo_group import ComboProductGroup
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class SaladaDentroDoComboTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-fid-combo', password='x')
        self.loja = Store.objects.create(owner=dono, name='Cê', slug='ce-fid-combo')
        self.saladas = StoreCategory.objects.create(store=self.loja, name='Saladas Especiais', slug='saladas-especiais')
        bebidas = StoreCategory.objects.create(store=self.loja, name='Bebidas', slug='bebidas')
        self.loja.metadata = {'loyalty_qualifying_categories': [str(self.saladas.id)]}
        self.loja.save(update_fields=['metadata'])
        self.queridinha = StoreProduct.objects.create(
            store=self.loja, category=self.saladas, name='Queridinha', slug='queridinha', price=Decimal('36.99'),
        )
        self.suco = StoreProduct.objects.create(
            store=self.loja, category=bebidas, name='Suco', slug='suco', price=Decimal('8.00'),
        )
        self.combo = StoreCombo.objects.create(
            store=self.loja, name='Queridinha + Suco + Sobremesa', slug='qss', price=Decimal('54.99'),
        )
        self.g_salada = ComboProductGroup.objects.create(combo=self.combo, title='Salada')
        self.g_bebida = ComboProductGroup.objects.create(combo=self.combo, title='Bebida')
        self.carrinho = StoreCart.objects.create(store=self.loja, session_key='fid-combo')

    def _combo(self, quantidade=1, preco=None):
        selecoes = {str(self.g_salada.id): [str(self.queridinha.id)], str(self.g_bebida.id): [str(self.suco.id)]}
        return StoreCartComboItem.objects.create(
            cart=self.carrinho, combo=self.combo, quantity=quantidade, group_selections=selecoes,
            customizations={'selections': selecoes}, unit_price=preco,
        )

    def test_so_o_combo_abate_a_salada_de_dentro(self):
        self._combo()
        self.assertEqual(CheckoutService._cart_salad_discount(self.carrinho), Decimal('36.99'))

    def test_desconto_nunca_passa_do_valor_do_combo(self):
        self.combo.price = Decimal('30.00')
        self.combo.save(update_fields=['price'])
        self._combo()
        self.assertEqual(CheckoutService._cart_salad_discount(self.carrinho), Decimal('30.00'))

    def test_salada_avulsa_mais_barata_continua_sendo_a_escolhida(self):
        barata = StoreProduct.objects.create(
            store=self.loja, category=self.saladas, name='Basic', slug='basic', price=Decimal('29.90'),
        )
        StoreCartItem.objects.create(cart=self.carrinho, product=barata, quantity=1)
        self._combo()
        self.assertEqual(CheckoutService._cart_salad_discount(self.carrinho), Decimal('29.90'))

    def test_combo_sem_salada_nao_abate(self):
        selecoes = {str(self.g_bebida.id): [str(self.suco.id)]}
        StoreCartComboItem.objects.create(
            cart=self.carrinho, combo=self.combo, quantity=1, group_selections=selecoes,
            customizations={'selections': selecoes},
        )
        self.assertEqual(CheckoutService._cart_salad_discount(self.carrinho), Decimal('0'))
