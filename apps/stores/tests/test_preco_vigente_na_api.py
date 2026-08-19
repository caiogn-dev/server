"""A API precisa entregar o preço que o cliente vai pagar HOJE.

O model tem o SSOT `preco_vigente()`, e a docstring dele avisa: "não pode
mostrar na vitrine e cobrar outro no checkout". Só que o serializer expunha
`price`, `promo_price` e `promo_weekday` crus e nunca o preço resolvido —
então a vitrine mostrava R$ 42,99 numa quarta-feira em que o carrinho cobrava
R$ 30,75. A "quarta da almôndega" funcionava na cobrança e era invisível para
quem decide comprar.

`price` continua sendo o preço de cadastro (o painel edita esse campo). Quem
mostra preço passa a ler `preco_vigente`.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreProduct
from apps.stores.api.serializers import StoreProductSerializer


class PrecoVigenteNaApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_pv', email='d@pv.com', password='x')
        self.store = Store.objects.create(name='Loja PV', slug='loja-pv', owner=owner)

    def _produto(self, weekday):
        return StoreProduct.objects.create(
            store=self.store, name='Almôndega Premium',
            price=Decimal('42.99'), compare_at_price=Decimal('44.90'),
            promo_price=Decimal('30.75'), promo_weekday=weekday,
        )

    def test_no_dia_da_promo_entrega_o_preco_promocional(self):
        p = self._produto(date.today().weekday())
        d = StoreProductSerializer(p).data
        self.assertEqual(Decimal(str(d['preco_vigente'])), Decimal('30.75'))
        self.assertTrue(d['em_promocao'])

    def test_fora_do_dia_entrega_o_preco_cheio(self):
        p = self._produto((date.today().weekday() + 1) % 7)
        d = StoreProductSerializer(p).data
        self.assertEqual(Decimal(str(d['preco_vigente'])), Decimal('42.99'))
        self.assertFalse(d['em_promocao'])

    def test_price_continua_sendo_o_cadastro(self):
        """O painel edita `price` — mudar a semântica dele quebraria a edição."""
        p = self._produto(date.today().weekday())
        d = StoreProductSerializer(p).data
        self.assertEqual(Decimal(str(d['price'])), Decimal('42.99'))

    def test_produto_sem_promo_tem_vigente_igual_ao_price(self):
        p = StoreProduct.objects.create(
            store=self.store, name='Suco', price=Decimal('12.00'),
        )
        d = StoreProductSerializer(p).data
        self.assertEqual(Decimal(str(d['preco_vigente'])), Decimal('12.00'))
        self.assertFalse(d['em_promocao'])

    def test_promo_cadastrada_pela_metade_nao_engana(self):
        """Promo sem dia (ou dia sem promo) não vale — regra do SSOT."""
        p = StoreProduct.objects.create(
            store=self.store, name='Meia', price=Decimal('20.00'),
            promo_price=Decimal('10.00'), promo_weekday=None,
        )
        d = StoreProductSerializer(p).data
        self.assertEqual(Decimal(str(d['preco_vigente'])), Decimal('20.00'))
